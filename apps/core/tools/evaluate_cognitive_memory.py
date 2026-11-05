#!/usr/bin/env python3
"""Real local ingestion and answer scoring over the synthetic memory corpus.

Archive assistant messages are explicitly labelled fixture placeholders. Memory
extraction, Qdrant projection, retrieval, and scored answers use real providers.
No expected fact is substituted for a generated answer. Journals retain failures.
Run in the Core environment; the child uses the separate memory lock environment.
Use only a fresh, named isolated state directory.
"""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import socket
import statistics
import subprocess
import sys
import threading
import time
import uuid

from okal_core.cognitive.learning import OWNER, EXTERNAL
from okal_core.cognitive.ledger import SENSITIVE
from okal_core.cognitive.process import AdapterClient
from okal_core.cognitive.retrieval import Retrieval
from okal_core.cognitive.service import MemoryWorker
from okal_core.intelligence import Intelligence, respond
from okal_core.mail.private import write_private
from okal_core.store import Store, private_file


def normalized(value):
    return value.casefold().translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789')).replace('ـ','')


def has_concepts(answer, concepts):
    text=normalized(answer)
    return all(any(normalized(option) in text for option in group) for group in concepts)


def quantile(values, fraction):
    return sorted(values)[max(0,math.ceil(len(values)*fraction)-1)] if values else None


