"""Real FTS, ledger filtering, scope and bounded personalization tests."""
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from okal_core.cognitive.context import reply_language
from okal_core.cognitive.retrieval import Retrieval
from okal_core.intelligence import Intelligence, respond
from okal_core.store import Store


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name)/'state')
        self.chat = Intelligence(self.store)
        self.ledger = self.chat.cognitive
        self.search = Retrieval(self.ledger)
        self.con = self.chat.create()['id']

    def say(self, message, **kwargs):
        return respond(self.store,self.con,uuid.uuid4().hex,message,
                       infer=lambda *_: {'intent':'answer','answer':'Synthetic answer.'}, **kwargs)

    def test_global_instruction_is_retrieved_without_keyword_overlap(self):
        memory = self.chat.save_memory('communication.language',
            'Always answer in Egyptian Arabic unless I ask for English.',kind='instruction')
        selected, metadata = self.search.select(self.con, 'Hello')
        self.assertEqual(selected[0]['id'], memory['id'])
        self.assertEqual(metadata['semantic_index'], 'not_configured')
        self.assertEqual(reply_language('Hello', selected), 'Egyptian Arabic')
        self.assertEqual(reply_language('Please reply in English.', selected), 'English')

    def test_conversation_instruction_precedes_global(self):
        self.chat.save_memory('communication.language', 'Always answer in English.',kind='instruction')
        self.chat.save_memory('communication.language', 'Always answer in Egyptian Arabic.',
                              kind='instruction',conversation_id=self.con)
        selected,_ = self.search.select(self.con,'Hello')
        self.assertEqual(reply_language('Hello',selected),'Egyptian Arabic')
        other = self.chat.create()['id']
        selected,_ = self.search.select(other,'Hello')
        self.assertEqual(reply_language('Hello',selected),'English')

    def test_current_chat_progress_never_receives_another_chats_pending_work(self):
        project=self.ledger.save_project('Orion garden')
        self.ledger.associate(self.con,project['id'])
        first=self.say('My next task in this conversation is test R-001.')
        self.ledger.save('conversation.pending_work','My next task in this conversation is test R-001.',
            kind='task',conversation_id=self.con,source_turn=first['turn_id'])
        original=self.con
        self.con=self.chat.create()['id'];self.ledger.associate(self.con,project['id'])
        second=self.say('My next task in this conversation is test R-002.')
        self.ledger.save('conversation.pending_work','My next task in this conversation is test R-002.',
            kind='task',conversation_id=self.con,source_turn=second['turn_id'])
        selected,context=self.search.select(original,'What is pending in this conversation?')
        rendered=json.dumps({'selected':selected,'context':context})
        self.assertIn('R-001',rendered);self.assertNotIn('R-002',rendered)

    def test_arabic_name_query_has_authoritative_profile_fallback(self):
        self.chat.save_memory('profile.name','My name is Mira.')
        selected,_=self.search.select(self.con,'اسمي إيه؟')
        self.assertTrue(any('Mira' in r['content'] for r in selected))

    def test_project_names_do_not_merge_and_explicit_name_recovers_across_chats(self):
        garden = self.ledger.save_project('Orion garden')
        satellite = self.ledger.save_project('Orion satellite')
        one = self.ledger.save('architecture.database', 'We chose SQLite for offline garden work.',
                               kind='decision',project_id=garden['id'])
        two = self.ledger.save('architecture.database', 'We chose PostgreSQL for satellite telemetry.',
                               kind='decision',project_id=satellite['id'])
        selected, metadata = self.search.select(self.con, 'Continue the Orion garden project.')
        self.assertIn(one['id'], [r['id'] for r in selected])
        self.assertNotIn(two['id'], [r['id'] for r in selected])
        self.assertEqual(metadata['project']['id'],garden['id'])
        selected, metadata = self.search.select(self.con,'Continue Orion project.')
        self.assertEqual(selected,[])
        self.assertEqual(len(metadata['project_ambiguity']),2)
        self.assertEqual(self.ledger.conversation_state(self.con)['project_id'],None)

    def test_ambiguity_returns_one_clarification_without_inference_or_actions(self):
        self.ledger.save_project('Orion garden')
        self.ledger.save_project('Orion satellite')
        response = respond(self.store,self.con,uuid.uuid4().hex,'Continue Orion project.',
            infer=lambda *_: self.fail('Ambiguous project must not reach inference'))
        self.assertEqual(response['source'],'explicit_project_clarification')
        self.assertIn('Orion garden', response['answer'])

    def test_unique_full_owner_project_reference_associates_without_keyword_guessing(self):
        project=self.ledger.save_project('Orion garden')
        self.say('Continue the Orion garden project.')
        self.assertEqual(self.ledger.conversation_state(self.con)['project_id'],project['id'])
        job=self.ledger.claim_job()
        self.assertEqual(job['scope_project_id'],project['id'])

    def test_automatic_reference_does_not_relabel_unrelated_earlier_history(self):
        first=self.say('I prefer concise replies.')
        project=self.ledger.save_project('Orion garden')
        second=self.say('Continue the Orion garden project.')
        with self.store.connect() as db:
            mappings={r[0]:r[1] for r in db.execute('SELECT turn_id,project_id FROM memory_turn_projects')}
        self.assertIsNone(mappings[first['turn_id']])
        self.assertEqual(mappings[second['turn_id']],project['id'])

    def test_distinctive_decision_reference_retrieves_without_writing_association(self):
        project=self.ledger.save_project('Local assistant')
        decision=self.ledger.save('memory.engine','We chose Mem0 for multilingual memory.',kind='decision',project_id=project['id'])
        selected,context=self.search.select(self.con,'Why did we choose Mem0?')
        self.assertIn(decision['id'],[r['id'] for r in selected])
        self.assertEqual(context['project']['id'],project['id'])
        self.assertIsNone(self.ledger.conversation_state(self.con)['project_id'])

    def test_one_clarification_binds_original_source_to_confirmed_project(self):
        garden=self.ledger.save_project('Orion garden')
        satellite=self.ledger.save_project('Orion satellite')
        self.ledger.associate(self.con,garden['id'])
        quote='We chose SQLite for the Orion satellite project.'
        reply=self.say(quote)
        self.assertEqual(reply['source'],'explicit_project_clarification')
        self.assertIsNone(self.ledger.claim_job())
        self.say('Orion satellite')
        job=self.ledger.claim_job()
        self.assertEqual(job['turn_id'],reply['turn_id'])
        self.assertEqual(job['scope_project_id'],satellite['id'])
        self.ledger.apply_job(job['turn_id'],job['lease'],[
            {'key':'architecture.database','kind':'decision','scope':'project','quote':quote}])
        self.assertEqual(self.chat.memories(project_id=garden['id'])['items'],[])
        self.assertEqual(len(self.chat.memories(project_id=satellite['id'])['items']),1)

    def test_project_switch_never_relabels_old_sources(self):
        garden=self.ledger.save_project('Orion garden')
        satellite=self.ledger.save_project('Orion satellite')
        link=self.ledger.associate(self.con,garden['id'])
        source=self.say('We chose SQLite for offline operation.')
        self.ledger.associate(self.con,satellite['id'],revision=link['revision'])
        job=self.ledger.claim_job()
        self.assertEqual(job['scope_project_id'],garden['id'])
        self.assertEqual(len(self.search.archive('SQLite',project_id=garden['id'])['items']),1)
        self.assertEqual(self.search.archive('SQLite',project_id=satellite['id'])['items'],[])
        self.ledger.apply_job(job['turn_id'],job['lease'],[
            {'key':'architecture.database','kind':'decision','scope':'project','quote':'We chose SQLite for offline operation.'}])
        self.assertEqual(self.ledger.versions(self.chat.memories(project_id=garden['id'])['items'][0]['id'])['sources'][0]['turn_id'],source['turn_id'])

    def test_archive_is_searchable_and_forget_updates_fts_without_erasing_other_text(self):
        turn = self.say('I prefer concise answers. The greenhouse needs a temperature sensor.')
        memory = self.chat.save_memory('communication.style','I prefer concise answers.',source_turn=turn['turn_id'])
        self.assertEqual(len(self.search.archive('concise')['items']),1)
        self.chat.forget(memory['id'])
        self.assertEqual(self.search.archive('concise')['items'],[])
        preserved = self.search.archive('greenhouse')['items']
        self.assertEqual(len(preserved),1)
        self.assertIn('temperature sensor', preserved[0]['owner_excerpt'])
        self.assertIsNone(preserved[0]['assistant_excerpt'])

    def test_archive_search_is_scoped_and_quotes_are_not_promoted(self):
        project = self.ledger.save_project('Garden')
        self.ledger.associate(self.con,project['id'])
        self.say('The document says: A greenhouse needs five sensors.')
        self.con = self.chat.create()['id']
        self.say('A greenhouse needs nine sensors.')
        rows = self.search.archive('greenhouse',project_id=project['id'])['items']
        self.assertEqual(len(rows),1)
        self.assertIn('five',rows[0]['owner_excerpt'])
        self.assertEqual(self.chat.memories()['items'],[])

    def test_terminal_fallback_still_enqueues_committed_owner_evidence(self):
        response = respond(self.store,self.con,uuid.uuid4().hex,'I prefer brief answers.',
                           infer=lambda *_: (_ for _ in ()).throw(OSError('offline')))
        self.assertEqual(response['mode'],'saved_fallback')
        self.assertIsNotNone(self.ledger.claim_job())

    def test_archive_query_operators_and_pagination_are_data(self):
        for number in range(3):
            self.say(f'I prefer project note {number}.')
        first = self.search.archive('project',limit=2)
        second = self.search.archive('project',before=first['next_before'],limit=2)
        self.assertEqual(len(first['items'])+len(second['items']),3)
        self.assertEqual(self.search.archive('" OR NEAR(*)')['items'],[])
        with self.store.connect() as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_delete_archive_source_fences_cross_chat_answer(self):
        project = self.ledger.save_project('Garden')
        self.ledger.associate(self.con,project['id'])
        original = self.con
        self.say('The irrigation budget is four sensors.')
        self.con = self.chat.create()['id']
        claim = self.chat.begin(self.con,uuid.uuid4().hex,'Continue Garden irrigation budget.')
        _, context = self.chat.context(self.con,'Continue Garden irrigation budget.',claim['turn_id'])
        self.assertTrue(context['archive_excerpts'])
        self.chat.delete(original)
        from okal_core.store import Conflict
        with self.assertRaises(Conflict):
            self.chat.finish(claim['turn_id'],claim['lease'],{'answer':'Four sensors.','mode':'owner_memory'})
        results=self.search.archive('irrigation')['items']
        self.assertNotIn('four sensors',json.dumps(results))
        self.assertEqual(len(results),1)  # The unrelated owner question survives.
        self.assertIsNone(results[0]['assistant_excerpt'])


if __name__=='__main__':
    unittest.main()
