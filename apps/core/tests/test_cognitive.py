"""Authoritative lifecycle / privacy tests; no model or provider mocks needed."""
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from okal_core.cognitive.learning import validate_candidates
from okal_core.intelligence import Intelligence, respond
from okal_core.store import Store, Conflict


def uid():
    return uuid.uuid4().hex


def answer(*args):
    return {'intent': 'answer', 'answer': 'A synthetic response.'}


def candidate(quote, key='communication.style', kind='instruction', scope='owner'):
    return {'quote': quote, 'key': key, 'kind': kind, 'scope': scope}


class CognitiveLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = 1_800_000_000
        self.store = Store(Path(self.temp.name) / 'state', clock=lambda: self.now)
        self.chat = Intelligence(self.store)
        self.ledger = self.chat.cognitive
        self.conversation = self.chat.create()['id']

    def tearDown(self):
        self.temp.cleanup()

    def say(self, message):
        return respond(self.store, self.conversation, uid(), message, infer=answer)

    def test_default_lifetime_survives_years_and_restart(self):
        self.say('I prefer brief answers.')
        self.chat.save_memory('communication.style', 'I prefer brief answers.', kind='instruction')
        self.now += 5 * 366 * 86400
        recovered = Intelligence(self.store)
        self.assertEqual(recovered.settings()['retention_days'], 0)
        self.assertEqual(len(recovered.get(self.conversation)['turns']), 1)
        self.assertEqual(len(recovered.memories()['items']), 1)

    def test_sensitive_editor_requires_consent_and_cannot_save_credentials(self):
        with self.assertRaises(ValueError):self.chat.save_memory('health','My medical appointment is monthly.')
        saved=self.chat.save_memory('health','My medical appointment is monthly.',sensitive_confirmed=True)
        self.assertEqual(saved['content'],'My medical appointment is monthly.')
        with self.assertRaises(ValueError):self.chat.save_memory('credential','password=synthetic-secret',sensitive_confirmed=True)
        for key,content in [('login','My password is synthetic-value.'),('api key','synthetic-value'),
                            ('login','كلمة المرور هي قيمة تجريبية')]:
            with self.subTest(key=key):
                with self.assertRaises(ValueError):self.chat.save_memory(key,content,sensitive_confirmed=True)
        with self.assertRaises(ValueError):self.ledger.save_project('Synthetic project','My password is synthetic-value.')
        for secret in ['My password is synthetic-value.','كلمة المرور هي قيمة تجريبية']:
            with self.assertRaises(ValueError):self.say(secret)

    def test_medical_and_financial_candidates_need_explicit_sensitive_editor(self):
        quotes=['I have diabetes.','My allergies include peanuts.','My prescription is private.',
                'My card number is a synthetic identifier.','My passport is a synthetic identifier.',
                'أنا عندي سكري.','أنا عندي حساسية.','أنا باخد دواء يوميا.',
                'رقم حساب بنكي يخصني.','راتبي معلومة خاصة.']
        for quote in quotes:
            with self.subTest(quote=quote):
                self.assertEqual(validate_candidates(quote,[candidate(quote,key='profile.private',kind='semantic')]),[])
                with self.assertRaises(ValueError):self.chat.save_memory('private',quote)
                with self.assertRaises(ValueError):self.ledger.save_project('Private fixture',quote)
        saved=self.chat.save_memory('health','I have diabetes.',sensitive_confirmed=True)
        self.assertEqual(saved['content'],'I have diabetes.')

    def test_correction_preserves_source_history_and_versions(self):
        first = self.say('I prefer detailed answers. My project is a garden.')
        memory = self.chat.save_memory('communication.style', 'I prefer detailed answers.',
                                      kind='instruction', source_turn=first['turn_id'])
        second = self.say('I prefer brief answers.')
        corrected = self.chat.save_memory('communication.style', 'I prefer brief answers.',
            kind='instruction', source_turn=second['turn_id'], revision=memory['revision'])
        self.assertEqual(memory['id'], corrected['id'])
        self.assertIn('My project is a garden.', self.chat.get(self.conversation)['turns'][0]['message'])
        self.assertIn('detailed answers', self.chat.get(self.conversation)['turns'][0]['message'])
        versions = self.ledger.versions(memory['id'])['items']
        self.assertEqual([v['status'] for v in versions], ['current', 'superseded'])
        self.assertEqual(self.ledger.active([{'id': memory['id'], 'revision': 1}]), [])

    def test_forgetting_shared_sentence_fences_other_facets_and_manual_duplicates(self):
        quote='Always answer in Egyptian Arabic and keep replies concise.'
        source=self.say(quote+' This unrelated owner text remains.')
        style=self.chat.save_memory('communication.style',quote,kind='instruction',source_turn=source['turn_id'])
        language=self.chat.save_memory('communication.language',quote,kind='instruction',source_turn=source['turn_id'])
        duplicate=self.chat.save_memory('copied preference',quote)
        independent=self.chat.save_memory('independent','I prefer offline research.')
        self.chat.forget(style['id'])
        self.assertEqual({r['id'] for r in self.chat.memories()['items']},{independent['id']})
        self.assertEqual(self.ledger.active([{'id':r['id'],'revision':1} for r in (style,language,duplicate)]),[])
        self.assertIn('This unrelated owner text remains.',json.dumps(self.chat.get(self.conversation)))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM memory_tombstones').fetchone()[0],3)

    def test_redaction_removes_last_source_support_but_preserves_independent_evidence(self):
        first=self.say('I prefer offline research. I prefer concise replies.')
        compound=self.chat.save_memory('compound','I prefer offline research. I prefer concise replies.',source_turn=first['turn_id'])
        research=self.chat.save_memory('research','I prefer offline research.',source_turn=first['turn_id'])
        style=self.chat.save_memory('communication.style','I prefer concise replies.',source_turn=first['turn_id'])
        other=self.chat.create()['id']
        second=respond(self.store,other,uid(),'I prefer offline research.',infer=answer)
        self.chat.save_memory('research','I prefer offline research.',source_turn=second['turn_id'])
        self.chat.forget(compound['id'])
        self.assertEqual({r['id'] for r in self.chat.memories()['items']},{research['id']})
        self.assertEqual(self.chat.memories()['items'][0]['source_turn'],second['turn_id'])
        self.assertEqual(self.ledger.active([{'id':style['id'],'revision':1}]),[])
        self.assertIn('I prefer offline research.',json.dumps(self.chat.get(other)))

    def test_forgetting_shared_old_quote_redacts_other_memory_history_not_its_independent_correction(self):
        quote='Always answer in Egyptian Arabic and keep replies concise.'
        source=self.say(quote)
        style=self.chat.save_memory('communication.style',quote,kind='instruction',source_turn=source['turn_id'])
        language=self.chat.save_memory('communication.language',quote,kind='instruction',source_turn=source['turn_id'])
        self.chat.save_memory('communication.language','Always answer in Egyptian Arabic.',kind='instruction',revision=1)
        self.chat.forget(style['id'])
        self.assertEqual({r['id'] for r in self.chat.memories()['items']},{language['id']})
        history=self.ledger.versions(language['id'])
        self.assertNotIn('concise',json.dumps(history))
        self.assertIsNone(history['items'][1]['snapshot'])

    def test_forgetting_removes_all_versions_and_preserves_unrelated_source_span(self):
        turn = self.say('I prefer detailed answers. My project is a garden.')
        memory = self.chat.save_memory('communication.style', 'I prefer detailed answers.',
                                      source_turn=turn['turn_id'])
        self.chat.save_memory('communication.style', 'I prefer brief answers.', revision=1)
        self.chat.forget(memory['id'])
        rendered = json.dumps(self.chat.get(self.conversation))
        self.assertNotIn('detailed answers', rendered)
        self.assertIn('My project is a garden.', rendered)
        self.assertTrue(all(v['snapshot'] is None for v in self.ledger.versions(memory['id'])['items']))
        self.assertEqual(self.ledger.active([{'id': memory['id'], 'revision': 2}]), [])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT operation FROM memory_outbox WHERE memory_id=?',
                                        (memory['id'],)).fetchone()[0], 'delete')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM memory_fts').fetchone()[0], 0)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_correction_fences_inflight_response(self):
        memory = self.chat.save_memory('subject', 'garden')
        claim = self.chat.begin(self.conversation, uid(), 'Which subject garden?')
        self.chat.context(self.conversation, 'Which subject garden?', claim['turn_id'])
        self.chat.save_memory('subject', 'observatory', revision=memory['revision'])
        with self.assertRaises(Conflict):
            self.chat.finish(claim['turn_id'], claim['lease'], {'answer': 'garden', 'mode': 'owner_memory'})

    def test_job_commit_idempotence_and_restart(self):
        self.say('I prefer concise answers.')
        claim = self.ledger.claim_job()
        self.assertIsNotNone(claim)
        self.assertIsNone(self.ledger.claim_job())
        self.now += 141
        recovered = Intelligence(self.store).cognitive
        retry = recovered.claim_job()
        self.assertNotEqual(retry['lease'], claim['lease'])
        with self.assertRaises(Conflict):
            recovered.apply_job(claim['turn_id'], claim['lease'], [candidate('I prefer concise answers.')])
        recovered.apply_job(retry['turn_id'], retry['lease'], [candidate('I prefer concise answers.')])
        self.assertIsNone(recovered.claim_job())
        self.assertEqual(recovered.backfill()['enqueued'], 0)
        self.assertEqual(len(self.chat.memories()['items']), 1)
        self.assertEqual(recovered.health()['jobs'], {'done': 1})

    def test_project_goal_cannot_supersede_current_architecture_decision(self):
        project=self.ledger.save_project('Synthetic typed subjects')
        self.ledger.associate(self.conversation,project['id'])
        choice='For this project, we use PostgreSQL because several devices write concurrently.'
        self.say(choice);job=self.ledger.claim_job()
        self.ledger.apply_job(job['turn_id'],job['lease'],[candidate(choice,'architecture.database','decision','project')])
        goal='For this project, our goal is a recoverable migration.'
        self.say(goal);job=self.ledger.claim_job()
        # Reproduces the actual local model reusing the last decision key.
        self.ledger.apply_job(job['turn_id'],job['lease'],[candidate(goal,'architecture.database','decision','project')])
        records={r['key']:r for r in self.chat.memories(project_id=project['id'])['items']}
        self.assertEqual(records['architecture.database']['content'],choice)
        self.assertEqual(records['architecture.database']['revision'],1)
        self.assertEqual(records['project.goal']['content'],goal)
        self.assertEqual(records['project.goal']['kind'],'goal')
        normalized=validate_candidates(goal,[candidate(goal,'architecture.database','semantic','owner')],project['id'])
        self.assertEqual((normalized[0]['scope'],normalized[0]['key']),('project','project.goal'))

    def test_automatic_cross_kind_subject_collision_defers_without_overwriting(self):
        from okal_core.cognitive.ledger import CandidateConflict
        quote='We chose SQLite for offline use.'
        old=self.chat.save_memory('architecture.database',quote,kind='decision')
        constraint='We require a local-only workflow.'
        self.say(constraint);job=self.ledger.claim_job()
        with self.assertRaises(CandidateConflict):
            self.ledger.apply_job(job['turn_id'],job['lease'],[candidate(constraint,'architecture.database','constraint')])
        self.ledger.fail_job(job['turn_id'],job['lease'],'candidate_subject_conflict')
        self.assertEqual(self.chat.memories()['items'][0]['content'],quote)
        self.assertEqual(self.ledger.active([{'id':old['id'],'revision':1}])[0]['content'],quote)
        with self.store.connect() as db:
            status,error=db.execute('SELECT status,error FROM memory_jobs WHERE turn_id=?',(job['turn_id'],)).fetchone()
            self.assertEqual((status,error),('pending','candidate_subject_conflict'))
        # Explicit owner editor correction remains available and authoritative.
        changed=self.chat.save_memory('architecture.database',constraint,kind='constraint',revision=1)
        self.assertEqual(changed['revision'],2)

    def test_distinct_preferences_survive_model_reuse_of_same_semantic_key(self):
        first='My preferred release test phrase is cedar ibis 126.'
        second='My preferred synthetic review label is jade finch 126.'
        for quote in (first,second):
            self.say(quote);job=self.ledger.claim_job()
            self.ledger.apply_job(job['turn_id'],job['lease'],[candidate(quote,'readiness.phrase','semantic')])
        records=self.chat.memories()['items']
        self.assertEqual({r['content'] for r in records},{first,second})
        self.assertEqual(len(records),2)
        # Same field, different model key: a genuine current-value correction.
        changed='My preferred release test phrase is cedar ibis 127.'
        self.say(changed);job=self.ledger.claim_job()
        self.ledger.apply_job(job['turn_id'],job['lease'],[candidate(changed,'different.model.label','semantic')])
        current=self.chat.memories()['items']
        self.assertEqual({r['content'] for r in current},{changed,second})
        revised=next(r for r in current if r['content']==changed)
        self.assertEqual(revised['revision'],2)
        self.assertEqual(revised['id'],next(r['id'] for r in records if r['content']==first))

    def test_literal_preference_survives_instruction_semantic_model_kind_change(self):
        first='My preferred deployment symbol is amber kestrel 128.'
        second='My preferred deployment symbol is amber kestrel 129.'
        self.say(first);job=self.ledger.claim_job()
        self.ledger.apply_job(job['turn_id'],job['lease'],[candidate(first,'architecture.symbol','instruction')])
        old=self.chat.memories()['items'][0]
        self.say(second);job=self.ledger.claim_job()
        self.ledger.apply_job(job['turn_id'],job['lease'],[candidate(second,'another.model.key','semantic')])
        current=self.chat.memories()['items']
        self.assertEqual(len(current),1)
        self.assertEqual((current[0]['id'],current[0]['revision'],current[0]['content']),
                         (old['id'],2,second))

    def test_existing_instruction_field_anchor_repair_preserves_owner_revision(self):
        first='My preferred deployment symbol is amber kestrel 128.'
        old=self.chat.save_memory('architecture.symbol',first,kind='instruction')
        with self.store.connect() as db, db:
            db.execute('UPDATE memory_meta SET subject_anchor=NULL WHERE memory_id=?',(old['id'],))
        self.ledger=Intelligence(self.store).cognitive
        repaired=self.chat.memories()['items'][0]
        self.assertEqual((repaired['id'],repaired['key'],repaired['revision'],repaired['content']),
                         (old['id'],old['key'],old['revision'],old['content']))
        second='My preferred deployment symbol is amber kestrel 129.'
        self.say(second);job=self.ledger.claim_job()
        self.ledger.apply_job(job['turn_id'],job['lease'],[candidate(second,'model.changed.key','semantic')])
        current=self.chat.memories()['items'][0]
        self.assertEqual((current['id'],current['key'],current['revision'],current['content']),
                         (old['id'],'architecture.symbol',2,second))

    def test_instruction_field_tombstone_rejects_old_semantic_job(self):
        first='My preferred editor is Vim.'
        self.say(first)
        saved=self.chat.save_memory('owner editor key','My preferred editor is Neovim.',kind='instruction')
        self.chat.forget(saved['id'])
        job=self.ledger.claim_job()
        self.ledger.apply_job(job['turn_id'],job['lease'],[candidate(first,'different.model.key','semantic')])
        self.assertEqual(self.chat.memories()['items'],[])

    def test_ambiguous_same_kind_collision_is_visible_and_preserves_existing_fact(self):
        from okal_core.cognitive.ledger import CandidateConflict
        saved=self.chat.save_memory('architecture.component','We selected Mem0 for personalization.',kind='decision')
        quote='We selected a weekly meeting schedule.'
        self.say(quote);job=self.ledger.claim_job()
        with self.assertRaises(CandidateConflict):
            self.ledger.apply_job(job['turn_id'],job['lease'],[candidate(quote,'architecture.component','decision')])
        self.ledger.fail_job(job['turn_id'],job['lease'],'candidate_subject_conflict')
        self.assertEqual(self.ledger.health()['deferred_subjects'],1)
        self.assertEqual(self.ledger.active([{'id':saved['id'],'revision':1}])[0]['content'],saved['content'])

    def test_pre_anchor_schema_and_owner_editor_key_preserve_identity(self):
        original=self.chat.save_memory('owner chosen label','My preferred editor is Vim.')
        with self.store.connect() as db, db:
            db.execute('DROP INDEX memory_subject_anchor')
            db.execute('ALTER TABLE memory_meta DROP COLUMN subject_anchor')
        self.ledger=Intelligence(self.store).cognitive
        quote='My preferred editor is Neovim.'
        self.say(quote);job=self.ledger.claim_job()
        self.ledger.apply_job(job['turn_id'],job['lease'],[candidate(quote,'unreliable.model.label','semantic')])
        revised=self.chat.memories()['items'][0]
        self.assertEqual((revised['id'],revised['key'],revised['revision']),(original['id'],'owner chosen label',2))

    def test_anchor_tombstone_fences_old_jobs_using_another_model_key(self):
        old='My preferred editor is Vim.'
        newer='My preferred editor is Neovim.'
        self.say(old)
        current=self.chat.save_memory('owner editor key',newer)
        self.chat.forget(current['id'])
        # The older source uses another value and key; neither may resurrect
        # the forgotten preference through delayed backfill.
        job=self.ledger.claim_job()
        self.ledger.apply_job(job['turn_id'],job['lease'],[candidate(old,'different.model.key','semantic')])
        self.assertEqual(self.chat.memories()['items'],[])

    def test_conversation_only_identity_does_not_change_global_profile(self):
        quote='In this conversation, my name is Local Canary.'
        proposed=validate_candidates(quote,[candidate(quote,'profile.name','semantic','owner')])
        self.assertEqual(proposed[0]['scope'],'conversation')

    def test_reserved_slots_require_owner_evidence_not_a_model_label(self):
        quote='My preferred review label is jade finch.'
        for key,kind in [('profile.name','semantic'),('project.goal','goal'),('conversation.pending_work','task')]:
            with self.subTest(key=key):
                self.assertEqual(validate_candidates(quote,[candidate(quote,key,kind)],'1'*32),[])

    def test_learning_correction_same_slot(self):
        for quote in ['I prefer detailed answers.', 'لا، أنا عايز ردودك مختصرة وتدخل في الموضوع على طول.']:
            self.say(quote)
            job = self.ledger.claim_job()
            self.ledger.apply_job(job['turn_id'], job['lease'], [candidate(quote)])
            self.now += 1
        memories = self.chat.memories()['items']
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]['revision'], 2)
        self.assertIn('مختصرة', memories[0]['content'])

    def test_concurrent_owner_edit_at_same_timestamp_is_not_overwritten(self):
        self.say('I prefer brief answers.')
        claim = self.ledger.claim_job()
        self.chat.save_memory('communication.style', 'I prefer detailed answers.', kind='instruction')
        with self.assertRaises(Conflict):
            self.ledger.apply_job(claim['turn_id'], claim['lease'], [candidate('I prefer brief answers.')])
        self.assertIn('detailed', self.chat.memories()['items'][0]['content'])

    def test_queued_turn_order_survives_out_of_order_retry(self):
        first = self.say('I prefer detailed answers.')
        second = self.say('I prefer brief answers.')
        claim = self.ledger.claim_job()
        self.ledger.fail_job(claim['turn_id'], claim['lease'])
        newer = self.ledger.claim_job()
        self.assertEqual(newer['turn_id'], second['turn_id'])
        self.ledger.apply_job(newer['turn_id'], newer['lease'], [candidate('I prefer brief answers.')])
        self.now += 61
        older = self.ledger.claim_job()
        self.assertEqual(older['turn_id'], first['turn_id'])
        self.ledger.apply_job(older['turn_id'], older['lease'], [candidate('I prefer detailed answers.')])
        self.assertEqual(self.chat.memories()['items'][0]['content'], 'I prefer brief answers.')

    def test_association_change_during_extraction_is_fenced(self):
        project = self.ledger.save_project('Garden')
        self.say('We chose a local database for the project.')
        claim = self.ledger.claim_job()
        self.ledger.associate(self.conversation, project['id'])
        with self.assertRaises(Conflict):
            self.ledger.apply_job(claim['turn_id'], claim['lease'], [])

    def test_bad_candidate_batch_rolls_back(self):
        self.say('I prefer concise answers.')
        claim = self.ledger.claim_job()
        with self.assertRaises(ValueError):
            self.ledger.apply_job(claim['turn_id'], claim['lease'],
                [candidate('I prefer concise answers.'), {'quote': 'bad'}])
        self.assertEqual(self.chat.memories()['items'], [])
        self.assertEqual(self.ledger.health()['jobs'], {'running': 1})

    def test_forget_during_extraction_cannot_commit_late_candidates(self):
        turn = self.say('I prefer concise answers.')
        saved = self.chat.save_memory('communication.style', 'I prefer concise answers.', source_turn=turn['turn_id'])
        claim = self.ledger.claim_job()
        self.chat.forget(saved['id'])
        with self.assertRaises(Conflict):
            self.ledger.apply_job(claim['turn_id'], claim['lease'], [candidate('I prefer concise answers.')])
        self.assertEqual(self.chat.memories()['items'], [])
        self.assertEqual(self.ledger.backfill()['enqueued'], 0)

    def test_jobs_yield_to_chat_and_have_bounded_retries(self):
        self.say('I prefer concise answers.')
        claim = self.chat.begin(self.conversation, uid(), 'Hello')
        self.assertIsNone(self.ledger.claim_job())
        self.chat.finish(claim['turn_id'], claim['lease'], {'answer': 'Hello', 'mode': 'owner_memory'})
        for _ in range(5):
            job = self.ledger.claim_job()
            self.ledger.fail_job(job['turn_id'], job['lease'])
            self.now += 61
        self.assertEqual(self.ledger.health()['jobs'].get('failed'), 1)

    def test_projects_use_stable_explicit_associations_and_cas(self):
        garden = self.ledger.save_project('Orion garden')
        satellite = self.ledger.save_project('Orion satellite')
        result = self.ledger.associate(self.conversation, garden['id'])
        self.assertEqual(self.ledger.conversation_state(self.conversation)['project_id'], garden['id'])
        with self.assertRaises(Conflict):
            self.ledger.associate(self.conversation, satellite['id'])
        self.ledger.associate(self.conversation, satellite['id'], revision=result['revision'])
        with self.assertRaises(Conflict):
            self.ledger.save_project('ORION GARDEN')

    def test_project_candidates_cannot_create_associations(self):
        quote = 'We chose a local database for the project.'
        self.say(quote)
        claim = self.ledger.claim_job()
        self.ledger.apply_job(claim['turn_id'], claim['lease'], [candidate(quote, 'database', 'decision', 'project')])
        self.assertEqual(self.chat.memories()['items'], [])
        self.assertIsNone(self.ledger.conversation_state(self.conversation)['project_id'])

    def test_delete_history_removes_jobs_and_sourced_memory(self):
        self.say('I prefer concise answers.')
        job = self.ledger.claim_job()
        self.ledger.apply_job(job['turn_id'], job['lease'], [candidate('I prefer concise answers.')])
        self.chat.delete(self.conversation)
        self.assertEqual(self.chat.memories()['items'], [])
        self.assertEqual(self.ledger.health()['jobs'], {})
        self.assertEqual(self.ledger.health()['deleted'], 1)

    def test_forgotten_subject_cannot_return_from_old_unrelated_chat_backfill(self):
        old = self.say('I prefer brief answers.')
        self.conversation = self.chat.create()['id']
        latest = self.say('I prefer concise answers.')
        memory = self.chat.save_memory('communication.style','I prefer concise answers.',source_turn=latest['turn_id'])
        self.chat.forget(memory['id'])
        job = self.ledger.claim_job()
        self.assertEqual(job['turn_id'], old['turn_id'])
        self.ledger.apply_job(job['turn_id'],job['lease'],[candidate('I prefer brief answers.')])
        self.assertEqual(self.chat.memories()['items'],[])
        # A genuinely new explicit statement after forgetting is new evidence.
        self.conversation = self.chat.create()['id']
        self.say('I prefer detailed answers.')
        job = self.ledger.claim_job()
        self.ledger.apply_job(job['turn_id'],job['lease'],[candidate('I prefer detailed answers.')])
        self.assertEqual(self.chat.memories()['items'][0]['content'],'I prefer detailed answers.')

    def test_delete_old_source_erases_its_snapshot_but_preserves_later_correction(self):
        old_conversation = self.conversation
        first = self.say('I prefer detailed answers.')
        memory = self.chat.save_memory('communication.style','I prefer detailed answers.',source_turn=first['turn_id'])
        self.conversation = self.chat.create()['id']
        second = self.say('I prefer brief answers.')
        self.chat.save_memory('communication.style','I prefer brief answers.',revision=1,source_turn=second['turn_id'])
        self.chat.delete(old_conversation)
        versions = self.ledger.versions(memory['id'])['items']
        self.assertEqual(versions[1]['status'],'deleted')
        self.assertIsNone(versions[1]['snapshot'])
        self.assertEqual(self.chat.memories()['items'][0]['content'],'I prefer brief answers.')

    def test_deleting_one_chat_keeps_fact_with_independent_owner_reaffirmation(self):
        original=self.conversation
        first=self.say('I prefer brief answers.')
        saved=self.chat.save_memory('communication.style','I prefer brief answers.',source_turn=first['turn_id'])
        self.conversation=self.chat.create()['id']
        second=self.say('I prefer brief answers.')
        replay=self.chat.save_memory('communication.style','I prefer brief answers.',source_turn=second['turn_id'])
        self.assertEqual(replay['id'],saved['id'])
        self.chat.delete(original)
        current=self.chat.memories()['items'][0]
        self.assertEqual(current['source_turn'],second['turn_id'])
        self.assertEqual(current['revision'],2)
        self.assertEqual(self.ledger.health()['deleted'],0)
        self.chat.forget(current['id'])
        self.assertNotIn('brief answers',json.dumps(self.chat.get(self.conversation)))


