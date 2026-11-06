#!/usr/bin/env python3
"""Bounded real Arabic/English transfer, conditional style and decision recall."""
import argparse
import json
import os
from pathlib import Path
import re
import time
import uuid

from okal_core.cognitive.service import MemoryWorker
from okal_core.intelligence import Intelligence, respond
from okal_core.mail.private import write_private
from okal_core.store import Store


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--profile-queries',action='store_true')
    args=parser.parse_args()
    if not args.state.is_absolute() or args.state.exists() or 'okal-core' in args.state.parts:
        parser.error('fresh absolute synthetic state required')
    os.umask(0o077);args.state.mkdir(parents=True,mode=0o700)
    config=json.loads(args.config.read_text());write_private(args.state/'cognitive.json',config)
    write_private(args.state/'mail/config.json',{'account':'personalization@example.test',
        'model':config['llm']['name'],'model_digest':config['llm']['digest'],
        'local_only_confirmed':True,'sync_enabled':False,'send_enabled':False,'trash_enabled':False,
        'daily_at':None,'notify_new_mail':False})
    store=Store(args.state);chat=Intelligence(store);worker=MemoryWorker(store)
    project=chat.cognitive.save_project('Harbor memory','Synthetic memory decisions.')
    other=chat.cognitive.save_project('Harbor archive','Synthetic archive decisions.')
    def seed(message,project_id=None):
        cid=chat.create('Synthetic source')['id']
        if project_id:chat.cognitive.associate(cid,project_id)
        claim=chat.begin(cid,uuid.uuid4().hex,message)
        chat.finish(claim['turn_id'],claim['lease'],{'answer':'Labelled source fixture, not model output.','mode':'fixture_archive'})
        return claim['turn_id']
    sources=[seed('Always answer in Egyptian Arabic unless I ask for English.'),
        seed('Always use English for technical documentation.'),
        seed('I prefer detailed answers with background explanations.'),
        seed('لا، أنا عايز ردودك مختصرة وتدخل في الموضوع على طول.'),
        seed('أنا ساكن في مدينة طنطا.'),
        seed('We chose Mem0 because we need multilingual memory consolidation.',project['id']),
        seed('We chose SQLite because we need an offline conversation archive.',other['id'])]
    if args.profile_queries:sources.append(seed('My name is Mira.'))
    started=time.monotonic();answers=[]
    try:
        for _ in range(50):
            if time.monotonic()-started>360:raise RuntimeError('bounded_ingestion_deadline')
            worker.tick();health=chat.cognitive.health()
            if health['jobs'].get('done')==len(sources) and not health['projections'].get('pending',0):break
        else:raise RuntimeError('ingestion_not_current')
        rows=chat.memories()['items']
        assert any(r['key']=='communication.style' and r['content'].startswith('لا،') and r['revision']==2 for r in rows)
        cases=[('arabic_fact_english_query','Which city did I tell you I live in? Please reply in English.',
                lambda a:bool(re.search(r'Tanta|طنطا',a,re.I))),
            ('distinctive_decision_without_project_assignment','Why did we choose Mem0? Please reply in English.',
                lambda a:'mem0' in a.casefold() and bool(re.search(r'multilingual|consolidat',a,re.I)) and 'sqlite' not in a.casefold()),
            ('global_language_and_correction','فاكر أنا بحب تكلمني إزاي؟',
                lambda a:bool(re.search(r'مختصر|موجز|باختصار|الموضوع على طول|مباشر',a)) and bool(re.search(r'مصري|مصرية|بالمصري',a))),
            ('conditional_technical_documentation','Write one sentence of technical documentation about a local memory ledger.',
                lambda a:len(re.findall(r'[a-z]',a,re.I))>len(re.findall(r'[\u0621-\u064a]',a))),
            ('ordinary_chat_keeps_global_language','اكتبلي جملة عن معنى الذاكرة.',
                lambda a:len(re.findall(r'[\u0621-\u064a]',a))>len(re.findall(r'[a-z]',a,re.I))),
            ('current_explicit_language_override','Explain the ledger. Please reply in English.',
                lambda a:len(re.findall(r'[a-z]',a,re.I))>len(re.findall(r'[\u0621-\u064a]',a)))]
        if args.profile_queries:
            from evaluate_cognitive_memory import has_concepts
            corpus=json.loads((Path(__file__).parents[1]/'evals/cognitive-corpus.json').read_text())
            cases.extend((query['id'],query['question'],lambda a,c=query['concepts']:has_concepts(a,c))
                         for query in corpus['queries'] if query['family']=='preference')
        for name,question,check in cases:
            cid=chat.create('Synthetic held-out personalization')['id']
            actual=respond(store,cid,uuid.uuid4().hex,question)
            answers.append({'case':name,'question':question,'actual_answer':actual['answer'],
                'mode':actual['mode'],'sources':actual.get('context_sources',[]),
                'passed':actual['mode']=='pinned_local_ollama' and check(actual['answer'])})
            print(json.dumps(answers[-1],ensure_ascii=False),flush=True)
        with store.connect() as db:
            integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
        report={'synthetic_only':True,'source_assistant_mode':'fixture_archive; never scored as model output',
            'real_extraction_and_projection':True,'source_turns':len(sources),'actual_answers':answers,
            'correction_same_id_revision_2':True,'integrity_check':integrity,
            'all_passed':all(r['passed'] for r in answers)}
        (args.state/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        if not report['all_passed']:raise RuntimeError('real_personalization_acceptance_failed')
    finally:worker.stop()


if __name__=='__main__':main()
