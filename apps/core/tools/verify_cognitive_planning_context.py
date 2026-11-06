#!/usr/bin/env python3
"""Real local Tasks/Calendar evidence combined with cross-chat project memory."""
import argparse
from datetime import datetime,timedelta
import json
import os
from pathlib import Path
import subprocess
import uuid
from zoneinfo import ZoneInfo

from okal_core.intelligence import Intelligence,respond
from okal_core.local_calendar import LocalCalendar
from okal_core.mail.private import write_private
from okal_core.store import Store
from okal_core.task_planner import TaskPlanner


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    args=parser.parse_args()
    if not args.state.is_absolute() or args.state.exists() or 'okal-core' in args.state.parts:
        parser.error('fresh private synthetic state required')
    os.umask(0o077);args.state.mkdir(parents=True,mode=0o700)
    config=json.loads(args.config.read_text())
    write_private(args.state/'mail/config.json',{'account':'planning-context@example.test',
        'model':config['llm']['name'],'model_digest':config['llm']['digest'],
        'local_only_confirmed':True,'sync_enabled':False,'send_enabled':False,'trash_enabled':False,
        'daily_at':None,'notify_new_mail':False})
    store=Store(args.state);chat=Intelligence(store)
    project=chat.cognitive.save_project('Cedar workshop','A synthetic wooden clock project.')
    source=chat.create('Synthetic project source')['id'];chat.cognitive.associate(source,project['id'])
    memory=chat.cognitive.save('project.goal','Our goal is a wooden clock prototype.',kind='goal',project_id=project['id'])
    now=datetime.now(ZoneInfo('Africa/Cairo'));when=(now+timedelta(days=1)).replace(hour=14,minute=0,second=0,microsecond=0)
    task=TaskPlanner(store).create('Cedar workshop: inspect gears',notes='Synthetic task code TC-241.',due=when.isoformat())
    LocalCalendar(store).save({'id':uuid.uuid4().hex,'revision':0,'kind':'event',
        'title':'Cedar workshop design review','notes':'Synthetic event code CE-551.',
        'start':when.isoformat(),'end':(when+timedelta(hours=1)).isoformat(),
        'target_date':None,'reminder_minutes':None})
    original_tasks=TaskPlanner(store).list()['items'];original_events=LocalCalendar(store).list()['items']
    answers=[]
    for question in [
        'Continue Cedar workshop. Which locally saved task and calendar event are available? Include both fixture codes. Please reply in English.',
        'نكمل Cedar workshop. فكرني بالمهمة والموعد المحفوظين محليا، واذكر كود كل واحد.']:
        cid=chat.create('Synthetic planning continuation')['id'];chat.cognitive.associate(cid,project['id'])
        actual=respond(store,cid,uuid.uuid4().hex,question)
        normalized=actual['answer'].translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'))
        date_time_correct=when.date().isoformat() in normalized and '14:00' in normalized
        passed=(actual['mode']=='pinned_local_ollama' and date_time_correct and all(code in actual['answer'] for code in ('TC-241','CE-551'))
                and memory['id'] in {r['id'] for r in actual.get('context_sources',[])})
        answers.append({'question':question,'actual_answer':actual['answer'],'mode':actual['mode'],
            'sources':actual.get('context_sources',[]),'date_time_correct':date_time_correct,'passed':passed})
    tasks=TaskPlanner(store).list()['items'];events=LocalCalendar(store).list()['items']
    assert len(tasks)==len(events)==1 and tasks[0]['id']==task['task_id'] and tasks[0]['status']==events[0]['status']=='open'
    assert tasks==original_tasks and events==original_events
    with store.connect() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    report={'synthetic_only':True,'source_head':subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip(),
        'source_clean':not subprocess.run(['git','status','--porcelain'],capture_output=True,text=True,check=True).stdout.strip(),
        'expected_date_time':when.strftime('%Y-%m-%d %H:%M'),
        'real_local_task_and_event_storage':True,'actual_answers':answers,
        'project_memory_and_planning_snapshot_combined':all(a['passed'] for a in answers),
        'task_and_calendar_unchanged_by_chat':True,'external_provider_mutations':False,'integrity_check':'ok',
        'scope':'Project-qualified saved titles/notes plus stable project memory; no new automatic provider-side project tagging.'}
    (args.state/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
    if not all(a['passed'] for a in answers):raise RuntimeError('planning_context_acceptance_failed')


if __name__=='__main__':main()