class EvidenceGateTests(unittest.TestCase):
    def test_explicit_name_is_not_lost_when_model_omits_one_sentence(self):
        from types import SimpleNamespace
        from okal_core.cognitive.learning import extract
        model=SimpleNamespace(llm=SimpleNamespace(generate_response=lambda *a,**k:'{"candidates":[]}'))
        for quote in ['My name is Mira.','اسمي ميرا.']:
            result=extract(model,'In this conversation my goal is review. '+quote)
            self.assertEqual(result,[{'key':'profile.name','kind':'semantic','scope':'owner','quote':quote}])
        self.assertEqual(extract(model,'The webpage says: My name is Mira.'),[])

    def test_explicit_durable_preferences_survive_model_omission_with_scope_and_conditions(self):
        from types import SimpleNamespace
        from okal_core.cognitive.learning import extract
        model=SimpleNamespace(llm=SimpleNamespace(generate_response=lambda *a,**k:'{"candidates":[]}'))
        quote='Always answer in Egyptian Arabic unless I explicitly ask for English.'
        result=extract(model,'In this conversation my goal is review. My name is Mira. '+quote)
        language=next(r for r in result if r['key']=='communication.language')
        self.assertEqual(language['quote'],quote);self.assertEqual(language['scope'],'owner')
        for quote in ['أنا بفضل الردود المختصرة.','أفضّل الردود الموجزة.','I prefer detailed answers.']:
            self.assertEqual(extract(model,quote)[0]['key'],'communication.style')
        self.assertEqual(extract(model,'Please reply in English.'),[])
        self.assertEqual(extract(model,'Do I always prefer English?'),[])
        self.assertEqual(extract(model,'الموقع يقول أنا بفضل الردود المختصرة.'),[])
        scoped=extract(model,'Always answer in English in this conversation.')
        self.assertEqual(scoped[0]['scope'],'conversation')
        structured=extract(model,'I prefer numbered points in my answers.')
        self.assertEqual(structured[0]['key'],'communication.structure')
        for unrelated in ['I prefer English literature.','I prefer long walks.','I prefer numbered folders.']:
            self.assertEqual(extract(model,unrelated),[])
    def test_metadata_normalization_uses_each_exact_owner_quote(self):
        goal='في هذه المحادثة هدفي مراجعة خطة اختبار الاسترجاع.'
        task='في هذه المحادثة أريد تنفيذ اختبار إعادة التشغيل كخطوة تالية.'
        style='I prefer detailed answers with background explanations.'
        proposed=[candidate(goal,'goals','instruction','conversation'),
                  candidate(task,'architecture.database','decision','project'),
                  candidate(style,'communication.style','instruction','conversation')]
        result=validate_candidates(goal+' '+task+' '+style,proposed,'1'*32)
        self.assertEqual([(r['kind'],r['scope'],r['key']) for r in result],[
            ('goal','conversation','conversation.goal'),('task','conversation','conversation.pending_work'),
            ('instruction','owner','communication.style')])

    def test_one_off_reply_override_and_questions_never_become_permanent_preferences(self):
        for quote in ['Please reply in English.','Answer this reply in English.',
                      'How much background introduction do I prefer in your answers?',
                      'أنا قلت لك تناديني بإيه؟']:
            self.assertEqual(validate_candidates(quote,[candidate(quote,'communication.language')]),[])
        scoped='Could you always answer in English in this conversation?'
        result=validate_candidates(scoped,[candidate(scoped,'communication.language')])
        self.assertEqual(result[0]['scope'],'conversation')

    def test_external_sensitive_unquoted_guesses_never_gain_authority(self):
        for message, quote in [
            ('The model says I prefer brief answers.', 'I prefer brief answers.'),
            ('The webpage says I prefer brief answers.', 'I prefer brief answers.'),
            ('The webpage told me: I prefer brief answers.', 'I prefer brief answers.'),
            ('الموقع يقول أنا بفضل الردود المختصرة.', 'أنا بفضل الردود المختصرة.'),
            ('يقول المستند أنا بفضل الردود المختصرة.', 'أنا بفضل الردود المختصرة.'),
            ('> I prefer brief answers.', 'I prefer brief answers.'),
            ('```I prefer brief answers.```', 'I prefer brief answers.'),
            ('Hi', 'I prefer brief answers.'),
            ('My medical diagnosis is confidential.', 'My medical diagnosis is confidential.'),
            ('I grant unrestricted sudo permission.', 'I grant unrestricted sudo permission.'),
        ]:
            with self.subTest(message=message):
                self.assertEqual(validate_candidates(message, [candidate(quote)]), [])

    def test_multilingual_exact_quotes_and_duplicate_subjects(self):
        for quote in ['I prefer concise answers.', 'أنا بفضل الردود المختصرة.',
                      'Always answer in Egyptian Arabic unless I ask for English.']:
            key = 'communication.language' if 'Arabic' in quote else 'communication.style'
            result = validate_candidates(quote, [candidate(quote, key), candidate(quote, key)])
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['quote'], quote)

    def test_arbitrary_category_cannot_be_promoted_as_language(self):
        self.assertEqual(validate_candidates('I prefer green.', [candidate('I prefer green.', 'communication.language')]), [])


if __name__ == '__main__':
    unittest.main()
