"""Opt-in real Ollama benchmark. Synthetic inputs; never touches owner state.

PYTHONPATH=apps/core/src python apps/core/tools/intelligence_acceptance.py
"""
import json
from pathlib import Path
import tempfile
import re
import time
import uuid

from okal_core.intelligence import Intelligence, respond
from okal_core.mail.private import write_private
from okal_core.store import Store


def main():
    with tempfile.TemporaryDirectory() as directory:
        store=Store(Path(directory)/'state')
        write_private(store.directory/'mail'/'config.json', {
            'account':'synthetic@example.test','model':'qwen3.5:4b',
            'model_digest':'d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04',
            'local_only_confirmed':True})
        state=Intelligence(store); con=state.create()['id']; results=[]
        def turn(name,message,expected=None,model=True):
            started=time.monotonic()
            result=respond(store,con,uuid.uuid4().hex,message)
            passed=(expected is None or expected.casefold() in result['answer'].casefold())
            passed=passed and (not model or result['mode']=='pinned_local_ollama')
            if model and not re.search(r'[\u0600-\u06ff]',message):
                passed=passed and not re.search(r'[\u0600-\u06ff]',result['answer'])
            results.append({'case':name,'seconds':round(time.monotonic()-started,2),
                'passed':passed,'mode':result['mode'],'answer':result['answer']})
            print(json.dumps(results[-1],ensure_ascii=False),flush=True)
            return result
        turn('explicit_english_save','remember project: Zephyr',model=False)
        turn('english_recall','What project did I ask you to remember?', 'Zephyr')
        turn('english_followup','Spell its name again, please.', 'Zephyr')
        turn('explicit_arabic_save','افتكر اللون: بنفسجي',model=False)
        turn('arabic_recall','إيه اللون اللي طلبت منك تفتكره؟', 'بنفسجي')
        memory=next(m for m in state.memories()['items'] if m['key']=='project')
        state.save_memory('project','Orion',revision=memory['revision'])
        turn('corrected_memory','What project is saved now?', 'Orion')
        state.forget(memory['id'])
        result=turn('forgotten_memory','What project is saved now?')
        assert 'Zephyr' not in result['answer'] and 'Orion' not in result['answer'], 'forgotten data leaked'
        # Exercise a genuine local verification failure, then retry the same
        # durable request after restoring the synthetic pinned configuration.
        config_path=store.directory/'mail'/'config.json'
        config=json.loads(config_path.read_text()); good_digest=config['model_digest']
        config['model_digest']='0'*64; write_private(config_path,config)
        request_id=uuid.uuid4().hex
        failed=respond(store,con,request_id,'Say hello in English.')
        assert failed['mode']=='saved_fallback', 'unverified model used'
        config['model_digest']=good_digest; write_private(config_path,config)
        recovered=respond(store,con,request_id,'Say hello in English.',retry=True)
        assert recovered['mode']=='pinned_local_ollama'
        assert recovered['turn_id']==failed['turn_id'], 'duplicate retry turn'
        results.extend([{'case':'real_verification_failure','passed':True},
                        {'case':'real_failure_recovery_same_id','passed':True}])
        # Re-open the state through a fresh Store to simulate application restart.
        reopened=Intelligence(Store(store.directory))
        assert reopened.get(con)['turns'], 'restart persistence failed'
        assert all(r['passed'] for r in results), 'real-model benchmark failed'
        print(json.dumps({'passed':len(results),'total':len(results)},ensure_ascii=False))


if __name__=='__main__':
    main()
