"""Real filesystem vault/CAS/privacy tests on temporary owner-private state."""
from pathlib import Path
import tempfile
import unittest

from okal_core.cognitive.vault import Vault
from okal_core.intelligence import Intelligence
from okal_core.store import Store, Conflict


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'state')
        self.chat = Intelligence(self.store)
        self.vault = Vault(self.chat.cognitive)
        self.memory = self.chat.save_memory('communication.style', 'I prefer concise answers.', kind='instruction')

    def test_private_structured_note_and_controlled_owner_revision(self):
        self.vault.export(self.memory)
        path = self.vault._locate(self.memory['id'])[0]
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.vault.root.stat().st_mode & 0o777, 0o700)
        self.assertIn('memory_id: "' + self.memory['id'] + '"', path.read_text())
        path.write_text(path.read_text().replace('I prefer concise answers.', 'I prefer detailed answers.'))
        self.assertTrue(self.vault.preview(self.memory['id'])['changed'])
        self.assertEqual(self.chat.memories()['items'][0]['content'], 'I prefer concise answers.')
        with self.assertRaises(Conflict):
            self.vault.export(self.memory)
        result = self.vault.import_revision(self.memory['id'], 1, self.vault.preview(self.memory['id'])['content_sha256'])
        self.assertEqual(result['revision'], 2)
        self.assertEqual(self.chat.memories()['items'][0]['content'], 'I prefer detailed answers.')
        self.assertFalse(self.vault.preview(self.memory['id'])['changed'])

    def test_stale_note_cannot_overwrite_correction(self):
        self.vault.export(self.memory)
        self.chat.save_memory('communication.style', 'I prefer detailed answers.', kind='instruction', revision=1)
        with self.assertRaises(Conflict):
            self.vault.import_revision(self.memory['id'], 1, '0'*64)

    def test_memory_import_requires_exact_previewed_content(self):
        self.vault.export(self.memory)
        path=self.vault._locate(self.memory['id'])[0]
        path.write_text(path.read_text().replace('I prefer concise answers.','I prefer detailed answers.'))
        preview=self.vault.preview(self.memory['id'])
        path.write_text(path.read_text().replace('I prefer detailed answers.','I prefer brief answers.'))
        with self.assertRaises(Conflict):
            self.vault.import_revision(self.memory['id'],1,preview['content_sha256'])
        self.assertEqual(self.chat.memories()['items'][0]['revision'],1)
        fresh=self.vault.preview(self.memory['id'])
        self.vault.import_revision(self.memory['id'],1,fresh['content_sha256'])
        self.assertEqual(self.chat.memories()['items'][0]['content'],'I prefer brief answers.')

    def test_project_import_requires_exact_previewed_content(self):
        project=self.chat.cognitive.save_project('Preview project','Original description.')
        self.vault.export_project(project['id'])
        path=self.vault.root/'projects'/('project-'+project['id']+'.md')
        path.write_text(path.read_text().replace('Original description.','Previewed description.'))
        preview=self.vault.preview_project(project['id'])
        path.write_text(path.read_text().replace('Previewed description.','Unseen description.'))
        with self.assertRaises(Conflict):
            self.vault.import_project(project['id'],1,preview['content_sha256'])
        self.assertEqual(self.chat.cognitive.projects()['items'][0]['description'],'Original description.')

    def test_browser_import_contract_rejects_missing_or_obsolete_preview(self):
        from fastapi.testclient import TestClient
        from okal_core.api import create_app
        client=TestClient(create_app(self.store),base_url='http://127.0.0.1:8766',client=('127.0.0.1',1234))
        self.addCleanup(client.close)
        headers={'Origin':'http://127.0.0.1:8766','Sec-Fetch-Site':'same-origin'}
        self.vault.export(self.memory)
        path=self.vault._locate(self.memory['id'])[0]
        path.write_text(path.read_text().replace('I prefer concise answers.','I prefer detailed answers.'))
        body={'memory_id':self.memory['id'],'revision':1}
        endpoint='/api/v1/chat/vault-import'
        self.assertEqual(client.post(endpoint,json=body,headers=headers).status_code,422)
        preview=client.post('/api/v1/chat/vault-preview',json={'memory_id':self.memory['id']},headers=headers).json()
        body['content_sha256']=preview['content_sha256']
        path.write_text(path.read_text().replace('I prefer detailed answers.','I prefer brief answers.'))
        self.assertEqual(client.post(endpoint,json=body,headers=headers).status_code,409)
        self.assertEqual(self.chat.memories()['items'][0]['revision'],1)
        body['content_sha256']=self.vault.preview(self.memory['id'])['content_sha256']
        self.assertEqual(client.post(endpoint,json=body,headers=headers).status_code,200)

    def test_forgotten_note_and_stale_export_cannot_resurrect(self):
        self.vault.export(self.memory)
        path = self.vault._locate(self.memory['id'])[0]
        original = path.read_text()
        self.chat.forget(self.memory['id'])
        with self.assertRaises(Conflict):
            self.vault.import_revision(self.memory['id'], 1, '0'*64)
        with self.assertRaises(Conflict):
            self.vault.export(self.memory)
        self.vault.delete(self.memory['id'])
        self.assertFalse(path.exists())
        path.write_text(original)
        with self.assertRaises(Conflict):
            self.vault.import_revision(self.memory['id'], 1, '0'*64)
        self.assertEqual(self.chat.memories()['items'], [])

    def test_symlink_note_and_nonprivate_directory_are_rejected(self):
        self.vault.export(self.memory)
        path = self.vault._locate(self.memory['id'])[0]
        outside = Path(self.temp.name) / 'outside'
        outside.write_text('untouched')
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaises(OSError):
            self.vault.preview(self.memory['id'])
        self.vault.delete(self.memory['id'])
        self.assertEqual(outside.read_text(), 'untouched')
        (self.vault.root / 'preferences').chmod(0o755)
        with self.assertRaises(ValueError):
            self.vault.export(self.memory)

    def test_credential_import_and_wrong_revision_are_rejected(self):
        self.vault.export(self.memory)
        path = self.vault._locate(self.memory['id'])[0]
        path.write_text(path.read_text().replace('I prefer concise answers.', 'password=synthetic-password'))
        with self.assertRaises(ValueError):
            self.vault.import_revision(self.memory['id'], 1, '0'*64)
        path.write_text(path.read_text().replace('password=synthetic-password', 'I prefer English.'))
        with self.assertRaises(Conflict):
            self.vault.import_revision(self.memory['id'], 100, '0'*64)

    def test_general_computer_actions_cannot_read_curated_vault(self):
        from types import SimpleNamespace
        from okal_core.computer.files import Files
        from okal_core.computer.contracts import Denied
        self.vault.export(self.memory)
        files=Files([SimpleNamespace(root=self.temp.name,write=True)], self.store.directory)
        with self.assertRaises(Denied):
            files.read(str(self.vault._locate(self.memory['id'])[0]))

    def test_automatic_note_text_cannot_embed_remote_images_or_break_fence(self):
        content='I prefer literal examples: ![image](https://invalid.example/private) ``` <img src="https://invalid.example">'
        record=self.chat.save_memory('literal examples',content)
        self.vault.export(record)
        path=self.vault._locate(record['id'])[0]
        raw=path.read_text()
        self.assertIn('````text\n'+content+'\n````',raw)
        self.assertEqual(self.vault.preview(record['id'])['content'],content)

    def test_ephemeral_conversation_tasks_do_not_create_vault_notes(self):
        conversation=self.chat.create()['id']
        record=self.chat.save_memory('pending','I need to run a temporary test.',kind='task',conversation_id=conversation)
        self.assertEqual(self.vault.export(record)['status'],'not_curated')
        self.assertEqual(self.vault._locate(record['id']),[])

    def test_kind_correction_moves_one_note_without_discarding_owner_edits(self):
        record=self.chat.save_memory('durable plan','I want offline operation.',kind='semantic')
        self.vault.export(record)
        old_path=self.vault._locate(record['id'])[0]
        edited=old_path.read_text().replace('I want offline operation.','I want reviewed offline operation.')
        old_path.write_text(edited)
        revised=self.chat.save_memory('durable plan','I want offline operation.',kind='goal',revision=1)
        with self.assertRaises(Conflict):self.vault.export(revised)
        self.assertEqual(old_path.read_text(),edited)
        old_path.write_text(edited.replace('I want reviewed offline operation.','I want offline operation.'))
        self.vault.export(revised)
        paths=self.vault._locate(record['id'])
        self.assertEqual(len(paths),1)
        self.assertEqual(paths[0].parent.name,'goals')
        self.assertFalse(old_path.exists())

    def test_project_overview_links_and_controlled_description_import(self):
        project=self.chat.cognitive.save_project('Orion garden','Private offline planning.')
        memory=self.chat.cognitive.save('database','We chose SQLite.',kind='decision',project_id=project['id'])
        self.vault.export(memory)
        self.vault.export_project(project['id'])
        path=self.vault.root/'projects'/('project-'+project['id']+'.md')
        self.assertIn('[[memory-'+memory['id']+']]',path.read_text())
        self.assertIn('[[project-'+project['id']+']]',self.vault._locate(memory['id'])[0].read_text())
        path.write_text(path.read_text().replace('Private offline planning.','Reviewed offline planning.'))
        preview=self.vault.preview_project(project['id'])
        self.assertTrue(preview['changed'])
        self.assertEqual(self.chat.cognitive.projects()['items'][0]['revision'],1)
        with self.assertRaises(Conflict):self.vault.export_project(project['id'])
        self.assertEqual(self.vault.import_project(project['id'],1,preview['content_sha256'])['revision'],2)
        with self.assertRaises(Conflict):self.vault.import_project(project['id'],1,preview['content_sha256'])
        self.chat.forget(memory['id'])
        self.vault.export_project(project['id'])
        self.assertNotIn('[[memory-',path.read_text())

    def test_obsidian_unquoted_identifier_properties_remain_inert(self):
        self.vault.export(self.memory)
        path=self.vault._locate(self.memory['id'])[0]
        path.write_text(path.read_text().replace('memory_id: "'+self.memory['id']+'"',
                                                'memory_id: '+self.memory['id']).replace('scope: "owner"','scope: owner'))
        self.assertFalse(self.vault.preview(self.memory['id'])['changed'])
        path.write_text(path.read_text().replace('scope: owner','scope: !!python/object:evil'))
        with self.assertRaises(ValueError):self.vault.preview(self.memory['id'])


if __name__ == '__main__':
    unittest.main()
