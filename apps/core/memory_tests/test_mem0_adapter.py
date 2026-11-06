"""Offline CI integration: real Mem0/Qdrant with deterministic vector fixtures.

These tests establish adapter/lifecycle compatibility, not model recall quality.
The separate on-device harness evaluates actual pinned Ollama models.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing

from okal_core.cognitive.adapter import Mem0Adapter
from okal_core.cognitive.providers import ModelPin


class FixtureRuntime:
    def __init__(self, fail_probe=False):
        self.llm=ModelPin('qwen3.5:4b','1'*64)
        self.embedder=ModelPin('bge-m3:latest','2'*64)
        self.dimensions=64
        self.fail_probe=fail_probe
        self.closed=False

    def verify(self,pin):
        if pin not in (self.llm,self.embedder):raise ValueError('unreviewed_fixture_model')

    def embed(self,texts,action='add'):
        if self.fail_probe:raise OSError('injected_initial_probe_interruption')
        return [[(value+1)/256 for value in hashlib.sha512(text.encode()).digest()] for text in texts]

    def generate(self,*args,**kwargs):
        raise AssertionError('CRUD projection must not make autonomous LLM decisions')

    def close(self):
        self.closed=True


class Mem0Integration(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'projection'

    def record(self,revision=1,content='I prefer concise answers.'):
        return {'id':'a'*32,'revision':revision,'scope':'owner','content':content}

    def test_real_persistent_crud_and_no_competing_history(self):
        adapter=Mem0Adapter(self.path,FixtureRuntime())
        try:
            created=adapter.project(self.record())
            self.assertEqual(adapter.project(self.record())['vector_id'],created['vector_id'])
            adapter.project(self.record(2,'I prefer detailed answers.'))
            self.assertEqual(adapter.search('detailed answers')[0]['revision'],2)
            from mem0.memory import telemetry
            self.assertFalse(telemetry.MEM0_TELEMETRY)
            with closing(sqlite3.connect(self.path/'derived-history.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM history').fetchone()[0],0)
        finally:adapter.close()
        reopened=Mem0Adapter(self.path,FixtureRuntime())
        try:
            self.assertEqual(reopened.search('detailed answers')[0]['id'],'a'*32)
            reopened.delete('a'*32);reopened.delete('a'*32)
            self.assertEqual(reopened.search('detailed answers'),[])
        finally:reopened.close()

    def test_exclusive_owner_and_rebuild_in_place(self):
        adapter=Mem0Adapter(self.path,FixtureRuntime())
        try:
            with self.assertRaisesRegex(ValueError,'already_running'):
                Mem0Adapter(self.path,FixtureRuntime())
            adapter.project(self.record())
            adapter.reset_projection()
            self.assertEqual(adapter.search('preference'),[])
            adapter.project(self.record())
            self.assertEqual(adapter.search('preference')[0]['revision'],1)
        finally:adapter.close()

    def test_interrupted_probe_does_not_leave_empty_manifest(self):
        with self.assertRaises(OSError):Mem0Adapter(self.path,FixtureRuntime(fail_probe=True))
        self.assertFalse((self.path/'index.json').exists())
        adapter=Mem0Adapter(self.path,FixtureRuntime())
        try:self.assertEqual(json.loads((self.path/'index.json').read_text())['dimensions'],64)
        finally:adapter.close()

    def test_legacy_empty_initial_manifest_can_recover_but_populated_index_cannot(self):
        self.path.mkdir(mode=0o700)
        (self.path/'qdrant').mkdir(mode=0o700)
        manifest=self.path/'index.json';manifest.touch(mode=0o600)
        adapter=Mem0Adapter(self.path,FixtureRuntime())
        adapter.project(self.record());adapter.close()
        manifest.write_text('')
        with self.assertRaisesRegex(ValueError,'corrupt_rebuild_required'):
            Mem0Adapter(self.path,FixtureRuntime())

    def test_model_fingerprint_change_requires_explicit_new_index(self):
        adapter=Mem0Adapter(self.path,FixtureRuntime());adapter.close()
        runtime=FixtureRuntime();runtime.embedder=ModelPin('bge-m3:latest','3'*64)
        with self.assertRaisesRegex(ValueError,'upgrade_requires'):
            Mem0Adapter(self.path,runtime)


if __name__=='__main__':unittest.main()
