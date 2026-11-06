"""Fail-closed online snapshot tests using disposable databases and state."""
import importlib.util
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('readiness_snapshot', Path(__file__).parents[1] / 'tools/readiness_snapshot.py')
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


class ReadinessSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state = self.root / 'state'
        self.state.mkdir(mode=0o700)
        self.database = self.state / 'core.sqlite3'
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('CREATE TABLE example(id INTEGER PRIMARY KEY, message TEXT, binary BLOB)')
            db.execute('INSERT INTO example VALUES(1,?,?)', ('Synthetic / تجريبي', b'\x00\xff'))
        self.database.chmod(0o600)

    def tearDown(self):
        self.temporary.cleanup()

    def test_exact_database_and_full_state_metadata_without_source_writes(self):
        config = self.state / 'config.json'
        config.write_text('{"synthetic":"private"}')
        config.chmod(0o400)
        os.link(config, self.state / 'same-config')
        (self.state / 'outside-link').symlink_to('/nonexistent-owner-private-canary')
        before = snapshot.sha(self.database)
        report = snapshot.snapshot(self.state, self.root / 'backup')
        self.assertEqual(snapshot.sha(self.database), before)
        self.assertEqual(report['root_mode'], 0o700)
        self.assertEqual(report['table_fingerprints']['example']['count'], 1)
        self.assertEqual(report['files']['config.json']['mode'], 0o400)
        self.assertEqual(report['files']['outside-link']['kind'], 'symlink')
        with tarfile.open(self.root / 'backup/state-files.tar') as archive:
            self.assertEqual(archive.extractfile('config.json').read(), config.read_bytes())
            self.assertTrue(archive.getmember('outside-link').issym())
        self.assertEqual((self.root / 'backup/core.sqlite3').stat().st_mode & 0o777, 0o600)

    def test_refuses_nested_existing_or_symlinked_backup_destination(self):
        (self.root / 'alias').symlink_to(self.state, target_is_directory=True)
        for output in (self.state / 'backup', self.root / 'alias/backup', self.state):
            with self.subTest(output=output), self.assertRaises(ValueError):
                snapshot.snapshot(self.state, output)

    def test_refuses_symlink_database_and_exposed_state(self):
        self.database.rename(self.root / 'actual.sqlite3')
        self.database.symlink_to(self.root / 'actual.sqlite3')
        with self.assertRaises(ValueError):
            snapshot.snapshot(self.state, self.root / 'backup')
        self.state.chmod(0o755)
        with self.assertRaises(ValueError):
            snapshot.snapshot(self.state, self.root / 'backup2')

    def test_rejects_foreign_key_corruption(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('CREATE TABLE child(parent INTEGER REFERENCES example(id))')
            db.execute('INSERT INTO child VALUES(999)')
        with self.assertRaisesRegex(ValueError, 'foreign_keys'):
            snapshot.snapshot(self.state, self.root / 'backup')
        self.assertFalse((self.root / 'backup/verified-private.json').exists())

    def test_live_file_change_is_not_reported_verified(self):
        config = self.state / 'config.json'
        config.write_text('before')
        inventory = snapshot.inventory
        count = 0
        def changed(root):
            nonlocal count
            count += 1
            if count == 2:
                config.write_text('after')
            return inventory(root)
        with patch.object(snapshot, 'inventory', changed), self.assertRaisesRegex(ValueError, 'changed_during_backup'):
            snapshot.snapshot(self.state, self.root / 'backup')

    def test_concurrent_wal_write_does_not_change_the_captured_snapshot(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('PRAGMA journal_mode=WAL')
        original = snapshot.fingerprint
        written = False
        def concurrent(db):
            nonlocal written
            result = original(db)
            if not written:
                written = True
                with closing(sqlite3.connect(self.database)) as writer, writer:
                    writer.execute('INSERT INTO example VALUES(2,?,NULL)', ('New concurrent message',))
            return result
        with patch.object(snapshot, 'fingerprint', concurrent):
            report = snapshot.snapshot(self.state, self.root / 'backup')
        self.assertEqual(report['table_fingerprints']['example']['count'], 1)
        with closing(sqlite3.connect(self.database)) as db, db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM example').fetchone()[0], 2)


if __name__ == '__main__':
    unittest.main()
