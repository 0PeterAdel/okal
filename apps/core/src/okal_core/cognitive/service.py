"""Bounded background ingestion and independent projection reconciliation."""
from contextlib import contextmanager
import fcntl
import os
import threading

from .process import AdapterClient, AdapterUnavailable
from .vault import Vault
from .learning import OWNER,EXTERNAL
from .ledger import SENSITIVE, CREDENTIAL_CATEGORY, CandidateConflict
from ..store import Conflict


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
        if vault_status not in {'current','not_curated'}:
            try:
                vault = Vault(self.ledger)
                result=vault.export(record) if record else vault.delete(memory_id)
                vault_status = 'not_curated' if result['status']=='not_curated' else 'current'
            except Exception:
                vault_status, error = 'failed', 'vault_conflict_or_unavailable'
        attempts = job['attempts'] + 1
        status = 'current' if index_status == 'current' and vault_status in {'current','not_curated'} else (
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
        with self.store.connect() as db:
            rebuild = dict(db.execute('SELECT * FROM memory_index_state WHERE id=1').fetchone())
        if rebuild['status']=='pending' and rebuild['available_at']<=self.ledger.now:
            try:
                self.adapter.call('reset', {})
            except AdapterUnavailable:
                with self.store.connect() as db, db:
                    db.execute('UPDATE memory_index_state SET status=?,attempts=attempts+1,available_at=? WHERE generation=?',
                        ('failed' if rebuild['attempts']>=4 else 'pending', self.ledger.now+60,rebuild['generation']))
                self.status='delayed'
                return
            with self.store.connect() as db, db:
                db.execute('BEGIN IMMEDIATE')
                for row in db.execute('''SELECT m.id,m.revision FROM chat_memories m
                    JOIN memory_meta x ON x.memory_id=m.id WHERE x.category<>'credential_quarantined' ''').fetchall():
                    self.ledger._outbox(db,row['id'],row['revision'],'upsert')
                db.execute("UPDATE memory_index_state SET status='current',attempts=0 WHERE generation=?", (rebuild['generation'],))
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
        with self.store.connect() as db:
            projects=[dict(r) for r in db.execute('''SELECT * FROM memory_project_outbox
                WHERE status='pending' AND available_at<=? ORDER BY project_id LIMIT 2''',(self.ledger.now,))]
        for project in projects:
            try:
                Vault(self.ledger).export_project(project['project_id'])
                status='current'
            except Exception:
                status='failed' if project['attempts']>=4 else 'pending'
            with self.store.connect() as db, db:
                db.execute('''UPDATE memory_project_outbox SET status=?,attempts=attempts+1,available_at=?
                    WHERE project_id=? AND revision=? AND generation=?''',(status,0 if status=='current' else self.ledger.now+60,
                        project['project_id'],project['revision'],project['generation']))
        if self.stop_event.is_set():
            return
        with mail_idle(self.store.directory) as idle:
            if not idle:
                self.status = 'waiting_for_mail'
                return
            job = self.ledger.claim_job()
            if job:
                try:
                    project_id=job['scope_project_id']
                    # Existing subject labels help Mem0 consolidate; source text
                    # and authoritative revision checks remain in Core.
                    with self.store.connect() as db:
                        existing = [dict(r) for r in db.execute(
                            'SELECT id,revision,key,kind,scope FROM chat_memories WHERE scope IN (?,?,?) '
                            'ORDER BY updated_at DESC LIMIT 16',
                            ('owner', job['conversation_id'], 'project:' + (project_id or '')))]
                    if OWNER.search(job['user_text']) and not EXTERNAL.search(job['user_text']) and not SENSITIVE.search(job['user_text']) and not CREDENTIAL_CATEGORY.search(job['user_text']):
                        # Mem0 semantic retrieval supplies consolidation subjects;
                        # Core resolves every returned ID/revision and scope.
                        hits=self.adapter.call('search',{'query':job['user_text'],'limit':8})
                        related=[r for r in self.ledger.active(hits) if r['scope'] in {
                            'owner',job['conversation_id'],'project:'+(project_id or '')}]
                        candidates=[{k:r[k] for k in ('id','revision','key','kind','scope')} for r in related]+existing
                        existing=list({r['id']:r for r in candidates}.values())[:16]
                    candidates = self.adapter.call('extract', {'message': job['user_text'],
                        'project_id': project_id, 'existing': existing})
                    self.ledger.apply_job(job['turn_id'], job['lease'], candidates)
                except Exception as exc:
                    code='candidate_subject_conflict' if isinstance(exc,CandidateConflict) else 'source_changed' if isinstance(exc,Conflict) else (
                        'local_adapter_unavailable' if isinstance(exc,AdapterUnavailable) else 'invalid_candidates')
                    self.ledger.fail_job(job['turn_id'], job['lease'],code)
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
