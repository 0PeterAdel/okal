"""Bounded background ingestion and independent projection reconciliation."""
from contextlib import contextmanager
import fcntl
import os
import threading

from .process import AdapterClient, AdapterUnavailable
from .vault import Vault


@contextmanager
def mail_idle(directory):
    """Share the existing mail serialization boundary without reading credentials."""
    path = directory / 'mail' / 'operation.lock'
    if not path.exists():
        yield True
        return
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
        else:
            yield True
    finally:
        os.close(fd)


class MemoryWorker:
    def __init__(self, store):
        from ..intelligence import Intelligence
        self.store = store
        self.ledger = Intelligence(store).cognitive
        self.adapter = AdapterClient(store.directory)
        self.stop_event = threading.Event()
        self.thread = None
        self.status = 'not_configured'
        # Chat can opportunistically retrieve; it never waits for extraction.
        store.memory_adapter = self.adapter
        store.memory_worker = self

    def _project(self, job):
        memory_id, revision = job['memory_id'], job['revision']
        operation = job['operation']
        index_status, vault_status = job['index_status'], job['vault_status']
        error = None
        record = None
        if operation == 'upsert':
            records = self.ledger.active([{'id': memory_id, 'revision': revision}])
            if not records:
                return
            record = records[0]
        if index_status != 'current':
            try:
                self.adapter.call('project' if record else 'delete',
                                  {'record': record} if record else {'id': memory_id})
                index_status = 'current'
            except AdapterUnavailable:
                index_status, error = 'failed', 'local_adapter_unavailable'
        # Vault failure never prevents indexing or personal memory/chat use.
        if vault_status != 'current':
            try:
                vault = Vault(self.ledger)
                vault.export(record) if record else vault.delete(memory_id)
                vault_status = 'current'
            except Exception:
                vault_status, error = 'failed', 'vault_conflict_or_unavailable'
        attempts = job['attempts'] + 1
        status = 'current' if index_status == vault_status == 'current' else (
            'failed' if attempts >= 5 else 'pending')
        with self.store.connect() as db, db:
            db.execute('''UPDATE memory_outbox SET index_status=?,vault_status=?,status=?,
                attempts=?,available_at=?,error=?,updated_at=?
                WHERE memory_id=? AND revision=? AND operation=?''', (
                index_status, vault_status, status, attempts,
                self.ledger.now + min(3600, 15 * 2**attempts) if error else 0,
                error, self.ledger.now, memory_id, revision, operation))

    def tick(self):
        if not self.adapter.config_path.exists():
            self.status = 'not_configured'
            return
        self.ledger.backfill()
        with self.store.connect() as db:
            ready = [dict(r) for r in db.execute("SELECT * FROM memory_outbox WHERE status='pending' "
                    "AND available_at<=? ORDER BY CASE operation WHEN 'delete' THEN 0 ELSE 1 END,"
                    'updated_at,memory_id LIMIT 4', (self.ledger.now,))]
        self.status = 'processing'
        for job in ready:
            if self.stop_event.is_set():
                return
            self._project(job)
        if self.stop_event.is_set():
            return
        with mail_idle(self.store.directory) as idle:
            if not idle:
                self.status = 'waiting_for_mail'
                return
            job = self.ledger.claim_job()
            if job:
                try:
                    state = self.ledger.conversation_state(job['conversation_id'])
                    # Existing subject labels help Mem0 consolidate; source text
                    # and authoritative revision checks remain in Core.
                    with self.store.connect() as db:
                        existing = [dict(r) for r in db.execute(
                            'SELECT key,kind,scope FROM chat_memories WHERE scope IN (?,?,?) '
                            'ORDER BY updated_at DESC LIMIT 16',
                            ('owner', job['conversation_id'], 'project:' + (state['project_id'] or '')))]
                    candidates = self.adapter.call('extract', {'message': job['user_text'],
                        'project_id': state['project_id'], 'existing': existing})
                    self.ledger.apply_job(job['turn_id'], job['lease'], candidates)
                except Exception:
                    self.ledger.fail_job(job['turn_id'], job['lease'])
                    self.status = 'delayed'
                    return
        self.status = 'idle'

    def _run(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:
                self.status = 'delayed'
            # At most one extraction per tick. No tight retry loop or unbounded
            # GPU occupancy; state/lease survives process interruption.
            self.stop_event.wait(10)

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, name='okal-memory', daemon=True)
            self.thread.start()

    def stop(self):
        self.stop_event.set()
        # A local request has a bounded timeout. Terminate the child to release
        # any index locks promptly; the job lease/outbox will recover on restart.
        if self.thread:
            self.thread.join(timeout=2)
        self.adapter._stop()
        if self.thread:
            self.thread.join(timeout=3)
