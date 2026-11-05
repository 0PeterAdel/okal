#!/usr/bin/env python3
"""Rehearse schema migration and backup rollback with synthetic old-Core data.

Never opens Production state. The baseline source is read-only; a subprocess
uses it to write a fresh synthetic database and later verify a restored backup.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from okal_core.intelligence import Intelligence
from okal_core.store import Store


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--baseline-source',type=Path,required=True)
    args=parser.parse_args()
    if (not args.state.is_absolute() or args.state.exists() or 'okal-core' in args.state.parts
            or not (args.baseline_source/'okal_core/intelligence.py').is_file()):
        parser.error('fresh isolated state and existing old-Core source required')
    os.umask(0o077);args.state.mkdir(parents=True,mode=0o700)
    original=args.state/'migrated';original.mkdir(mode=0o700)
    restored=args.state/'restored';restored.mkdir(mode=0o700)
    baseline_env=dict(os.environ,PYTHONPATH=str(args.baseline_source),PYTHONDONTWRITEBYTECODE='1')
    create='''
from pathlib import Path
import json,sys,uuid
from okal_core.store import Store
from okal_core.intelligence import Intelligence
store=Store(Path(sys.argv[1])); chat=Intelligence(store)
cid=chat.create('Synthetic pre-migration bilingual archive')['id']
for i in range(100):
 message=('Always answer in English.' if i==0 else 'Always answer in Egyptian Arabic.' if i==1
          else 'Synthetic owner turn '+str(i)+' / محادثة اختبار فقط')
 claim=chat.begin(cid,uuid.uuid4().hex,message)
 chat.finish(claim['turn_id'],claim['lease'],{'answer':'Synthetic archived answer.','mode':'pinned_local_ollama'})
 if i==0:old_source=claim['turn_id']
memory=chat.save_memory('language','Always answer in English.',kind='semantic',source_turn=old_source,days=30)
chat.save_memory('communication.style','I prefer brief answers.',kind='semantic')
with store.connect() as db:
 assert db.execute('SELECT version FROM chat_schema').fetchone()[0]==1
 assert db.execute('SELECT COUNT(*) FROM chat_turns').fetchone()[0]==100
print(json.dumps({'conversation_id':cid,'memory_id':memory['id'],'expires_at':memory['expires_at']}))
'''
    output=subprocess.run([sys.executable,'-c',create,str(original)],env=baseline_env,
                          capture_output=True,text=True,check=True,timeout=30)
    before=json.loads(output.stdout)
    backup=args.state/'pre-migration.sqlite3'
    with sqlite3.connect(original/'core.sqlite3') as source, sqlite3.connect(backup) as target:
        source.backup(target)
        assert target.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    backup_hash=hashlib.sha256(backup.read_bytes()).hexdigest()
    chat=Intelligence(Store(original))
    with chat.store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM chat_turns').fetchone()[0]==100
        assert db.execute('SELECT COUNT(*) FROM memory_jobs').fetchone()[0]==100
        assert db.execute('SELECT version FROM chat_schema').fetchone()[0]==2
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    assert chat.settings()['retention_days']==0
    records={r['key']:r for r in chat.memories()['items']}
    assert records['communication.language']['expires_at']==before['expires_at']
    assert records['communication.style']['expires_at']==0
    assert chat.cognitive.backfill()['enqueued']==0
    first=chat.cognitive.claim_job()
    chat.cognitive.apply_job(first['turn_id'],first['lease'],[{'key':'communication.language',
        'kind':'instruction','scope':'owner','quote':'Always answer in English.'}])
    later=chat.cognitive.claim_job()
    chat.cognitive.apply_job(later['turn_id'],later['lease'],[{'key':'communication.language',
        'kind':'instruction','scope':'owner','quote':'Always answer in Egyptian Arabic.'}])
    corrected={r['key']:r for r in chat.memories()['items']}['communication.language']
    assert corrected['id']==before['memory_id'] and corrected['content']=='Always answer in Egyptian Arabic.'
    assert chat.cognitive.versions(corrected['id'])['items'][1]['status']=='superseded'
    rejection=subprocess.run([sys.executable,'-c',
        'from pathlib import Path;import sys;from okal_core.store import Store;from okal_core.intelligence import Intelligence;Intelligence(Store(Path(sys.argv[1])))',
        str(original)],env=baseline_env,capture_output=True,text=True,timeout=30)
    assert rejection.returncode!=0 and 'unsupported_chat_schema' in rejection.stderr
    with sqlite3.connect(backup) as source, sqlite3.connect(restored/'core.sqlite3') as target:
        source.backup(target)
    verify='''
from pathlib import Path
import sys
from okal_core.store import Store
from okal_core.intelligence import Intelligence
chat=Intelligence(Store(Path(sys.argv[1])))
with chat.store.connect() as db:
 assert db.execute('SELECT COUNT(*) FROM chat_turns').fetchone()[0]==100
 assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 assert db.execute('SELECT version FROM chat_schema').fetchone()[0]==1
assert chat.settings()['retention_days']==90
print('restored old Core verified')
'''
    subprocess.run([sys.executable,'-c',verify,str(restored)],env=baseline_env,
                   capture_output=True,text=True,check=True,timeout=30)
    assert hashlib.sha256(backup.read_bytes()).hexdigest()==backup_hash
    report={'synthetic_only':True,'turns_preserved':100,'backup_integrity':'ok',
        'migrated_integrity':'ok','foreign_key_violations':0,'source_schema':1,'target_schema':2,
        'retention_default_migrated_to_forever':True,'explicit_finite_memory_expiry_preserved':True,
        'legacy_default_memory_expiry_migrated_to_forever':True,
        'later_archived_correction_supersedes_legacy_source':True,
        'idempotent_backfill':True,'old_code_refuses_new_schema':True,
        'backup_restored_and_old_code_verified':True,'backup_unchanged':True}
    (args.state/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
