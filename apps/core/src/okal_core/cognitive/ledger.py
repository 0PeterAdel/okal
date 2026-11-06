"""Authoritative lifecycle on the existing chat tables, never on vector results.

chat_memories is the current view. Revisions preserve correction provenance;
forgetting erases revision contents and leaves only non-content tombstones.
Every projection is reconciled through a transactionally written outbox.
"""
from contextlib import contextmanager
import hashlib
import json
import re
import uuid

from ..store import Conflict

KINDS = {'semantic', 'episodic', 'task', 'instruction', 'decision', 'goal', 'constraint', 'lesson'}
SENSITIVE = re.compile(
    r'\b(?:password|passwd|token|secret|medical|my health|mental health|diagnos\w*|blood pressure|'
    r'diabet\w*|cancer|hiv|allerg\w*|pregnan\w*|medicat\w*|prescription|'
    r'psychiatr\w*|depress\w*|bank account|credit card|card number|account number|'
    r'routing number|iban|salary|income|social security|tax id|passport|national id)\b|'
    r'كلمة السر|كلمة المرور|حساب بنكي|بطاقة ائتمان|رقم (?:حساب|بطاقة|قومي)|'
    r'تشخيص|مرض|سكري|السكر|سرطان|حساسية|حامل|علاج|دواء|أدوية|اكتئاب|'
    r'صحة نفسية|جواز سفر|راتبي|مرتبي', re.I)
CREDENTIAL_CATEGORY = re.compile(
    r'\b(?:password|passwd|passphrase|credentials?|api[_ -]?keys?|access[_ -]?tokens?|'
    r'refresh[_ -]?tokens?|client[_ -]?secrets?|private[_ -]?keys?)\b|'
    r'كلمة\s*(?:السر|المرور)|توكن|مفتاح سري|مفتاح خاص',re.I)


def owner_view(record):
    """Withhold a legacy credential value without destroying the owner's archive."""
    result=dict(record)
    if CREDENTIAL_CATEGORY.search(result.get('key','')+' '+result.get('content','')):
        result.update(content='[Legacy credential-related memory excluded; forget to remove it.]',
                      quarantined=True,assertion='unverified',status='unverified')
    return result


def uid():
    return uuid.uuid4().hex


class CandidateConflict(ValueError):
    """Automatic extraction could not establish a matching owner subject."""


def subject_anchor(content: str, kind: str) -> str | None:
    """Narrow, literal single-value preferences; never infer arbitrary topics.

    Model-generated keys are not evidence of subject identity. These anchored
    owner statements identify a field independently of its changing value.
    Other ambiguous updates require the owner editor rather than a model guess.
    """
    if kind != 'semantic':
        return None
    match = re.match(r'^(my|our)\s+((?:preferred|favorite|favourite|default|current)\s+'
                     r'[\w -]{1,70}?)\s+is\s+\S', content.strip(), re.I)
    return re.sub(r'\s+', ' ', ' '.join(match.groups()).casefold()) if match else None


def anchor_key(anchor: str) -> str:
    label = re.sub(r'[^\w]+', '_', anchor).strip('_')[:45]
    return 'preference.' + label + '.' + hashlib.sha256(anchor.encode()).hexdigest()[:16]


def governed_subject(key: str, old: str, new: str) -> bool:
    if key in {'communication.language','communication.language.technical_docs',
               'communication.style','communication.structure','profile.name',
               'conversation.goal','project.goal','conversation.pending_work','project.pending_work'}:
        return True  # Core's exact-source validator governs these slots.
    database = r'\b(?:database|SQLite|PostgreSQL|MySQL|MariaDB|MongoDB|DuckDB)\b|قاعدة (?:ال)?بيانات'
    return key == 'architecture.database' and bool(re.search(database, old, re.I)
                                                   and re.search(database, new, re.I))


