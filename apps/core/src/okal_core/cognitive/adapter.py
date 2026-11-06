"""Mem0 OSS / embedded Qdrant projection. Import only in the adapter process.

The Core always validates returned IDs/revisions against SQLite. This module
does not open the authoritative database and has no authority to create facts.
"""
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import uuid

from .providers import BASE_URL, LocalRuntime, configure
from ..store import private_directory, private_file


class Mem0Adapter:
    def __init__(self, directory: Path, runtime: LocalRuntime):
        self.directory = private_directory(directory)
        lock_path = self.directory / 'adapter.lock'
        private_file(lock_path)
        self.lock = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self.lock)
            raise ValueError('memory_adapter_already_running') from None
        self.memory = None
        self.runtime = runtime
        try:
            self._open()
        except BaseException:
            self.close()
            raise

    def _open(self):
        os.environ.update(MEM0_TELEMETRY='False', DO_NOT_TRACK='1',
                          MEM0_DIR=str(self.directory / 'mem0'))
        # An already-imported telemetry singleton cannot be made private by
        # changing an env var. Reject such embedding of this adapter in Core.
        import sys
        if 'mem0.memory.telemetry' in sys.modules:
            if sys.modules['mem0.memory.telemetry'].MEM0_TELEMETRY:
                raise ValueError('mem0_imported_before_privacy_configuration')
        configure(self.runtime)
        self.runtime.verify(self.runtime.llm)
        self.runtime.verify(self.runtime.embedder)
        from mem0 import Memory
        from mem0.configs.llms.ollama import OllamaConfig
        from mem0.utils.factory import EmbedderFactory, LlmFactory
        # Mem0 2.2.1 validates a fixed provider name list. Replace only the
        # process-local Ollama classes; never modify the installed package.
        LlmFactory.register_provider('ollama',
            'okal_core.cognitive.providers.PinnedLLM', OllamaConfig)
        EmbedderFactory.provider_to_class['ollama'] = (
            'okal_core.cognitive.providers.PinnedEmbedding')
        index = private_directory(self.directory / 'qdrant')
        fingerprint = {'model': self.runtime.embedder.name,
                       'digest': self.runtime.embedder.digest,
                       'dimensions': self.runtime.dimensions, 'prefix_version': 1}
        manifest = self.directory / 'index.json'
        initialize = not manifest.exists()
        if manifest.exists() or manifest.is_symlink():
            private_file(manifest)
            raw = manifest.read_text()
            if not raw and not any(index.iterdir()) and not (self.directory/'derived-history.sqlite3').exists():
                initialize = True  # Recover the interrupted pre-index creation path.
            elif not raw:
                raise ValueError('index_manifest_corrupt_rebuild_required')
            elif json.loads(raw) != fingerprint:
                raise ValueError('embedding_upgrade_requires_new_index_and_rebuild')
        if initialize:
            self.runtime.embed(['Verify embedding dimensions.'])
            temporary=self.directory/('.index-'+uuid.uuid4().hex+'.tmp')
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            try:
                with os.fdopen(fd,'w',encoding='utf-8') as stream:
                    stream.write(json.dumps(fingerprint));stream.flush();os.fsync(stream.fileno())
                os.replace(temporary,manifest)
                directory_fd=os.open(self.directory,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(directory_fd)
                finally:os.close(directory_fd)
            finally:
                temporary.unlink(missing_ok=True)
        history = self.directory / 'derived-history.sqlite3'
        private_file(history)
        self.memory = Memory.from_config({
            'version': 'v1.1', 'history_db_path': str(history),
            'llm': {'provider': 'ollama', 'config': {
                'model': self.runtime.llm.name, 'ollama_base_url': BASE_URL,
                'temperature': 0, 'max_tokens': 1000}},
            'embedder': {'provider': 'ollama', 'config': {
                'model': self.runtime.embedder.name,
                'embedding_dims': self.runtime.dimensions, 'ollama_base_url': BASE_URL}},
            'vector_store': {'provider': 'qdrant', 'config': {
                'collection_name': 'okal_owner_memory_v2',
                'embedding_model_dims': self.runtime.dimensions,
                'path': str(index), 'on_disk': True}},
        })

    def project(self, record: dict) -> dict:
        """Idempotent reconciliation by ledger ID, not Mem0-generated fact IDs."""
        memory_id, revision = record['id'], record['revision']
        matches = self.memory.get_all(filters={
            'user_id': 'owner', 'ledger_id': memory_id}, top_k=100)['results']
        metadata = {'ledger_id': memory_id, 'revision': revision,
                    'scope': record['scope'], 'source_turn': record.get('source_turn')}
        # Repair interrupted legacy duplicates before acknowledging the outbox.
        for duplicate in matches[1:]:
            self.memory.delete(duplicate['id'])
        if matches:
            vector_id = matches[0]['id']
            self.memory.update(vector_id, text=record['content'], metadata=metadata)
        else:
            results = self.memory.add(record['content'], user_id='owner',
                                      metadata=metadata, infer=False)['results']
            if len(results) != 1:
                raise ValueError('unexpected_mem0_projection_result')
            vector_id = results[0]['id']
        self._purge_history()
        return {'id': memory_id, 'revision': revision, 'vector_id': vector_id}

    def search(self, query: str, limit: int = 12) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 24:
            raise ValueError('invalid_retrieval_limit')
        result = self.memory.search(query, filters={'user_id': 'owner'},
                                    top_k=limit, rerank=False)['results']
        return [{'id': r['metadata']['ledger_id'],
                 'revision': r['metadata']['revision'], 'score': r['score']}
                for r in result if isinstance(r.get('metadata'), dict)
                and 'ledger_id' in r['metadata'] and 'revision' in r['metadata']]

    def delete(self, memory_id: str):
        matches = self.memory.get_all(filters={
            'user_id': 'owner', 'ledger_id': memory_id}, top_k=100)['results']
        for match in matches:
            self.memory.delete(match['id'])
        self._purge_history()
        return {'id': memory_id, 'deleted': True}

    def reset_projection(self):
        # Reset the reviewed provider in place. Memory.reset() replaces its
        # Qdrant client and can collide with the existing embedded path lock.
        self.memory.vector_store.reset()
        self._purge_history()
        return {'reset': True}

    def _purge_history(self):
        # Mem0's internal change history is a disposable cache, never a second
        # archive. Do not retain superseded or deleted owner text there.
        with closing(sqlite3.connect(self.directory / 'derived-history.sqlite3')) as db, db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('DELETE FROM history')

    def close(self):
        try:
            if self.memory is not None:
                try:
                    self.memory.close()
                finally:
                    self.memory.vector_store.client.close()
                    self.memory = None
        finally:
            self.runtime.close()
            if self.lock is not None:
                os.close(self.lock)
                self.lock = None
