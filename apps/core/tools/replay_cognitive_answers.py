#!/usr/bin/env python3
"""Rebuild and rescore all held-out answers on a fresh clone of synthetic ingestion.

This is a current-code answer/index regression run, not another extraction run.
Only the 1,000 labelled source turns survive in the clone; previous model answers
are removed before replay. The original finished benchmark is read-only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import statistics
import subprocess
import sys
import time
import uuid

from evaluate_cognitive_memory import Samples, has_concepts, lifecycle_probe, quantile
from audit_cognitive_answers import audit as audit_answers
from okal_core.cognitive.retrieval import Retrieval
from okal_core.cognitive.service import MemoryWorker
from okal_core.intelligence import Intelligence, respond
from okal_core.mail.private import write_private
from okal_core.store import Store


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--max-seconds',type=int,default=5400)
    args=parser.parse_args()
    if (not args.source.is_absolute() or not args.state.is_absolute() or args.state.exists()
            or any('okal-core' in p.parts for p in (args.source,args.state))
            or not 60<=args.max_seconds<=5400):parser.error('finished synthetic source and fresh isolated state required')
    original=json.loads((args.source/'report.json').read_text())
    manifest=json.loads((args.source/'manifest.json').read_text())
    if (original.get('incomplete') or original.get('source_turns')!=1000
            or not manifest.get('archive_assistant_mode','').startswith('fixture_archive;')):
        parser.error('completed 200-conversation synthetic ingestion required')
    os.umask(0o077);args.state.mkdir(parents=True,mode=0o700)
    with sqlite3.connect((args.source/'core.sqlite3').as_uri()+'?mode=ro',uri=True) as source, sqlite3.connect(args.state/'core.sqlite3') as target:
        source.backup(target)
        target.execute('PRAGMA foreign_keys=ON')
        target.execute('DELETE FROM chat_turns WHERE id NOT IN (SELECT value FROM json_each(?))',
                       (json.dumps(manifest['source_turns']),))
        target.commit()
        assert target.execute('SELECT COUNT(*) FROM chat_turns').fetchone()[0]==1000
        assert all(json.loads(row[0])['mode']=='fixture_archive' for row in target.execute('SELECT response FROM chat_turns'))
    config=json.loads(args.config.read_text());write_private(args.state/'cognitive.json',config)
    write_private(args.state/'mail/config.json',{'account':'replay-evaluation@example.test',
        'model':config['llm']['name'],'model_digest':config['llm']['digest'],
        'local_only_confirmed':True,'sync_enabled':False,'send_enabled':False,'trash_enabled':False,
        'daily_at':None,'notify_new_mail':False})
    source_head=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    clean=not subprocess.run(['git','status','--porcelain'],capture_output=True,text=True,check=True).stdout.strip()
    manifest.update(ingestion_source_head=manifest['source_head'],source_head=source_head,source_clean=clean,
        replay_of_report_sha256=hashlib.sha256((args.source/'report.json').read_bytes()).hexdigest(),
        replay_previous_answers_removed=True)
    (args.state/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    corpus=json.loads((Path(__file__).parents[1]/'evals/cognitive-corpus.json').read_text())
    assert hashlib.sha256((Path(__file__).parents[1]/'evals/cognitive-corpus.json').read_bytes()).hexdigest()==manifest['corpus_sha256']
    denied=[]
    def network_audit(event,values):
        if event=='socket.connect':
            sock,address=values
            if sock.family!=socket.AF_INET or address!=('127.0.0.1',11434):
                denied.append('destination_denied');raise PermissionError('replay_network_denied')
        elif event=='socket.getaddrinfo' and values[0]!='127.0.0.1':
            denied.append('dns_denied');raise PermissionError('replay_dns_denied')
    sys.addaudithook(network_audit)
    store=Store(args.state);chat=Intelligence(store);ledger=chat.cognitive;worker=MemoryWorker(store)
    samples=Samples(args.state);samples.thread.start()
    started=time.monotonic();deadline=started+args.max_seconds;answers=[];retrieval_times=[]
    def drain():
        for tick in range(1500):
            if time.monotonic()>deadline:raise RuntimeError('bounded_replay_deadline')
            worker.tick();health=ledger.health()
            if (not health['jobs'].get('pending',0) and not health['jobs'].get('running',0)
                    and not health['projections'].get('pending',0) and health['rebuild']['status']=='current'):return
            if tick%20==0:print(json.dumps({'phase':'drain','health':health}),flush=True)
        raise RuntimeError('bounded_replay_iterations')
    report={'incomplete':True}
    try:
        ledger.request_rebuild();drain()
        with store.connect() as db:
            profile_before=[tuple(r) for r in db.execute("SELECT id,revision,content FROM chat_memories WHERE scope='owner' ORDER BY id")]
        for query in corpus['queries']:
            if time.monotonic()>deadline:raise RuntimeError('bounded_replay_deadline')
            cid=manifest['conversations'][query['conversation']] if query.get('conversation') else chat.create('Synthetic current-code recall')['id']
            if query.get('project'):ledger.associate(cid,manifest['projects'][query['project']])
            before=time.monotonic();selected,metadata=Retrieval(ledger).select(cid,query['question'])
            retrieval_times.append(time.monotonic()-before)
            with store.connect() as db:
                relevant={r['id'] for r in db.execute('SELECT * FROM chat_memories') if has_concepts(r['content'],query['concepts']) and (
                    r['scope']=='owner' if query['family']=='preference' else
                    r['scope']=='project:'+manifest['projects'][query['project']] if query['family']=='project' else r['conversation_id']==cid)}
            before=time.monotonic();actual=respond(store,cid,uuid.uuid4().hex,query['question']);answer=actual['answer']
            retrieved={r['id'] for r in selected};ar=len(re.findall(r'[\u0621-\u064a]',answer));latin=len(re.findall(r'[a-z]',answer,re.I))
            row={'id':query['id'],'family':query['family'],'subject':query.get('subject'),'question':query['question'],
                'expected_concepts':query['concepts'],'actual_answer':answer,'mode':actual['mode'],
                'passed':actual['mode']=='pinned_local_ollama' and has_concepts(answer,query['concepts']),
                'seconds':time.monotonic()-before,'selected_ids':sorted(retrieved),'sources':actual.get('context_sources',[]),
                'semantic_index':metadata.get('semantic_index'),'relevant_ledger_ids':sorted(relevant),
                'expected_reply_language':query['expected_reply_language'],'inference_usage':actual.get('inference_usage',{}),
                'language_adherence':None if ar+latin<20 else (latin>ar if query['expected_reply_language']=='English' else ar>=latin),
                'retrieval_precision_at_8':len(retrieved & relevant)/len(retrieved) if retrieved else 0,
                'retrieval_recall_at_8':len(retrieved & relevant)/len(relevant) if relevant else 0}
            answers.append(row)
            with (args.state/'answers.jsonl').open('a') as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
            print(json.dumps({'phase':'answer','id':row['id'],'passed':row['passed']}),flush=True)
        cid=chat.create('Synthetic unknown fact')['id']
        unknown=respond(store,cid,uuid.uuid4().hex,'What is my favorite editor? Only tell me if I actually shared it. Please reply in English.')
        unknown_text=unknown['answer'].casefold()
        unknown_pass=unknown['mode']=='pinned_local_ollama' and 'emacs' not in unknown_text and bool(re.search(
            r"don.t (?:know|have)|not (?:know|shared|provided|stored|recorded|remember)|no (?:record|saved|information)|haven.t|hasn.t|didn.t|wasn.t|not.*(?:memory|context)",unknown_text))
        (args.state/'unknown-answer.json').write_text(json.dumps(unknown,ensure_ascii=False,indent=2)+'\n')
        drain()
        with store.connect() as db:
            profile_after=[tuple(r) for r in db.execute("SELECT id,revision,content FROM chat_memories WHERE scope='owner' ORDER BY id")]
        lifecycle=lifecycle_probe(chat,worker.adapter)
        ledger.request_rebuild();drain()
        selected,context=Retrieval(ledger).select(cid,'amber canoe 672')
        lifecycle['forgotten_absent_after_rebuild']='amber canoe 672' not in json.dumps({'records':selected,'context':context})
        with store.connect() as db:
            integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
            fk=db.execute('PRAGMA foreign_key_check').fetchall()
            duplicates=db.execute('SELECT COUNT(*) FROM (SELECT scope,key FROM chat_memories GROUP BY scope,key HAVING COUNT(*)>1)').fetchone()[0]
        families={name:{'answered':sum(r['family']==name for r in answers),'passed':sum(r['family']==name and r['passed'] for r in answers)} for name in ('preference','project','conversation')}
        for group in families.values():group['recall']=group['passed']/group['answered']
        report={'source_head':source_head,'source_clean':clean,'ingestion_source_head':manifest['ingestion_source_head'],
            'source_turns':1000,'source_conversations':200,'actual_scored_answers':len(answers),
            'prior_model_answers_removed':True,'new_private_adapter_index_rebuilt':True,'families':families,
            'retrieval_seconds_p50':statistics.median(retrieval_times),'retrieval_seconds_p95':quantile(retrieval_times,.95),
            'answer_seconds_p50':statistics.median(r['seconds'] for r in answers),'answer_seconds_p95':quantile([r['seconds'] for r in answers],.95),
            'retrieval_precision_at_8_mean':statistics.mean(r['retrieval_precision_at_8'] for r in answers),
            'retrieval_recall_at_8_mean':statistics.mean(r['retrieval_recall_at_8'] for r in answers),
            'actual_prompt_tokens_max':max(r['inference_usage'].get('prompt_eval_count',0) for r in answers),
            'lifecycle_probe':lifecycle,'integrity_check':integrity,'foreign_key_violations':len(fk),'duplicate_current_keys':duplicates,
            'elapsed_monotonic_seconds':time.monotonic()-started,
            'consistency_gates':{'profile_stable':profile_before==profile_after,'unknown_fact':unknown_pass,
                'explicit_corrections':all(r['passed'] for r in answers if r['subject']=='style' or r['family']=='project'),
                'lifecycle':all(lifecycle.values()),'integrity':integrity=='ok' and not fk,'no_duplicates':duplicates==0,'no_external_attempts':not denied}}
    except Exception as exc:
        report={'incomplete':True,'failure_type':type(exc).__name__,'actual_scored_answers':len(answers)}
        raise
    finally:
        worker.stop();report['resources']=samples.finish()
        (args.state/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    audited=audit_answers(args.state)
    (args.state/'answer-audit.json').write_text(json.dumps(audited,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'report':report,'audit':{k:v for k,v in audited.items() if k!='rows'}},ensure_ascii=False),flush=True)
    return 0 if audited['quality_gates_passed'] and not audited['missing_persisted_responses'] and all(report['consistency_gates'].values()) else 2


if __name__=='__main__':raise SystemExit(main())
