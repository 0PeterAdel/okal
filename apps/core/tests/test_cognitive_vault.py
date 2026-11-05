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
        result = self.vault.import_revision(self.memory['id'], 1)
        self.assertEqual(result['revision'], 2)
        self.assertEqual(self.chat.memories()['items'][0]['content'], 'I prefer detailed answers.')
        self.assertFalse(self.vault.preview(self.memory['id'])['changed'])

    def test_stale_note_cannot_overwrite_correction(self):
        self.vault.export(self.memory)
        self.chat.save_memory('communication.style', 'I prefer detailed answers.', kind='instruction', revision=1)
        with self.assertRaises(Conflict):
            self.vault.import_revision(self.memory['id'], 1)

    def test_forgotten_note_and_stale_export_cannot_resurrect(self):
        self.vault.export(self.memory)
        path = self.vault._locate(self.memory['id'])[0]
        original = path.read_text()
        self.chat.forget(self.memory['id'])
        with self.assertRaises(Conflict):
            self.vault.import_revision(self.memory['id'], 1)
        with self.assertRaises(Conflict):
            self.vault.export(self.memory)
        self.vault.delete(self.memory['id'])
        self.assertFalse(path.exists())
        path.write_text(original)
        with self.assertRaises(Conflict):
            self.vault.import_revision(self.memory['id'], 1)
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
            self.vault.import_revision(self.memory['id'], 1)
        path.write_text(path.read_text().replace('password=synthetic-password', 'I prefer English.'))
        with self.assertRaises(Conflict):
            self.vault.import_revision(self.memory['id'], 100)


if __name__ == '__main__':
    unittest.main()