class Ledger:
    def __init__(self, intelligence):
        self.state = intelligence
        self.store = intelligence.store
        self._migrate()

    @property
    def now(self):
        return self.state.now

    @contextmanager
    def _transaction(self, external=None):
        if external is not None:
            yield external
        else:
            with self.store.connect() as db, db:
                db.execute('BEGIN IMMEDIATE')
                yield db

    def _migrate(self):
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('PRAGMA secure_delete=ON')
            db.execute('CREATE TABLE IF NOT EXISTS cognitive_schema (version INTEGER NOT NULL)')
            version = db.execute('SELECT version FROM cognitive_schema').fetchone()
            if version and version[0] != 1:
                raise ValueError('unsupported_cognitive_schema_do_not_downgrade')
            first = version is None
            if first:
                db.execute('INSERT INTO cognitive_schema VALUES(1)')
            statements = (
                '''CREATE TABLE IF NOT EXISTS memory_projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL, revision INTEGER NOT NULL,
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)''',
                '''CREATE TABLE IF NOT EXISTS memory_conversations (
                    conversation_id TEXT PRIMARY KEY REFERENCES chat_conversations(id) ON DELETE CASCADE,
                    project_id TEXT REFERENCES memory_projects(id), revision INTEGER NOT NULL DEFAULT 1,
                    state TEXT NOT NULL DEFAULT '{}', updated_at INTEGER NOT NULL)''',
                '''CREATE TABLE IF NOT EXISTS memory_turn_projects (
                    turn_id TEXT PRIMARY KEY REFERENCES chat_turns(id) ON DELETE CASCADE,
                    project_id TEXT REFERENCES memory_projects(id) ON DELETE SET NULL,
                    revision INTEGER NOT NULL DEFAULT 1)''',
                '''CREATE TABLE IF NOT EXISTS memory_meta (
                    memory_id TEXT PRIMARY KEY REFERENCES chat_memories(id) ON DELETE CASCADE,
                    project_id TEXT REFERENCES memory_projects(id),
                    assertion TEXT NOT NULL CHECK(assertion IN ('remembered','inferred','unverified')),
                    category TEXT NOT NULL, extractor TEXT NOT NULL)''',
                '''CREATE TABLE IF NOT EXISTS memory_versions (
                    memory_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    snapshot TEXT, status TEXT NOT NULL,
                    created_at INTEGER NOT NULL, PRIMARY KEY(memory_id,revision))''',
                '''CREATE TABLE IF NOT EXISTS memory_evidence (
                    memory_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    turn_id TEXT NOT NULL REFERENCES chat_turns(id) ON DELETE CASCADE,
                    quote TEXT NOT NULL, PRIMARY KEY(memory_id,revision,turn_id))''',
                '''CREATE TABLE IF NOT EXISTS memory_tombstones (
                    memory_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    deleted_at INTEGER NOT NULL)''',
                '''CREATE TABLE IF NOT EXISTS memory_subject_tombstones (
                    subject_hash TEXT PRIMARY KEY, cutoff_seq INTEGER NOT NULL)''',
                '''CREATE TABLE IF NOT EXISTS memory_outbox (
                    memory_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    operation TEXT NOT NULL CHECK(operation IN ('upsert','delete')),
                    status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                    available_at INTEGER NOT NULL DEFAULT 0, error TEXT,
                    updated_at INTEGER NOT NULL)''',
                '''CREATE TABLE IF NOT EXISTS memory_jobs (
                    turn_id TEXT PRIMARY KEY REFERENCES chat_turns(id) ON DELETE CASCADE,
                    digest TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0, lease TEXT, lease_until INTEGER,
                    available_at INTEGER NOT NULL DEFAULT 0, error TEXT,
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)''',
                '''CREATE INDEX IF NOT EXISTS memory_jobs_ready
                    ON memory_jobs(status,available_at,created_at)''',
                '''CREATE TABLE IF NOT EXISTS memory_turn_sources (
                    turn_id TEXT NOT NULL REFERENCES chat_turns(id) ON DELETE CASCADE,
                    source_turn TEXT NOT NULL REFERENCES chat_turns(id) ON DELETE CASCADE,
                    PRIMARY KEY(turn_id,source_turn))''',
                '''CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    memory_id UNINDEXED, key, content, tokenize='unicode61 remove_diacritics 2')''',
            )
            for statement in statements:
                db.execute(statement)
            db.execute('''CREATE TABLE IF NOT EXISTS memory_project_outbox (
                project_id TEXT PRIMARY KEY REFERENCES memory_projects(id) ON DELETE CASCADE,
                revision INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0, available_at INTEGER NOT NULL DEFAULT 0,
                generation INTEGER NOT NULL DEFAULT 1)''')
            if 'generation' not in {r['name'] for r in db.execute('PRAGMA table_info(memory_project_outbox)')}:
                db.execute('ALTER TABLE memory_project_outbox ADD COLUMN generation INTEGER NOT NULL DEFAULT 1')
            db.execute('''INSERT OR IGNORE INTO memory_project_outbox(project_id,revision)
                SELECT id,revision FROM memory_projects''')
            archive_exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='chat_archive_fts'").fetchone()
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chat_archive_fts USING fts5(user_text,response,content='chat_turns',content_rowid='seq')")
            db.execute('''CREATE TRIGGER IF NOT EXISTS chat_archive_insert AFTER INSERT ON chat_turns BEGIN
                INSERT INTO chat_archive_fts(rowid,user_text,response) VALUES(new.seq,new.user_text,new.response); END''')
            db.execute('''CREATE TRIGGER IF NOT EXISTS chat_archive_delete AFTER DELETE ON chat_turns BEGIN
                INSERT INTO chat_archive_fts(chat_archive_fts,rowid,user_text,response)
                VALUES('delete',old.seq,old.user_text,old.response); END''')
            db.execute('''CREATE TRIGGER IF NOT EXISTS chat_archive_update AFTER UPDATE ON chat_turns BEGIN
                INSERT INTO chat_archive_fts(chat_archive_fts,rowid,user_text,response)
                VALUES('delete',old.seq,old.user_text,old.response);
                INSERT INTO chat_archive_fts(rowid,user_text,response) VALUES(new.seq,new.user_text,new.response); END''')
            if not archive_exists:
                db.execute("INSERT INTO chat_archive_fts(chat_archive_fts) VALUES('rebuild')")
            db.execute('CREATE TABLE IF NOT EXISTS memory_clock (id INTEGER PRIMARY KEY CHECK(id=1),seq INTEGER NOT NULL)')
            db.execute('INSERT OR IGNORE INTO memory_clock VALUES(1,0)')
            db.execute('''CREATE TABLE IF NOT EXISTS memory_index_state (
                id INTEGER PRIMARY KEY CHECK(id=1),generation INTEGER NOT NULL,
                status TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,available_at INTEGER NOT NULL DEFAULT 0)''')
            db.execute("INSERT OR IGNORE INTO memory_index_state(id,generation,status) VALUES(1,1,'current')")
            columns = {r['name'] for r in db.execute('PRAGMA table_info(memory_outbox)')}
            for column in ('index_status', 'vault_status'):
                if column not in columns:
                    db.execute('ALTER TABLE memory_outbox ADD COLUMN ' + column + " TEXT NOT NULL DEFAULT 'pending'")
            for table, additions in {
                'memory_meta': {'write_seq': 0, 'effective_seq': 0},
                'memory_jobs': {'source_seq': 0, 'basis_seq': 0, 'project_revision': 0},
            }.items():
                columns = {r['name'] for r in db.execute('PRAGMA table_info(' + table + ')')}
                for column, default in additions.items():
                    if column not in columns:
                        db.execute('ALTER TABLE ' + table + ' ADD COLUMN ' + column +
                                   ' INTEGER NOT NULL DEFAULT ' + str(default))
            anchors_new = 'subject_anchor' not in {r['name'] for r in db.execute('PRAGMA table_info(memory_meta)')}
            if anchors_new:
                db.execute('ALTER TABLE memory_meta ADD COLUMN subject_anchor TEXT')
            db.execute('CREATE INDEX IF NOT EXISTS memory_subject_anchor ON memory_meta(subject_anchor)')
            columns = {r['name'] for r in db.execute('PRAGMA table_info(memory_jobs)')}
            if 'scope_project_id' not in columns:
                db.execute('ALTER TABLE memory_jobs ADD COLUMN scope_project_id TEXT')
            if first:
                # Stage 1 did not retain transitive archive dependencies. Its
                # completed turns consumed preceding completed chat context.
                # A conservative chronological chain preserves forgetting's
                # privacy fence without deleting unrelated owner messages.
                db.execute('''INSERT OR IGNORE INTO memory_turn_sources(turn_id,source_turn)
                    SELECT turn_id,source_turn FROM (
                        SELECT id AS turn_id,LAG(id) OVER (
                            PARTITION BY conversation_id ORDER BY seq) AS source_turn
                        FROM chat_turns WHERE status='complete') WHERE source_turn IS NOT NULL''')
                # Owner requested keep-until-deleted. The former default 90
                # cannot be distinguished from an explicitly selected 90 in v1.
                # Preserve other finite policies; document this migration.
                db.execute('UPDATE chat_settings SET retention_days=0 WHERE retention_days=90')
                # Stage 1 also used a default 365-day memory lifetime, without
                # recording whether it was explicitly selected. Preserve other
                # finite policies, but do not silently expire enduring facts at
                # the obsolete default after the owner requested indefinite
                # retention. The owner can explicitly select 365 again.
                db.execute('UPDATE chat_memories SET expires_at=0 WHERE expires_at=updated_at+365*86400')
                for row in db.execute('SELECT * FROM chat_memories').fetchall():
                    record = dict(row)
                    if record['key'] in {'language','preferred language'} and not db.execute(
                            'SELECT 1 FROM chat_memories WHERE scope=? AND key=?',
                            (record['scope'],'communication.language')).fetchone():
                        record['key']='communication.language'
                        db.execute('UPDATE chat_memories SET key=? WHERE id=?',(record['key'],record['id']))
                    origin=db.execute('SELECT seq FROM chat_turns WHERE id=?',(record['source_turn'],)).fetchone()
                    cutoff=origin[0] if origin else db.execute(
                        'SELECT COALESCE(MAX(seq),0) FROM chat_turns WHERE created_at<=?',(record['updated_at'],)).fetchone()[0]
                    # Historical jobs and migrated evidence share chronological
                    # ordering. A later archived correction must beat an older
                    # source; new V2 owner-editor revisions still outrank backfill.
                    db.execute('''INSERT INTO memory_meta(memory_id,project_id,assertion,category,extractor,effective_seq)
                        VALUES(?,NULL,?,?,?,?)''',
                               (record['id'], 'unverified' if CREDENTIAL_CATEGORY.search(record['key']+' '+record['content']) else 'remembered',
                                'credential_quarantined' if CREDENTIAL_CATEGORY.search(record['key']+' '+record['content']) else record['kind'],
                                'stage1-migration',cutoff-(1<<62)))
                    self._snapshot(db, record)
                    unsafe=bool(CREDENTIAL_CATEGORY.search(record['key']+' '+record['content']))
                    self._outbox(db, row['id'], row['revision'], 'delete' if unsafe else 'upsert')
                    if not unsafe:self._fts(db, record)
                    if row['source_turn']:
                        db.execute('INSERT OR IGNORE INTO memory_evidence VALUES(?,?,?,?)',
                                   (row['id'], row['revision'], row['source_turn'], row['content']))
                self._backfill(db, limit=500)
            if anchors_new:
                for row in db.execute('SELECT id,content,kind FROM chat_memories').fetchall():
                    db.execute('UPDATE memory_meta SET subject_anchor=? WHERE memory_id=?',
                               (subject_anchor(row['content'],row['kind']),row['id']))
            # Old Core must refuse to run against an upgraded lifecycle.
            db.execute('UPDATE chat_schema SET version=2')

    def _snapshot(self, db, record):
        db.execute("UPDATE memory_versions SET status='superseded' WHERE memory_id=? AND status='current'",
                   (record['id'],))
        db.execute('INSERT INTO memory_versions VALUES(?,?,?,?,?)', (
            record['id'], record['revision'], json.dumps(record, ensure_ascii=False), 'current', self.now))

    def _next_seq(self, db):
        db.execute('UPDATE memory_clock SET seq=seq+1 WHERE id=1')
        return db.execute('SELECT seq FROM memory_clock WHERE id=1').fetchone()[0]

    def _fts(self, db, record):
        db.execute('DELETE FROM memory_fts WHERE memory_id=?', (record['id'],))
        db.execute('INSERT INTO memory_fts VALUES(?,?,?)',
                   (record['id'], record['key'], record['content']))

    def _outbox(self, db, memory_id, revision, operation):
        db.execute('''UPDATE memory_project_outbox SET status='pending',attempts=0,available_at=0,generation=generation+1
            WHERE project_id IN (SELECT project_id FROM memory_meta WHERE memory_id=?)''',(memory_id,))
        db.execute('''INSERT INTO memory_outbox(memory_id,revision,operation,updated_at)
            VALUES(?,?,?,?) ON CONFLICT(memory_id) DO UPDATE SET
            revision=excluded.revision,operation=excluded.operation,status='pending',
            attempts=0,available_at=0,error=NULL,index_status='pending',vault_status='pending',
            updated_at=excluded.updated_at''',
                   (memory_id, revision, operation, self.now))

    def save(self, key, content, kind='semantic', conversation_id=None,
             source_turn=None, revision=0, days=0, *, project_id=None,
             assertion='remembered', extractor='owner-editor', _db=None, _source_seq=None):
        from ..intelligence import text, identifier, Missing
        key, content = text(key, 80).casefold(), text(content, 600)
        if CREDENTIAL_CATEGORY.search(key+' '+content):
            raise ValueError('credential_memory_forbidden_even_with_sensitive_consent')
        if SENSITIVE.search(content) and extractor not in {
                'owner-confirmed-sensitive-editor','owner-confirmed-vault-edit'}:
            raise ValueError('sensitive_memory_requires_explicit_editor_confirmation')
        if (kind not in KINDS or assertion not in {'remembered', 'inferred', 'unverified'}
                or type(revision) is not int or revision < 0
                or type(days) is not int or not 0 <= days <= 365):
            raise ValueError('invalid_memory_metadata')
        for value in (conversation_id, project_id, source_turn):
            if value is not None:
                identifier(value)
        if conversation_id and project_id:
            raise ValueError('choose_conversation_or_project_scope')
        scope = conversation_id or ('project:' + project_id if project_id else 'owner')
        with self._transaction(_db) as db:
            if _db is None:
                self.state._prune(db)
            if conversation_id and not db.execute('SELECT 1 FROM chat_conversations WHERE id=?',
                                                  (conversation_id,)).fetchone():
                raise Missing('conversation_not_found')
            if project_id and not db.execute('SELECT 1 FROM memory_projects WHERE id=?',
                                             (project_id,)).fetchone():
                raise Missing('project_not_found')
            if source_turn:
                source = db.execute('SELECT user_text FROM chat_turns WHERE id=?', (source_turn,)).fetchone()
                if not source or content not in source[0] or source[0] == '[forgotten]':
                    raise ValueError('memory_must_quote_owner_source')
            old = db.execute('SELECT * FROM chat_memories WHERE scope=? AND key=?', (scope, key)).fetchone()
            if old and old['content'] == content and old['kind'] == kind:
                if revision in (0, old['revision'] - 1):
                    if source_turn:
                        db.execute('INSERT OR IGNORE INTO memory_evidence VALUES(?,?,?,?)',
                                   (old['id'],old['revision'],source_turn,content))
                    return dict(old)
            if (old and revision != old['revision']) or (not old and revision != 0):
                raise Conflict('memory_revision_conflict')
            record = dict(id=old['id'] if old else uid(), kind=kind, key=key,
                          content=content, scope=scope, conversation_id=conversation_id,
                          source_turn=source_turn, source='owner_message' if source_turn else 'owner_editor',
                          confidence=1 if assertion == 'remembered' else 0.5,
                          revision=revision + 1, created_at=old['created_at'] if old else self.now,
                          updated_at=self.now, expires_at=self.now + days * 86400 if days else 0)
            if old:
                # A correction must fence in-flight responses that read the old
                # revision, but never erase the owner's earlier discussion.
                db.execute("UPDATE chat_turns SET lease=NULL,lease_until=NULL,status='failed' "
                           "WHERE status='running' AND id IN "
                           '(SELECT turn_id FROM chat_sources WHERE memory_id=?)', (old['id'],))
            columns = ','.join(record)
            db.execute('INSERT INTO chat_memories(' + columns + ') VALUES(' +
                       ','.join(':' + k for k in record) + ') ON CONFLICT(id) DO UPDATE SET ' +
                       ','.join(k + '=excluded.' + k for k in record if k != 'id'), record)
            write_seq = self._next_seq(db)
            db.execute('''INSERT INTO memory_meta(memory_id,project_id,assertion,category,extractor,write_seq,effective_seq,subject_anchor)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(memory_id) DO UPDATE SET project_id=excluded.project_id,
                assertion=excluded.assertion,category=excluded.category,extractor=excluded.extractor,
                write_seq=excluded.write_seq,effective_seq=excluded.effective_seq,subject_anchor=excluded.subject_anchor''',
                       (record['id'], project_id, assertion, kind, extractor, write_seq,
                        _source_seq if _source_seq is not None else write_seq,subject_anchor(content,kind)))
            self._snapshot(db, record)
            if source_turn:
                db.execute('INSERT OR IGNORE INTO memory_evidence VALUES(?,?,?,?)',
                           (record['id'], record['revision'], source_turn, content))
            self._outbox(db, record['id'], record['revision'], 'upsert')
            self._fts(db, record)
            return record

    def forget(self, db, memory_id):
        """Forget shared text/support iteratively; no surviving facet may replay it."""
        pending=[memory_id];seen=set()
        while pending:
            current=pending.pop()
            if current in seen:continue
            seen.add(current)
            pending.extend(self._forget_one(db,current))

    def _forget_one(self, db, memory_id):
        from ..intelligence import identifier
        identifier(memory_id)
        row = db.execute('SELECT revision,content,scope,key FROM chat_memories WHERE id=?', (memory_id,)).fetchone()
        if row is None:
            return []
        evidence = db.execute('SELECT turn_id,quote FROM memory_evidence WHERE memory_id=?',
                              (memory_id,)).fetchall()
        affected = {r[0] for r in db.execute('SELECT turn_id FROM chat_sources WHERE memory_id=?', (memory_id,))}
        quotes = {r['quote'] for r in evidence} | {row['content']}
        quotes.update(json.loads(r[0])['content'] for r in db.execute(
            'SELECT snapshot FROM memory_versions WHERE memory_id=? AND snapshot IS NOT NULL',(memory_id,)))
        # Preserve independent facts, but remember which current facts had
        # source support before redaction. Losing that last support cannot
        # leave another active memory of an erased passage behind.
        supported={r['memory_id'] for r in db.execute('''SELECT DISTINCT e.memory_id
            FROM memory_evidence e JOIN chat_memories m ON m.id=e.memory_id AND m.revision=e.revision
            JOIN chat_turns t ON t.id=e.turn_id WHERE instr(t.user_text,e.quote)>0''')}
        invalidated = set(affected)
        redacted=set()
        # Exact source spans are removed throughout the archive. Other owner
        # sentences survive; dependent assistant responses are invalidated.
        for turn in db.execute('SELECT id,user_text,conversation_id FROM chat_turns').fetchall():
            cleaned = turn['user_text']
            for quote in sorted(quotes, key=len, reverse=True):
                cleaned = cleaned.replace(quote, '[forgotten]')
            changed = cleaned != turn['user_text']
            if changed or turn['id'] in affected:
                if changed:redacted.add(turn['id'])
                invalidated.add(turn['id'])
                db.execute("UPDATE chat_turns SET user_text=?,response=NULL,status='failed',"
                           'lease=NULL,lease_until=NULL,digest=? WHERE id=?', (
                    cleaned, hashlib.sha256(cleaned.encode()).hexdigest(), turn['id']))
                db.execute("UPDATE memory_jobs SET status='forgotten',lease=NULL,lease_until=NULL "
                           'WHERE turn_id=?', (turn['id'],))
                db.execute("UPDATE chat_conversations SET title='Conversation (redacted)' WHERE id=?",
                           (turn['conversation_id'],))
                # Derived per-chat summaries may paraphrase the fact.
                db.execute("UPDATE memory_conversations SET state='{}',revision=revision+1 WHERE conversation_id=?",
                           (turn['conversation_id'],))
        self.invalidate_sources(db, invalidated)
        surviving={r['memory_id'] for r in db.execute('''SELECT DISTINCT e.memory_id
            FROM memory_evidence e JOIN chat_memories m ON m.id=e.memory_id AND m.revision=e.revision
            JOIN chat_turns t ON t.id=e.turn_id WHERE instr(t.user_text,e.quote)>0''')}
        related=[r['id'] for r in db.execute('SELECT id,content FROM chat_memories WHERE id<>?',(memory_id,))
                 if r['id'] in supported-surviving or any(quote in r['content'] for quote in quotes)]
        removed=db.execute('''SELECT DISTINCT e.memory_id,e.revision FROM memory_evidence e
            JOIN chat_turns t ON t.id=e.turn_id WHERE e.turn_id IN (SELECT value FROM json_each(?))
            AND instr(t.user_text,e.quote)=0''',(json.dumps(list(redacted)),)).fetchall()
        db.execute('''DELETE FROM memory_evidence WHERE turn_id IN (SELECT value FROM json_each(?))
            AND NOT EXISTS(SELECT 1 FROM chat_turns t WHERE t.id=turn_id AND instr(t.user_text,quote)>0)''',
            (json.dumps(list(redacted)),))
        for version in db.execute('SELECT memory_id,revision,snapshot FROM memory_versions WHERE snapshot IS NOT NULL').fetchall():
            content=json.loads(version['snapshot'])['content']
            lost_support=any(r['memory_id']==version['memory_id'] and r['revision']==version['revision'] for r in removed) and not db.execute(
                'SELECT 1 FROM memory_evidence WHERE memory_id=? AND revision=? LIMIT 1',
                (version['memory_id'],version['revision'])).fetchone()
            if lost_support or any(quote in content for quote in quotes):
                db.execute("UPDATE memory_versions SET snapshot=NULL,status='deleted' WHERE memory_id=? AND revision=?",
                           (version['memory_id'],version['revision']))
        for other in db.execute('''SELECT m.* FROM chat_memories m JOIN chat_turns t ON t.id=m.source_turn
            WHERE m.source_turn IN (SELECT value FROM json_each(?)) AND instr(t.user_text,m.content)=0''',
            (json.dumps(list(redacted)),)).fetchall():
            if other['id']==memory_id or other['id'] in related:continue
            alternative=db.execute('''SELECT e.turn_id FROM memory_evidence e JOIN chat_turns t ON t.id=e.turn_id
                WHERE e.memory_id=? AND e.revision=? AND instr(t.user_text,e.quote)>0 ORDER BY t.seq DESC LIMIT 1''',
                (other['id'],other['revision'])).fetchone()
            if alternative:self._revise_source(db,other,alternative['turn_id'])
        db.execute('UPDATE memory_versions SET snapshot=NULL,status=\'deleted\' WHERE memory_id=?', (memory_id,))
        db.execute('DELETE FROM memory_evidence WHERE memory_id=?', (memory_id,))
        db.execute('DELETE FROM memory_fts WHERE memory_id=?', (memory_id,))
        db.execute("INSERT INTO memory_fts(memory_fts) VALUES('optimize')")
        db.execute("INSERT INTO chat_archive_fts(chat_archive_fts) VALUES('optimize')")
        db.execute('''UPDATE memory_project_outbox SET status='pending',attempts=0,available_at=0,generation=generation+1
            WHERE project_id IN (SELECT project_id FROM memory_meta WHERE memory_id=?)''',(memory_id,))
        db.execute('DELETE FROM chat_memories WHERE id=?', (memory_id,))
        revision = row['revision'] + 1
        db.execute('INSERT OR REPLACE INTO memory_tombstones VALUES(?,?,?)', (memory_id, revision, self.now))
        subjects = {row['key']} | {anchor_key(anchor) for quote in quotes
                                   if (anchor := subject_anchor(quote,'semantic')) is not None}
        cutoff = self._next_seq(db)
        for subject in subjects:
            subject_hash = hashlib.sha256((row['scope'] + '\0' + subject).encode()).hexdigest()
            db.execute('INSERT OR REPLACE INTO memory_subject_tombstones VALUES(?,?)', (subject_hash,cutoff))
        self._outbox(db, memory_id, revision, 'delete')
        return related

    def invalidate_sources(self, db, turn_ids):
        """Fence transitive archive/history consumers without erasing owner text."""
        dependents = db.execute('''WITH RECURSIVE affected(id) AS (
            SELECT value FROM json_each(?) UNION
            SELECT s.turn_id FROM memory_turn_sources s JOIN affected a ON s.source_turn=a.id)
            SELECT id FROM affected''', (json.dumps(list(turn_ids)),)).fetchall()
        for dependent in dependents:
            db.execute("UPDATE chat_turns SET response=NULL,status='failed',lease=NULL,lease_until=NULL WHERE id=?",
                       (dependent[0],))
            # Its owner message remains evidence, but a late worker must
            # not finish against the invalidated context/source generation.
            db.execute("UPDATE memory_jobs SET status='forgotten',lease=NULL,lease_until=NULL WHERE turn_id=?",
                       (dependent[0],))

    def deleting_history(self, db, conversation_id):
        sources = {r[0] for r in db.execute('SELECT id FROM chat_turns WHERE conversation_id=?', (conversation_id,))}
        sources.update(r[0] for r in db.execute('''SELECT s.turn_id FROM chat_sources s
            JOIN memory_evidence e ON e.memory_id=s.memory_id JOIN chat_turns t ON t.id=e.turn_id
            WHERE t.conversation_id=?''', (conversation_id,)))
        self.invalidate_sources(db, sources)
        # Current facts with another source survive; old snapshots tied to the
        # deleted source do not remain as a hidden competing history.
        db.execute('''UPDATE memory_versions SET snapshot=NULL,status='deleted' WHERE (memory_id,revision) IN
            (SELECT memory_id,revision FROM memory_evidence WHERE turn_id IN
            (SELECT id FROM chat_turns WHERE conversation_id=?))''', (conversation_id,))
        for row in db.execute('SELECT conversation_id,state FROM memory_conversations').fetchall():
            state = json.loads(row['state'])
            cleaned = {k:v for k,v in state.items() if v.get('turn_id') not in sources}
            if cleaned != state:
                db.execute('UPDATE memory_conversations SET state=?,revision=revision+1 WHERE conversation_id=?',
                           (json.dumps(cleaned,ensure_ascii=False),row['conversation_id']))

    def retain_independent_source(self, db, memory_id, deleted_conversation):
        """Deleting one chat is not forgetting a fact restated in another chat."""
        row=db.execute('SELECT * FROM chat_memories WHERE id=?',(memory_id,)).fetchone()
        if row is None or row['conversation_id']==deleted_conversation:
            return False
        alternative=db.execute('''SELECT e.turn_id FROM memory_evidence e JOIN chat_turns t ON t.id=e.turn_id
            WHERE e.memory_id=? AND e.revision=? AND t.conversation_id<>?
            AND instr(t.user_text,e.quote)>0 ORDER BY t.seq DESC LIMIT 1''',
            (memory_id,row['revision'],deleted_conversation)).fetchone()
        if alternative is None:
            return False
        self._revise_source(db,row,alternative[0])
        return True

    def _revise_source(self, db, row, source_turn):
        memory_id=row['id']
        record=dict(row,source_turn=source_turn,revision=row['revision']+1,updated_at=self.now)
        db.execute('UPDATE chat_memories SET source_turn=?,revision=?,updated_at=? WHERE id=?',
                   (record['source_turn'],record['revision'],self.now,memory_id))
        db.execute('UPDATE memory_meta SET write_seq=? WHERE memory_id=?',(self._next_seq(db),memory_id))
        self._snapshot(db,record)
        db.execute('INSERT INTO memory_evidence VALUES(?,?,?,?)',
                   (memory_id,record['revision'],record['source_turn'],record['content']))
        self._outbox(db,memory_id,record['revision'],'upsert')

    def _backfill(self, db, limit=100):
        rows = db.execute("SELECT t.id,t.digest,t.seq FROM chat_turns t LEFT JOIN memory_jobs j "
                          "ON j.turn_id=t.id WHERE t.status IN ('complete','failed') AND t.response IS NOT NULL AND j.turn_id IS NULL "
                          "ORDER BY t.seq LIMIT ?", (limit,)).fetchall()
        for row in rows:
            # A stable negative sequence orders historical turns before new
            # live edits, without timestamp ties or changing batch offsets.
            db.execute('INSERT OR IGNORE INTO memory_jobs(turn_id,digest,created_at,updated_at,source_seq) VALUES(?,?,?,?,?)',
                       (row['id'], row['digest'], self.now, self.now, row['seq'] - (1 << 62)))
        return len(rows)

    def enqueue(self, db, turn_id):
        if db.execute("SELECT 1 FROM chat_turns WHERE id=? AND status IN ('complete','failed') AND response IS NOT NULL", (turn_id,)).fetchone() and not db.execute(
                'SELECT 1 FROM memory_jobs WHERE turn_id=?', (turn_id,)).fetchone():
            db.execute('''INSERT INTO memory_jobs(turn_id,digest,created_at,updated_at,source_seq)
                SELECT id,digest,?,?,? FROM chat_turns WHERE id=?''',
                       (self.now, self.now, self._next_seq(db), turn_id))

    def backfill(self, limit=100):
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError('invalid_backfill_batch')
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            return {'enqueued': self._backfill(db, limit)}

    def versions(self, memory_id):
        from ..intelligence import identifier
        identifier(memory_id)
        with self.store.connect() as db:
            current=db.execute('SELECT key,content FROM chat_memories WHERE id=?',(memory_id,)).fetchone()
            unsafe=current and CREDENTIAL_CATEGORY.search(current['key']+' '+current['content'])
            sources=[dict(r) for r in db.execute('''SELECT e.turn_id,e.quote,t.conversation_id,t.created_at
                                  FROM memory_evidence e JOIN chat_turns t ON t.id=e.turn_id
                                  WHERE e.memory_id=? ORDER BY e.revision DESC LIMIT 100''', (memory_id,))]
            for source in sources:
                if unsafe or CREDENTIAL_CATEGORY.search(source['quote']):
                    source['quote']='[Credential-related legacy source withheld.]'
            return {'sources':sources,
                    'items': [dict(r, snapshot=owner_view(json.loads(r['snapshot'])) if r['snapshot'] else None)
                              for r in db.execute('SELECT * FROM memory_versions WHERE memory_id=? '
                                                  'ORDER BY revision DESC LIMIT 100', (memory_id,))]}

    def active(self, ids: list[dict]):
        """No stale vector, forged scope or stale vault revision gains authority."""
        from ..intelligence import identifier
        if not isinstance(ids,list) or len(ids) > 24:
            raise ValueError('retrieval_result_budget')
        result = []
        with self.store.connect() as db:
            for candidate in ids:
                if not isinstance(candidate,dict):
                    raise ValueError('invalid_retrieval_reference')
                identifier(candidate.get('id'))
                if type(candidate.get('revision')) is not int or candidate['revision'] < 1:
                    raise ValueError('invalid_retrieval_revision')
                row = db.execute('''SELECT m.*,x.project_id,x.assertion,x.effective_seq FROM chat_memories m
                    JOIN memory_meta x ON x.memory_id=m.id LEFT JOIN memory_tombstones t ON t.memory_id=m.id
                    WHERE m.id=? AND m.revision=? AND t.memory_id IS NULL
                    AND (m.expires_at=0 OR m.expires_at>?)''',
                    (candidate.get('id'), candidate.get('revision'), self.now)).fetchone()
                if row and not CREDENTIAL_CATEGORY.search(row['key']+' '+row['content']):
                    result.append(dict(row))
        return result

    def health(self):
        with self.store.connect() as db:
            counts = lambda table: {r[0]: r[1] for r in db.execute('SELECT status,COUNT(*) FROM ' + table + ' GROUP BY status')}
            worker = getattr(self.store, 'memory_worker', None)
            return {'schema': 1, 'jobs': counts('memory_jobs'), 'projections': counts('memory_outbox'),
                    'index': {r[0]:r[1] for r in db.execute('SELECT index_status,COUNT(*) FROM memory_outbox GROUP BY index_status')},
                    'vault': {r[0]:r[1] for r in db.execute('SELECT vault_status,COUNT(*) FROM memory_outbox GROUP BY vault_status')},
                    'project_vault': counts('memory_project_outbox'),
                    'worker': worker.status if worker else 'not_started',
                    'configured': (self.store.directory/'cognitive.json').exists(),
                    'rebuild': dict(db.execute('SELECT generation,status,attempts FROM memory_index_state WHERE id=1').fetchone()),
                    'active': db.execute("SELECT COUNT(*) FROM memory_meta WHERE category<>'credential_quarantined'").fetchone()[0],
                    'quarantined':db.execute("SELECT COUNT(*) FROM memory_meta WHERE category='credential_quarantined'").fetchone()[0],
                    'deleted': db.execute('SELECT COUNT(*) FROM memory_tombstones').fetchone()[0],
                    'deferred_subjects': db.execute("SELECT COUNT(*) FROM memory_jobs WHERE "
                        "error='candidate_subject_conflict' AND status IN ('pending','failed')").fetchone()[0]}

    def browse(self, status='current', offset=0):
        if status not in {'current','superseded','deleted','inferred','unverified'} or type(offset) is not int or not 0 <= offset <= 1_000_000:
            raise ValueError('invalid_memory_browser_filter')
        with self.store.connect() as db:
            if status in {'current','inferred','unverified'}:
                rows = db.execute('''SELECT m.*,x.assertion,x.project_id FROM chat_memories m JOIN memory_meta x ON x.memory_id=m.id
                    WHERE (?='current' OR x.assertion=?) AND (m.expires_at=0 OR m.expires_at>?)
                    ORDER BY m.updated_at DESC,m.id LIMIT 51 OFFSET ?''', (status,status,self.now,offset)).fetchall()
                items = [owner_view(dict(r,status=r['assertion'])) for r in rows[:50]]
            else:
                rows = db.execute('SELECT * FROM memory_versions WHERE status=? ORDER BY created_at DESC,memory_id,revision DESC LIMIT 51 OFFSET ?',
                                  (status,offset)).fetchall()
                items = [dict(r,snapshot=owner_view(json.loads(r['snapshot'])) if r['snapshot'] else None) for r in rows[:50]]
            return {'items':items, 'next_offset':offset+50 if len(rows)>50 else None}

    def projects(self, offset=0, conversation_id=None):
        from ..intelligence import identifier
        if type(offset) is not int or not 0<=offset<=1_000_000:
            raise ValueError('invalid_project_cursor')
        if conversation_id is not None:identifier(conversation_id)
        with self.store.connect() as db:
            rows=db.execute('SELECT * FROM memory_projects ORDER BY updated_at DESC,id LIMIT 201 OFFSET ?',
                            (offset,)).fetchall()
            items=[dict(r) for r in rows[:200]]
            if conversation_id is not None and offset==0:
                active=db.execute('''SELECT p.* FROM memory_projects p JOIN memory_conversations c
                    ON c.project_id=p.id WHERE c.conversation_id=?''',(conversation_id,)).fetchone()
                if active and active['id'] not in {r['id'] for r in items}:items.append(dict(active))
            return {'items':items,'next_offset':offset+200 if len(rows)>200 else None}

    def save_project(self, name, description='', project_id=None, revision=0):
        from ..intelligence import text, identifier
        name = text(name, 100)
        description = text(description, 600) if description else ''
        if CREDENTIAL_CATEGORY.search(name+' '+description):
            raise ValueError('credential_project_note_forbidden')
        if SENSITIVE.search(name+' '+description):
            raise ValueError('sensitive_project_note_use_confirmed_memory_editor')
        if type(revision) is not int or revision < 0:
            raise ValueError('invalid_project_revision')
        if project_id:
            identifier(project_id)
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM memory_projects WHERE id=?', (project_id,)).fetchone()
            if (old is None and (project_id or revision != 0)) or (old and old['revision'] != revision):
                raise Conflict('project_revision_conflict')
            duplicate = db.execute('SELECT id FROM memory_projects WHERE name_key=?', (name.casefold(),)).fetchone()
            if duplicate and duplicate[0] != project_id:
                raise Conflict('project_name_already_exists_choose_explicit_project')
            result = dict(id=project_id or uid(), name=name, name_key=name.casefold(),
                          description=description, revision=revision + 1,
                          created_at=old['created_at'] if old else self.now, updated_at=self.now)
            db.execute('''INSERT INTO memory_projects VALUES(:id,:name,:name_key,:description,
                :revision,:created_at,:updated_at) ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                name_key=excluded.name_key,description=excluded.description,revision=excluded.revision,
                updated_at=excluded.updated_at''', result)
            db.execute('''INSERT INTO memory_project_outbox(project_id,revision) VALUES(?,?)
                ON CONFLICT(project_id) DO UPDATE SET revision=excluded.revision,status='pending',
                generation=memory_project_outbox.generation+1,attempts=0,available_at=0''', (result['id'],result['revision']))
            return result

    def associate(self, conversation_id, project_id=None, revision=0, *, include_history=True):
        from ..intelligence import identifier, Missing
        identifier(conversation_id)
        if project_id:
            identifier(project_id)
        if type(revision) is not int or revision < 0:
            raise ValueError('invalid_association_revision')
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM chat_conversations WHERE id=?', (conversation_id,)).fetchone():
                raise Missing('conversation_not_found')
            if project_id and not db.execute('SELECT 1 FROM memory_projects WHERE id=?', (project_id,)).fetchone():
                raise Missing('project_not_found')
            old = db.execute('SELECT * FROM memory_conversations WHERE conversation_id=?', (conversation_id,)).fetchone()
            if revision != (old['revision'] if old else 0):
                raise Conflict('conversation_state_revision_conflict')
            db.execute('''INSERT INTO memory_conversations(conversation_id,project_id,revision,updated_at)
                VALUES(?,?,?,?) ON CONFLICT(conversation_id) DO UPDATE SET project_id=excluded.project_id,
                revision=excluded.revision,updated_at=excluded.updated_at''',
                (conversation_id, project_id, revision + 1, self.now))
            if include_history and (old is None or old['project_id'] is None):
                # First explicit association may bind previously unassigned
                # source turns. Switching projects never relabels old sources.
                db.execute('''INSERT INTO memory_turn_projects(turn_id,project_id)
                    SELECT id,? FROM chat_turns WHERE conversation_id=? AND 1
                    ON CONFLICT(turn_id) DO UPDATE SET project_id=excluded.project_id,
                    revision=memory_turn_projects.revision+1 WHERE memory_turn_projects.project_id IS NULL''',
                    (project_id,conversation_id))
            db.execute('''UPDATE memory_turn_projects SET project_id=?,revision=revision+1 WHERE turn_id IN
                (SELECT j.turn_id FROM memory_jobs j JOIN chat_turns t ON t.id=j.turn_id
                WHERE j.status='scope_required' AND t.conversation_id=?)''', (project_id,conversation_id))
            db.execute("UPDATE memory_jobs SET status='pending',lease=NULL,lease_until=NULL WHERE status='scope_required' "
                       'AND turn_id IN (SELECT id FROM chat_turns WHERE conversation_id=?)', (conversation_id,))
            return {'conversation_id': conversation_id, 'project_id': project_id, 'revision': revision + 1}

    def conversation_state(self, conversation_id):
        from ..intelligence import identifier, Missing
        identifier(conversation_id)
        with self.store.connect() as db:
            if not db.execute('SELECT 1 FROM chat_conversations WHERE id=?', (conversation_id,)).fetchone():
                raise Missing('conversation_not_found')
            row = db.execute('SELECT * FROM memory_conversations WHERE conversation_id=?', (conversation_id,)).fetchone()
            return dict(row, state=json.loads(row['state'])) if row else {
                'conversation_id': conversation_id, 'project_id': None, 'revision': 0, 'state': {}}

    def claim_job(self):
        """One bounded lease; never compete with a currently running chat turn."""
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            self.state._prune(db)
            if db.execute("SELECT 1 FROM chat_turns WHERE status='running' AND lease_until>? LIMIT 1",
                          (self.now,)).fetchone():
                return None
            row = db.execute('''SELECT j.*,t.user_text,t.conversation_id FROM memory_jobs j
                JOIN chat_turns t ON t.id=j.turn_id WHERE j.attempts<5 AND j.available_at<=?
                AND (j.status='pending' OR (j.status='running' AND j.lease_until<=?))
                AND t.status IN ('complete','failed') AND t.response IS NOT NULL
                AND t.digest=j.digest ORDER BY t.seq LIMIT 1''',
                (self.now, self.now)).fetchone()
            if row is None:
                return None
            lease = uid()
            basis = db.execute('SELECT seq FROM memory_clock WHERE id=1').fetchone()[0]
            association = db.execute('SELECT project_id,revision FROM memory_turn_projects WHERE turn_id=?',
                                     (row['turn_id'],)).fetchone()
            db.execute("UPDATE memory_jobs SET status='running',attempts=attempts+1,lease=?,"
                       'lease_until=?,updated_at=?,basis_seq=?,project_revision=?,scope_project_id=? WHERE turn_id=?',
                       (lease, self.now + 140, self.now, basis, association[1] if association else 0,
                        association[0] if association else None, row['turn_id']))
            return dict(row, lease=lease, scope_project_id=association[0] if association else None)

    def fail_job(self, turn_id, lease, code='local_adapter_unavailable'):
        if code not in {'local_adapter_unavailable', 'invalid_candidates', 'candidate_subject_conflict', 'source_changed', 'projection_failed'}:
            code = 'local_adapter_unavailable'
        with self.store.connect() as db, db:
            db.execute("UPDATE memory_jobs SET status=CASE WHEN attempts>=5 THEN 'failed' ELSE 'pending' END,"
                       'error=?,lease=NULL,lease_until=NULL,available_at=?,updated_at=? '
                       "WHERE turn_id=? AND lease=? AND status='running'",
                       (code, self.now + 60, self.now, turn_id, lease))

    def apply_job(self, turn_id, lease, candidates):
        from .learning import validate_candidates
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('''SELECT j.*,t.user_text,t.conversation_id,t.digest AS current_digest,
                t.status AS turn_status,t.response AS turn_response FROM memory_jobs j JOIN chat_turns t ON t.id=j.turn_id
                WHERE j.turn_id=? AND j.lease=? AND j.status='running' AND j.lease_until>?''',
                (turn_id, lease, self.now)).fetchone()
            if (job is None or job['current_digest'] != job['digest']
                    or job['turn_status'] not in {'complete','failed'} or job['turn_response'] is None):
                raise Conflict('source_changed_or_job_lease_lost')
            association = db.execute('SELECT project_id,revision FROM memory_turn_projects WHERE turn_id=?',
                                     (turn_id,)).fetchone()
            project_id = association[0] if association else None
            if (job['project_revision'] != (association[1] if association else 0)
                    or job['scope_project_id'] != project_id):
                raise Conflict('conversation_association_changed_during_extraction')
            approved = validate_candidates(job['user_text'], candidates, project_id)
            saved = []
            state = db.execute('SELECT state FROM memory_conversations WHERE conversation_id=?',
                               (job['conversation_id'],)).fetchone()
            checkpoint = json.loads(state[0]) if state else {}
            for candidate in approved:
                scope = job['conversation_id'] if candidate['scope'] == 'conversation' else (
                    'project:' + project_id if candidate['scope'] == 'project' else 'owner')
                anchor = subject_anchor(candidate['quote'],candidate['kind'])
                if anchor:
                    matches = db.execute('''SELECT m.key FROM chat_memories m JOIN memory_meta x ON x.memory_id=m.id
                        WHERE m.scope=? AND x.subject_anchor=? LIMIT 2''',(scope,anchor)).fetchall()
                    if len(matches)>1:
                        raise CandidateConflict('ambiguous_owner_subject')
                    candidate = dict(candidate,key=matches[0]['key'] if matches else anchor_key(anchor))
                subjects = {candidate['key']} | ({anchor_key(anchor)} if anchor else set())
                if any(db.execute('SELECT 1 FROM memory_subject_tombstones WHERE subject_hash=? AND cutoff_seq>=?',
                       (hashlib.sha256((scope+'\0'+subject).encode()).hexdigest(),job['source_seq'])).fetchone()
                       for subject in subjects):
                    continue
                old = db.execute('SELECT m.*,x.write_seq,x.effective_seq FROM chat_memories m '
                                 'JOIN memory_meta x ON x.memory_id=m.id WHERE m.scope=? AND m.key=?',
                                 (scope, candidate['key'])).fetchone()
                if old and old['content'] == candidate['quote']:
                    db.execute('INSERT OR IGNORE INTO memory_evidence VALUES(?,?,?,?)',
                        (old['id'],old['revision'],turn_id,candidate['quote']))
                    continue
                if old and old['write_seq'] > job['basis_seq']:
                    raise Conflict('memory_changed_during_extraction')
                if old and old['effective_seq'] > job['source_seq']:
                    continue  # Backfill must not overwrite a later owner correction.
                if old and not (anchor and subject_anchor(old['content'],old['kind'])==anchor) and not governed_subject(
                        candidate['key'],old['content'],candidate['quote']):
                    raise CandidateConflict('candidate_subject_identity_unproven')
                if old and old['kind'] != candidate['kind'] and candidate['key'] not in {
                        'communication.language','communication.language.technical_docs',
                        'communication.style','communication.structure'}:
                    # A model's reuse of an existing key does not prove the
                    # subjects match. Never erase a decision with a goal/task.
                    # The complete source remains archived; defer visibly for
                    # bounded retry or explicit owner correction instead.
                    raise CandidateConflict('candidate_subject_kind_conflict')
                record = self.save(candidate['key'], candidate['quote'], candidate['kind'],
                    conversation_id=job['conversation_id'] if candidate['scope'] == 'conversation' else None,
                    project_id=project_id if candidate['scope'] == 'project' else None,
                    source_turn=turn_id, revision=old['revision'] if old else 0,
                    extractor='mem0-local-v1', _db=db, _source_seq=job['source_seq'])
                saved.append(record['id'])
                if candidate['scope'] != 'owner':
                    checkpoint[candidate['key']] = {'quote': candidate['quote'], 'turn_id': turn_id,
                        'kind': candidate['kind'], 'assertion': 'owner_statement', 'memory_id': record['id']}
            # State remains extractive and bounded. No model narrative becomes
            # a second history, and no owner claim becomes a verified action.
            checkpoint = dict(list(checkpoint.items())[-24:])
            db.execute('''INSERT INTO memory_conversations(conversation_id,project_id,state,updated_at)
                VALUES(?,?,?,?) ON CONFLICT(conversation_id) DO UPDATE SET state=excluded.state,
                revision=memory_conversations.revision+1,updated_at=excluded.updated_at''',
                (job['conversation_id'], project_id, json.dumps(checkpoint, ensure_ascii=False), self.now))
            db.execute("UPDATE memory_jobs SET status='done',lease=NULL,lease_until=NULL,error=NULL,updated_at=? "
                       'WHERE turn_id=?', (self.now, turn_id))
            return {'accepted': saved, 'considered': len(candidates)}

    def retry_failed(self):
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            jobs = db.execute("UPDATE memory_jobs SET status='pending',attempts=0,available_at=0,error=NULL "
                              "WHERE status='failed'").rowcount
            projections = db.execute("UPDATE memory_outbox SET status='pending',attempts=0,available_at=0,error=NULL "
                                     "WHERE status='failed'").rowcount
            db.execute("UPDATE memory_index_state SET status='pending',attempts=0,available_at=0 WHERE status='failed'")
            db.execute("UPDATE memory_project_outbox SET status='pending',attempts=0,available_at=0 WHERE status='failed'")
            return {'retried_jobs': jobs, 'retried_projections': projections}

    def request_rebuild(self):
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE memory_index_state SET generation=generation+1,status='pending',attempts=0,available_at=0 WHERE id=1")
            return {'generation': db.execute('SELECT generation FROM memory_index_state WHERE id=1').fetchone()[0],
                    'status':'pending'}