class Samples:
    def __init__(self, directory):
        self.directory=directory
        self.stop=threading.Event()
        self.rows=[]
        self.thread=threading.Thread(target=self.run,daemon=True)

    def run(self):
        while not self.stop.is_set():
            row={'monotonic':time.monotonic(),'wall_time':time.time()}
            row['ram']={line.split(':')[0]:int(line.split()[1])*1024
                for line in Path('/proc/meminfo').read_text().splitlines()
                if line.startswith(('MemTotal:','MemAvailable:','SwapFree:'))}
            try:
                gpu=subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu',
                    '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3,check=True)
                row['gpu_used_mib'],row['gpu_utilization']=map(int,gpu.stdout.strip().split(','))
            except (OSError,ValueError,subprocess.SubprocessError):
                row['gpu_used_mib']=None
            self.rows.append(row)
            self.stop.wait(1)

    def finish(self):
        self.stop.set();self.thread.join(timeout=5)
        (self.directory/'resources.json').write_text(json.dumps(self.rows,indent=2))
        if not self.rows:return {}
        gpu=[r['gpu_used_mib'] for r in self.rows if r['gpu_used_mib'] is not None]
        return {'samples':len(self.rows),'min_available_ram_bytes':min(r['ram']['MemAvailable'] for r in self.rows),
            'peak_total_used_ram_bytes':max(r['ram']['MemTotal']-r['ram']['MemAvailable'] for r in self.rows),
            'baseline_gpu_used_mib':gpu[0] if gpu else None,'peak_total_gpu_used_mib':max(gpu) if gpu else None,
            'parent_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            'scope':'Observed whole-device RAM/VRAM peaks include existing desktop/services; sampled, not exclusive attribution.'}


class ObservedAdapter:
    def __init__(self, client, store, gold, directory, inject_interrupt):
        self.client,self.store,self.gold,self.directory=client,store,gold,directory
        self.config_path=client.config_path
        self.records=[];self.rpc=[];self.interrupted=False;self.inject_interrupt=inject_interrupt

    def call(self, method, payload, **kwargs):
        started=time.monotonic()
        source=None;timer=None
        if method=='extract':
            with self.store.connect() as db:
                row=db.execute("SELECT turn_id FROM memory_jobs WHERE status='running' ORDER BY updated_at DESC LIMIT 1").fetchone()
                source=row[0] if row else None
            if self.inject_interrupt and not self.interrupted:
                self.interrupted=True
                timer=threading.Timer(2,self.client._stop);timer.start()
        try:
            actual=self.client.call(method,payload,**kwargs)
        finally:
            if timer:timer.cancel();timer.join()
            self.rpc.append({'method':method,'seconds':time.monotonic()-started})
        if method=='extract':
            targets=self.gold.get(source,[])
            used=set();matched=0
            for target in targets:
                for index,item in enumerate(actual):
                    if index in used:continue
                    if (all(item.get(k)==v for k,v in target.items() if k!='terms')
                            and all(normalized(term) in normalized(item['quote']) for term in target.get('terms',[]))):
                        matched+=1;used.add(index);break
            record={'turn_id':source,'expected':targets,'actual':actual,'matched':matched,
                'model_called':bool(OWNER.search(payload['message'])) and not bool(EXTERNAL.search(payload['message']) or SENSITIVE.search(payload['message'])),
                'seconds':time.monotonic()-started}
            self.records.append(record)
            with (self.directory/'extraction.jsonl').open('a') as stream:stream.write(json.dumps(record,ensure_ascii=False)+'\n')
        return actual

    def close(self):
        self.client.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--conversations',type=int,default=200)
    parser.add_argument('--answers',type=int,default=240)
    parser.add_argument('--max-seconds',type=int,default=7200)
    parser.add_argument('--interrupt-once',action='store_true')
    parser.add_argument('--pilot',action='store_true',help='Ten representative chats across all phases; not a release gate')
    args=parser.parse_args()
    if (args.state.exists() or 'okal-core' in args.state.parts or not args.state.is_absolute()
            or not 1<=args.conversations<=200 or not 0<=args.answers<=240 or not 60<=args.max_seconds<=10800):
        parser.error('fresh isolated state and bounded corpus/answer/runtime limits required')
    os.umask(0o077);args.state.mkdir(mode=0o700,parents=True)
    private_file(args.state/'benchmark.lock')
    lock=os.open(args.state/'benchmark.lock',os.O_RDWR|os.O_NOFOLLOW)
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    network_denied=[]
    def audit(event,values):
        if event=='socket.connect':
            sock,address=values
            if sock.family!=socket.AF_INET or address[0]!='127.0.0.1' or address[1] not in {11434,8766}:
                network_denied.append('destination_denied');raise PermissionError('evaluation_network_denied')
        elif event=='socket.getaddrinfo' and values[0]!='127.0.0.1':
            network_denied.append('dns_denied');raise PermissionError('evaluation_dns_denied')
    sys.addaudithook(audit)
    config=json.loads(args.config.read_text())
    # Copy reviewed pins only. No owner mail configuration or credentials.
    write_private(args.state/'cognitive.json',config)
    write_private(args.state/'mail/config.json',{
        'account':'memory-evaluation@example.test','owner_name':'Synthetic Owner',
        'model':config['llm']['name'],'model_digest':config['llm']['digest'],
        'local_only_confirmed':True,'sync_enabled':False,'send_enabled':False,
        'trash_enabled':False,'daily_at':None,'notify_new_mail':False})
    corpus_path=Path(__file__).parents[1]/'evals/cognitive-corpus.json'
    corpus=json.loads(corpus_path.read_text())
    selected=([corpus['conversations'][i] for i in (0,1,40,41,100,101,140,141,180,181)]
              if args.pilot else corpus['conversations'][:args.conversations])
    store=Store(args.state);chat=Intelligence(store);ledger=chat.cognitive
    projects={p['label']:ledger.save_project(p['name'],p['description'])['id'] for p in corpus['projects']}
    conversations={};gold={};source_turns=[]
    started=time.monotonic();deadline=started+args.max_seconds
    for conversation in selected:
        cid=chat.create(conversation['title'])['id'];conversations[conversation['label']]=cid
        ledger.associate(cid,projects[conversation['project']])
        for index,turn in enumerate(conversation['turns']):
            request=uuid.uuid5(uuid.NAMESPACE_URL,'okal-eval/'+conversation['label']+'/'+str(index)).hex
            claim=chat.begin(cid,request,turn['text'])
            chat.finish(claim['turn_id'],claim['lease'],{'answer':turn['assistant'],
                'mode':'fixture_archive','source':'synthetic_corpus_fixture'})
            gold[claim['turn_id']]=turn['expected'];source_turns.append(claim['turn_id'])
    manifest={'corpus_sha256':hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        'conversations':conversations,'projects':projects,'source_turns':source_turns,
        'archive_assistant_mode':'fixture_archive; scripted dialogue is never scored as model output',
        'started_wall_time':time.time(),'limit_conversations':args.conversations,'limit_answers':args.answers}
    (args.state/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    worker=MemoryWorker(store)
    observed=ObservedAdapter(worker.adapter,store,gold,args.state,args.interrupt_once)
    worker.adapter=observed;store.memory_adapter=observed
    samples=Samples(args.state);samples.thread.start()
    ingestion_started=time.monotonic();iterations=0
    answers=[];retrieval_latencies=[];failure=None
    report={'incomplete':True,'source_conversations':len(selected),'source_turns':len(source_turns)}
    try:
        while time.monotonic()<deadline:
            worker.tick();iterations+=1
            health=ledger.health()
            pending=health['jobs'].get('pending',0)+health['jobs'].get('running',0)
            projections=health['projections'].get('pending',0)
            if iterations%10==0:
                print(json.dumps({'phase':'ingestion','iterations':iterations,'health':health}),flush=True)
            if not pending and not projections:break
            if iterations>2000:raise RuntimeError('bounded_iteration_limit')
            if not observed.records or iterations%20==0:time.sleep(.2)
        else:raise RuntimeError('bounded_evaluation_deadline')
        ingestion_seconds=time.monotonic()-ingestion_started
        with store.connect() as db:
            profile_before={r['key']:r['content'] for r in db.execute("SELECT key,content FROM chat_memories WHERE scope='owner'")}
        # Reopen the actual adapter and SQLite before scoring durable recall.
        observed.close()
        recovered=Intelligence(Store(args.state))
        assert recovered.cognitive.backfill()['enqueued']==0,'non_idempotent_backfill'
        queries=[q for q in corpus['queries'] if (not q.get('conversation') or q['conversation'] in conversations)
                 and all(label in conversations for label in q.get('requires',[]))]
        # Interleave families so a bounded pilot still exercises all three.
        ordered=[]
        families={name:[q for q in queries if q['family']==name] for name in ('preference','project','conversation')}
        while any(families.values()):
            for group in families.values():
                if group:ordered.append(group.pop(0))
        for query in ordered[:args.answers]:
            if time.monotonic()>=deadline:raise RuntimeError('bounded_evaluation_deadline')
            cid=conversations[query['conversation']] if query.get('conversation') else chat.create('Synthetic held-out recall')['id']
            if query.get('project'):
                ledger.associate(cid,projects[query['project']])
            before=time.monotonic()
            selected_records,metadata=Retrieval(ledger).select(cid,query['question'])
            retrieval_latencies.append(time.monotonic()-before)
            before=time.monotonic()
            actual=respond(store,cid,uuid.uuid4().hex,query['question'])
            answer=actual['answer']
            passed=actual['mode']=='pinned_local_ollama' and has_concepts(answer,query['concepts'])
            row={'id':query['id'],'family':query['family'],'question':query['question'],
                'expected_concepts':query['concepts'],'actual_answer':answer,'mode':actual['mode'],
                'passed':passed,'seconds':time.monotonic()-before,'selected_ids':[r['id'] for r in selected_records],
                'semantic_index':metadata.get('semantic_index'),'sources':actual.get('context_sources',[])}
            row['expected_reply_language']=query['expected_reply_language']
            row['inference_usage']=actual.get('inference_usage',{})
            row['subject']=query.get('subject')
            arabic=len(re.findall(r'[\u0621-\u064a]',answer));latin=len(re.findall(r'[a-z]',answer,re.I))
            row['language_adherence']=(None if arabic+latin<20 else
                (latin>arabic if query['expected_reply_language']=='English' else arabic>=latin))
            answers.append(row)
            with (args.state/'answers.jsonl').open('a') as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
            print(json.dumps({'phase':'answer','id':query['id'],'passed':passed,'mode':actual['mode']}),flush=True)
        # Exercise ingestion of the held-out questions too: temporary response
        # overrides must not silently change permanent profile preferences.
        for drain in range(1000):
            if time.monotonic()>=deadline:raise RuntimeError('bounded_evaluation_deadline')
            worker.tick()
            health=ledger.health()
            if not health['jobs'].get('pending',0) and not health['jobs'].get('running',0) and not health['projections'].get('pending',0):break
            if drain%10==0:print(json.dumps({'phase':'question_ingestion','health':health}),flush=True)
            time.sleep(.1)
        with store.connect() as db:
            profile_after={r['key']:r['content'] for r in db.execute("SELECT key,content FROM chat_memories WHERE scope='owner'")}
        with store.connect() as db:
            integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
            foreign_keys=[tuple(r) for r in db.execute('PRAGMA foreign_key_check')]
            duplicates=db.execute('SELECT COUNT(*) FROM (SELECT scope,key,COUNT(*) AS n FROM chat_memories GROUP BY scope,key HAVING n>1)').fetchone()[0]
            archive_count=db.execute('SELECT COUNT(*) FROM chat_turns WHERE id IN (SELECT turn_id FROM memory_jobs)').fetchone()[0]
        matched=sum(r['matched'] for r in observed.records)
        proposed=sum(len(r['actual']) for r in observed.records)
        expected=sum(len(r['expected']) for r in observed.records)
        by_family={name:{'answered':sum(r['family']==name for r in answers),
            'passed':sum(r['family']==name and r['passed'] for r in answers)} for name in ('preference','project','conversation')}
        for result in by_family.values():result['recall']=result['passed']/result['answered'] if result['answered'] else None
        report={'complete_corpus':len(selected)==200,'source_conversations':len(selected),
            'source_turns':len(source_turns),'archive_turns_including_queries':archive_count,
            'archive_assistant_mode':manifest['archive_assistant_mode'],'actual_scored_answers':len(answers),
            'families':by_family,'extraction_precision':matched/proposed if proposed else 0,
            'extraction_recall':matched/expected if expected else 1,
            'false_candidates_on_negative_sources':sum(len(r['actual']) for r in observed.records if not r['expected']),
            'ingestion_seconds':ingestion_seconds,'ingestion_turns_per_second':len(source_turns)/ingestion_seconds,
            'retrieval_seconds_p50':statistics.median(retrieval_latencies) if retrieval_latencies else None,
            'retrieval_seconds_p95':quantile(retrieval_latencies,.95),
            'answer_seconds_p50':statistics.median(r['seconds'] for r in answers) if answers else None,
            'answer_seconds_p95':quantile([r['seconds'] for r in answers],.95),
            'integrity_check':integrity,'foreign_key_violations':foreign_keys,'duplicate_current_keys':duplicates,
            'forbidden_python_network_attempts':len(network_denied),'health':ledger.health(),
            'profile_unchanged_by_recall_questions':profile_before==profile_after,
            'actual_prompt_tokens_max':max((r['inference_usage'].get('prompt_eval_count',0) for r in answers),default=0),
            'interruption_injected':observed.interrupted,'elapsed_monotonic_seconds':time.monotonic()-started,
            'disk_bytes':sum(p.stat().st_size for p in args.state.rglob('*') if p.is_file())}
    except (Exception,KeyboardInterrupt) as exc:
        failure=type(exc).__name__
        report={'incomplete':True,'failure_type':failure,'health':ledger.health(),
                'source_conversations':len(selected),'source_turns':len(source_turns),'actual_scored_answers':len(answers)}
    finally:
        observed.close();report['resources']=samples.finish();os.close(lock)
    (args.state/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False),flush=True)
    return 2 if failure else 0


if __name__=='__main__':
    sys.exit(main())
