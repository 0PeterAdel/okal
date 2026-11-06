#!/usr/bin/env python3
"""Kill an isolated extraction parent; recover the real durable job after lease expiry."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
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
    args=parser.parse_args()
    if not args.state.is_absolute() or args.state.exists() or 'okal-core' in args.state.parts:
        parser.error('fresh private synthetic state required')
    os.umask(0o077);args.state.mkdir(parents=True,mode=0o700)
    config=json.loads(args.config.read_text());write_private(args.state/'cognitive.json',config)
    write_private(args.state/'mail/config.json',{'account':'crash-evaluation@example.test',
        'owner_name':'Synthetic Owner','model':config['llm']['name'],'model_digest':config['llm']['digest'],
        'local_only_confirmed':True,'sync_enabled':False,'send_enabled':False,'trash_enabled':False,
        'daily_at':None,'notify_new_mail':False})
    store=Store(args.state);chat=Intelligence(store)
    con=chat.create('Synthetic process interruption')['id']
    response=respond(store,con,uuid.uuid4().hex,'Always answer in Egyptian Arabic unless I ask for English.')
    assert response['mode']=='pinned_local_ollama','real_initial_chat_unavailable'
    code='''from pathlib import Path
import sys
from okal_core.store import Store
from okal_core.cognitive.service import MemoryWorker
w=MemoryWorker(Store(Path(sys.argv[1])))
try:w.tick()
finally:w.stop()
'''
    process=subprocess.Popen([sys.executable,'-c',code,str(args.state)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for attempt in range(100):
            with store.connect() as db:
                job=dict(db.execute('SELECT * FROM memory_jobs WHERE turn_id=?',(response['turn_id'],)).fetchone())
            if job['status']=='running':break
            if process.poll() is not None:raise RuntimeError('worker_exited_before_crash_probe')
            time.sleep(.1)
        else:raise RuntimeError('worker_did_not_claim_job')
        process.send_signal(signal.SIGKILL);process.wait(timeout=10)
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=10)
    restarted=MemoryWorker(Store(args.state))
    with restarted.store.connect() as db:
        durable=dict(db.execute('SELECT * FROM memory_jobs WHERE turn_id=?',(response['turn_id'],)).fetchone())
    assert durable['status']=='running' and durable['lease']==job['lease']
    restarted.tick()
    with restarted.store.connect() as db:
        assert db.execute('SELECT lease FROM memory_jobs WHERE turn_id=?',(response['turn_id'],)).fetchone()[0]==job['lease']
    print(json.dumps({'phase':'waiting_for_real_lease_expiry','lease_seconds_remaining':max(0,job['lease_until']-time.time())}),flush=True)
    deadline=time.monotonic()+240
    try:
        while time.monotonic()<deadline:
            restarted.tick();health=restarted.ledger.health()
            if health['jobs'].get('done')==1 and health['projections'].get('current')==1:break
            time.sleep(2)
        else:raise RuntimeError('crash_recovery_deadline')
        with restarted.store.connect() as db:
            recovered=dict(db.execute('SELECT * FROM memory_jobs WHERE turn_id=?',(response['turn_id'],)).fetchone())
            count=db.execute("SELECT COUNT(*) FROM chat_memories WHERE key='communication.language'").fetchone()[0]
            integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert recovered['status']=='done' and recovered['attempts']==2 and count==1 and integrity=='ok'
        assert restarted.ledger.backfill()['enqueued']==0
        report={'synthetic_only':True,'real_initial_chat':True,'parent_sigkill_while_job_running':True,
            'unexpired_lease_not_stolen':True,'real_wall_clock_lease_recovery':True,
            'recovered_job_status':recovered['status'],'attempts':recovered['attempts'],
            'current_memory_records':count,'index_current':True,'vault_current':True,
            'idempotent_backfill':True,'integrity_check':integrity,'foreign_key_violations':0}
        (args.state/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)
    finally:restarted.stop()


if __name__=='__main__':main()
