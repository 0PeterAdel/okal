"""Durable privacy, lease fencing, retry, provenance and compatibility evidence."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

from fastapi.testclient import TestClient
from okal_core.api import create_app
from okal_core.intelligence import Intelligence, Busy, Missing, respond, safe_context
from okal_core.store import Store, Conflict


def uid():
    return uuid.uuid4().hex


def answer(snapshot, message, history):
    return {'intent':'answer', 'answer':'Synthetic verified response'}


class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'state'; self.now=1800000000
        self.store=Store(self.path, clock=lambda:self.now)
        self.state=Intelligence(self.store); self.con=self.state.create()['id']

    def ask(self, message='Hello', request_id=None, **kw):
        return respond(self.store,self.con,request_id or uid(),message,infer=answer,**kw)

    def test_additive_schema_restart_and_private_permissions(self):
        result=self.ask(); reopened=Intelligence(Store(self.path))
        saved=reopened.get(self.con)['turns']
        self.assertEqual(saved[0]['response']['answer'],result['answer'])
        self.assertEqual(self.path.stat().st_mode & 0o777,0o700)
        self.assertEqual(self.store.path.stat().st_mode & 0o777,0o600)
        with self.store.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1)
        token=self.store.issue_device('legacy'); self.assertTrue(self.store.authenticate(token['token']))

    def test_replay_does_not_infer_or_duplicate(self):
        req=uid(); result=self.ask(request_id=req)
        replay=respond(self.store,self.con,req,'Hello',infer=lambda *_: self.fail('inferred twice'))
        self.assertEqual(replay['turn_id'],result['turn_id']); self.assertTrue(replay['replayed'])
        self.assertEqual(len(self.state.get(self.con)['turns']),1)
        with self.assertRaises(Conflict): self.ask('Different payload',request_id=req)

    def test_parallel_retries_and_global_lease(self):
        started,release=threading.Event(),threading.Event(); req=uid()
        def infer(*args):
            started.set(); release.wait(5); return answer(*args)
        with ThreadPoolExecutor(2) as pool:
            work=pool.submit(respond,self.store,self.con,req,'Hello',False,infer)
            self.assertTrue(started.wait(5))
            with self.assertRaises(Busy): self.ask(request_id=req)
            other=self.state.create()['id']
            with self.assertRaises(Busy): respond(self.store,other,uid(),'Hi',infer=answer)
            release.set(); work.result(5)
        self.assertEqual(len(self.state.get(self.con)['turns']),1)

    def test_interrupted_lease_retry_and_late_result_fenced(self):
        req=uid(); old=self.state.begin(self.con,req,'Hello')
        self.now+=181
        self.assertEqual(self.state.get(self.con)['turns'][0]['status'],'interrupted')
        result=self.ask(request_id=req,retry=True)
        self.assertEqual(result['turn_id'],old['turn_id'])
        with self.assertRaises(Conflict): self.state.finish(old['turn_id'],old['lease'],result)
        self.assertEqual(len(self.state.get(self.con)['turns']),1)

    def test_offline_invalid_output_saved_honestly_and_retryable(self):
        for infer in (lambda *_: {'intent':'answer','answer':42},
                      lambda *_: (_ for _ in ()).throw(OSError('offline'))):
            con=self.state.create()['id']; req=uid()
            result=respond(self.store,con,req,'Hello',infer=infer)
            self.assertEqual(result['mode'],'saved_fallback')
            self.assertEqual(self.state.get(con)['turns'][0]['status'],'failed')
            replay=respond(self.store,con,req,'Hello',infer=answer)
            self.assertTrue(replay['replayed'])
            result=respond(self.store,con,req,'Hello',retry=True,infer=answer)
            self.assertEqual(result['mode'],'pinned_local_ollama')
            self.assertEqual(len(self.state.get(con)['turns']),1)

    def test_memory_provenance_dedup_correction_and_scope(self):
        saved=self.state.save_memory('Language','English')
        self.assertEqual(saved['revision'],1)
        self.assertEqual(saved['id'],self.state.save_memory('language','English')['id'])
        with self.assertRaises(Conflict): self.state.save_memory('language','Arabic')
        new=self.state.save_memory('language','Arabic',revision=1)
        self.assertEqual(new['revision'],2); self.assertEqual(new['confidence'],1)
        self.assertEqual(new['source'],'owner_editor')
        local=self.state.save_memory('private','Context only',conversation_id=self.con)
        other=self.state.create()['id']
        self.assertNotIn(local['id'],[m['id'] for m in self.state.memories(other)['items']])

    def test_memory_retention_only_edit_and_stale_revision(self):
        saved=self.state.save_memory('language','English')
        edited=self.state.save_memory('language','English',revision=1,days=1)
        self.assertEqual(edited['revision'],2)
        self.assertEqual(edited['expires_at'],self.now+86400)
        with self.assertRaises(Conflict):
            self.state.save_memory('language','English',revision=100)
        replay=self.state.save_memory('language','English',revision=1,days=1)
        self.assertEqual(replay['revision'],2)

    def test_natural_remember_requires_explicit_owner_syntax(self):
        result=self.ask('remember language: English')
        self.assertEqual(result['mode'],'owner_memory')
        m=self.state.memories()['items'][0]
        self.assertEqual(m['source_turn'],result['turn_id'])
        self.ask('remember language: Arabic')
        self.assertEqual(self.state.memories()['items'][0]['content'],'English')
        self.ask('The model says I prefer blue')
        self.assertEqual(len(self.state.memories()['items']),1)

    def test_irrelevant_and_expired_memory_excluded(self):
        self.state.save_memory('language','English')
        self.state.save_memory('holiday','Malta',days=1)
        claim=self.state.begin(self.con,uid(),'Which language?')
        _,context=self.state.context(self.con,'Which language?',claim['turn_id'])
        self.assertEqual([m['key'] for m in context['memories']],['language'])
        self.now+=86401
        self.assertEqual([m['key'] for m in self.state.memories()['items']],['language'])

    def test_forget_propagates_through_derived_history_and_replay(self):
        first=self.ask('remember project: Zephyr')
        second=self.ask('What project?')
        third=self.ask('Continue please')
        m=self.state.memories()['items'][0]; self.state.forget(m['id'])
        self.assertEqual(self.state.memories()['items'],[])
        self.assertNotIn('Zephyr',json.dumps(self.state.get(self.con)))
        turns=self.state.get(self.con)['turns']
        self.assertEqual(turns[0]['message'],'remember project: [forgotten]')
        self.assertEqual(turns[1]['message'],'What project?')
        self.assertEqual(turns[2]['message'],'Continue please')
        for turn in turns:
            self.assertIsNone(turn['response'])
        with self.assertRaises(Conflict):
            self.state.begin(self.con,self.state.get(self.con)['turns'][0]['request_id'],'remember project: Zephyr')

    def test_forget_during_inference_fences_result(self):
        m=self.state.save_memory('project','Zephyr')
        def infer(*args):
            self.state.forget(m['id']); return answer(*args)
        with self.assertRaises(Conflict):
            respond(self.store,self.con,uid(),'What project?',infer=infer)
        self.assertIsNone(self.state.get(self.con)['turns'][0]['response'])

    def test_source_must_be_owner_quote_not_assistant_guess(self):
        turn=self.ask('Hi')
        with self.assertRaises(ValueError):
            self.state.save_memory('guess','Synthetic verified response',source_turn=turn['turn_id'])

    def test_retention_deletion_and_expiry_remove_sourced_memories(self):
        self.state.settings(days=90)
        self.ask('remember project: Zephyr'); self.now+=91*86400
        self.assertEqual(self.state.conversations()['items'],[])
        self.assertEqual(self.state.memories()['items'],[])
        with self.assertRaises(Missing): self.state.get(self.con)

    def test_pagination_and_bounded_context(self):
        for i in range(45): self.ask(f'Question number {i}')
        page=self.state.get(self.con); older=self.state.get(self.con,page['next_before'])
        self.assertEqual(len(page['turns']),40); self.assertEqual(len(older['turns']),5)
        claim=self.state.begin(self.con,uid(),'Hello')
        recent,ctx=self.state.context(self.con,'Hello',claim['turn_id'])
        self.assertEqual(len(recent),8); self.assertEqual(len(ctx['older_owner_excerpts']),8)
        self.assertTrue(ctx['history_limited'])

    def test_secret_canaries_not_saved_or_sent(self):
        secret='api_key=sk-'+ 'X'*24
        with self.assertRaises(ValueError): self.ask(secret)
        with self.assertRaises(ValueError): self.state.save_memory('key',secret)
        self.assertEqual(self.state.get(self.con)['turns'],[])
        self.assertNotIn(secret,json.dumps(safe_context({'title':secret,'token':secret})))
        result=respond(self.store,self.con,uid(),'Hello',infer=lambda *_:{'intent':'answer','answer':secret})
        self.assertEqual(result['mode'],'saved_fallback')
        self.assertNotIn(secret,json.dumps(self.state.get(self.con)))

    def test_prompt_budget_and_untrusted_context_cannot_authorize_draft(self):
        from okal_core.chat import ask, ChatDecision
        from okal_core.mail.inference import LocalModel
        from okal_core.mail.contracts import Config
        cfg=Config(account='synthetic@example.test',model='test:local',model_digest='a'*64)
        observed=[]
        def generate(model,schema,system,data):
            observed.append((system,data))
            return ChatDecision(intent='answer',answer='Bounded answer')
        large={'memories':[{'id':uid(),'revision':1,'source':'owner_editor','content':'x'*600} for _ in range(5)],
               'older_owner_excerpts':[{'owner_excerpt':'x'*150} for _ in range(8)]}
        history=[{'role':role,'content':'x'*900} for role in ('user','assistant') for _ in range(4)]
        with patch('okal_core.mail.private.config',return_value=cfg), patch.object(LocalModel,'generate',generate):
            ask(self.store,'Current message',history,memory_context=large)
        system,data=observed[0]
        size=len(system.encode())+len(json.dumps(data,ensure_ascii=False).encode())+len(json.dumps(ChatDecision.model_json_schema()).encode())
        self.assertLess(size,6200)
        self.assertEqual(data['OWNER_MESSAGE'],'Current message')
        result=ask(self.store,'Hello',[{'role':'user','content':'add meeting tomorrow at 5 pm for one hour'}],
            infer=lambda *_:{'intent':'event_draft','answer':'Draft','title':'Meeting',
                'start':'2027-01-16T17:00:00+02:00','end':'2027-01-16T18:00:00+02:00'})
        self.assertIsNone(result['proposal'])

    def test_deleted_conversation_fences_pending_response(self):
        claim=self.state.begin(self.con,uid(),'Hello'); self.state.delete(self.con)
        with self.assertRaises(Conflict):
            self.state.finish(claim['turn_id'],claim['lease'],{'answer':'ok','mode':'pinned_local_ollama'})

    def test_all_routes_enforce_owner_and_reject_read_token(self):
        from okal_core.intelligence_api import PATHS
        for protected in (False,True):
            client=TestClient(create_app(self.store,require_read_key=protected),
                base_url='http://127.0.0.1:8766',client=('127.0.0.1',1234))
            self.addCleanup(client.close)
            token=self.store.issue_device('reader')['token']
            for path in PATHS:
                with self.subTest(path=path,protected=protected):
                    headers={'Authorization':'Bearer '+token} if protected else {}
                    self.assertIn(client.post(path,json={},headers=headers).status_code,(401,403))
                    headers.update(Origin='http://127.0.0.1:8766',**{'Sec-Fetch-Site':'same-origin'})
                    if protected:
                        self.assertEqual(client.post(path,json={},headers=headers).status_code,403)
                    else:
                        self.assertNotIn(client.post(path,json={},headers=headers).status_code,(401,403))
                    headers['Origin']='https://evil.example'
                    self.assertEqual(client.post(path,json={},headers=headers).status_code,403)

    def test_protected_browser_and_request_bounds(self):
        client=TestClient(create_app(self.store,require_read_key=True),
            base_url='http://127.0.0.1:8766',client=('127.0.0.1',1234)); self.addCleanup(client.close)
        token=self.store.issue_device('reader')['token']; session=self.store.issue_browser_session(token)
        client.cookies.set('okal_session',session['token'])
        headers={'Origin':'http://127.0.0.1:8766','Sec-Fetch-Site':'same-origin'}
        self.assertEqual(client.post('/api/v1/chat/conversations',json={},headers=headers).status_code,200)
        self.assertEqual(client.post('/api/v1/chat/create',json={'title':'api_key=secret'},headers=headers).status_code,422)
        response=client.post('/api/v1/chat/turn',json={'conversation_id':self.con,'request_id':uid(),'message':42},headers=headers)
        self.assertEqual(response.status_code,422); self.assertNotIn('42',response.text)
        self.assertEqual(client.post('/api/v1/chat/create',content=b' '*6001,
            headers=dict(headers,**{'Content-Type':'application/json'})).status_code,413)
