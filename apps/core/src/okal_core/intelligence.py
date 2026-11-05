"""Private durable chat state. Model output has no memory-write authority.

All SQL writes are short transactions; inference runs outside transactions.
Leases fence late responses and serialize chat inference across processes.
"""
import hashlib
import json
import re
import uuid

from .store import Conflict

LEASE_SECONDS = 180
MAX_MEMORIES = 500
SECRET = re.compile(
    r"-----BEGIN .*PRIVATE KEY|\b(?:Bearer\s+\S+|sk-[A-Za-z0-9_-]{12,}|"
    r"gh[pousr]_[A-Za-z0-9_]{12,}|AIza[A-Za-z0-9_-]{20,}|ya29\.[\w.-]+)|"
    r"(?:password|passwd|access[_ -]?token|refresh[_ -]?token|api[_ -]?key|"
    r"client[_ -]?secret|كلمة\s*(?:السر|المرور)|توكن)\s*[=:]\s*\S+",
    re.IGNORECASE,
)
STOP = set("the a an is are my me i of to in it and what do you remember about that "
           "من في على ايه إيه أنا انا هو هي ده دي عن و ما هل اللي عندي".split())


class Missing(ValueError):
    pass


class Busy(Conflict):
    pass


def text(value, maximum):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(ord(c) < 32 and c not in '\n\t' for c in value)):
        raise ValueError('invalid_text')
    if SECRET.search(value):
        raise ValueError('credential_like_text_rejected')
    return value.strip()


def safe_context(value):
    """Drop credential-like cached fields before model input, including nested data."""
    if isinstance(value, str):
        return '[sensitive text omitted]' if SECRET.search(value) else value
    if isinstance(value, list):
        return [safe_context(v) for v in value]
    if isinstance(value, dict):
        return {k: safe_context(v) for k, v in value.items()
                if not re.search('token|password|credential|secret', str(k), re.I)}
    return value


def terms(value):
    return set(re.findall(r'[\w\u0600-\u06ff]{2,}', value.casefold())) - STOP


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{32}', value):
        raise ValueError('invalid_identifier')
    return value


class Intelligence:
    def __init__(self, store):
        self.store = store
        with store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('PRAGMA secure_delete=ON')
            db.execute('CREATE TABLE IF NOT EXISTS chat_schema (version INTEGER NOT NULL)')
            version = db.execute('SELECT version FROM chat_schema').fetchone()
            if version is not None and version[0] not in (1, 2):
                raise ValueError('unsupported_chat_schema_do_not_downgrade')
            if version is None:
                db.execute('INSERT INTO chat_schema VALUES(1)')
            db.execute('''CREATE TABLE IF NOT EXISTS chat_conversations (
                id TEXT PRIMARY KEY, title TEXT NOT NULL,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS chat_turns (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT NOT NULL UNIQUE, conversation_id TEXT NOT NULL
                    REFERENCES chat_conversations(id) ON DELETE CASCADE,
                request_id TEXT NOT NULL, digest TEXT NOT NULL,
                user_text TEXT NOT NULL, response TEXT,
                status TEXT NOT NULL CHECK(status IN ('running','complete','failed')),
                lease TEXT, lease_until INTEGER, created_at INTEGER NOT NULL,
                UNIQUE(conversation_id,request_id))''')
            db.execute('''CREATE INDEX IF NOT EXISTS chat_turn_order
                ON chat_turns(conversation_id,seq)''')
            db.execute('''CREATE TABLE IF NOT EXISTS chat_memories (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                key TEXT NOT NULL, content TEXT NOT NULL, scope TEXT NOT NULL,
                conversation_id TEXT REFERENCES chat_conversations(id) ON DELETE CASCADE,
                source_turn TEXT REFERENCES chat_turns(id) ON DELETE CASCADE,
                source TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 1,
                revision INTEGER NOT NULL, created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
                UNIQUE(scope,key))''')
            db.execute('''CREATE TABLE IF NOT EXISTS chat_sources (
                turn_id TEXT NOT NULL REFERENCES chat_turns(id) ON DELETE CASCADE,
                memory_id TEXT NOT NULL REFERENCES chat_memories(id) ON DELETE CASCADE,
                PRIMARY KEY(turn_id,memory_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS chat_settings (
                id INTEGER PRIMARY KEY CHECK(id=1), retention_days INTEGER NOT NULL)''')
            db.execute('INSERT OR IGNORE INTO chat_settings VALUES(1,0)')
        from .cognitive.ledger import Ledger
        self.cognitive = Ledger(self)

    @property
    def now(self):
        return int(self.store.clock())

    def _forget(self, db, memory_id):
        self.cognitive.forget(db, memory_id)

    def _prune(self, db):
        db.execute('PRAGMA secure_delete=ON')
        for row in db.execute('SELECT id FROM chat_memories WHERE expires_at>0 AND expires_at<=?',
                              (self.now,)).fetchall():
            self._forget(db, row[0])
        retention = db.execute('SELECT retention_days FROM chat_settings WHERE id=1').fetchone()[0]
        if retention == 0:
            return
        for row in db.execute('SELECT id FROM chat_conversations WHERE updated_at<?',
                              (self.now - retention * 86400,)).fetchall():
            self._delete(db, row[0])

    def settings(self, days=None):
        if days is not None and (type(days) is not int or not 0 <= days <= 365):
            raise ValueError('invalid_retention')
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            if days is not None:
                db.execute('UPDATE chat_settings SET retention_days=? WHERE id=1', (days,))
            self._prune(db)
            return {'retention_days': db.execute(
                'SELECT retention_days FROM chat_settings WHERE id=1').fetchone()[0]}

    def create(self, title='New conversation'):
        title = text(title, 100)
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            self._prune(db)
            if db.execute('SELECT COUNT(*) FROM chat_conversations').fetchone()[0] >= 500:
                raise ValueError('conversation_limit_delete_old_conversations')
            result = dict(id=uuid.uuid4().hex, title=title, created_at=self.now, updated_at=self.now)
            db.execute('INSERT INTO chat_conversations VALUES(:id,:title,:created_at,:updated_at)', result)
            return result

    def conversations(self, before=None):
        if before is not None:
            identifier(before)
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            self._prune(db)
            cursor = db.execute('SELECT created_at,id FROM chat_conversations WHERE id=?', (before,)).fetchone() if before else None
            if before and cursor is None:
                raise Missing('conversation_cursor_not_found')
            rows = db.execute('SELECT * FROM chat_conversations WHERE (? IS NULL OR '
                              '(created_at,id)<(?,?)) ORDER BY created_at DESC,id DESC LIMIT 51',
                              (before, cursor[0] if cursor else 0, before)).fetchall()
            items = [dict(r) for r in rows[:50]]
            return {'items': items, 'next_before': items[-1]['id'] if len(rows) > 50 else None}

    def get(self, conversation_id, before=None):
        identifier(conversation_id)
        if before is not None and (type(before) is not int or not 1 <= before < 2**63):
            raise ValueError('invalid_cursor')
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            self._prune(db)
            row = db.execute('SELECT * FROM chat_conversations WHERE id=?', (conversation_id,)).fetchone()
            if row is None:
                raise Missing('conversation_not_found')
            turns = db.execute('SELECT * FROM chat_turns WHERE conversation_id=? '
                               'AND seq<? ORDER BY seq DESC LIMIT 41',
                               (conversation_id, before or 2**63 - 1)).fetchall()
            result = dict(row)
            result['turns'] = [self._public_turn(t) for t in reversed(turns[:40])]
            result['next_before'] = turns[39]['seq'] if len(turns) > 40 else None
            return result

    def _public_turn(self, row):
        return {'id': row['id'], 'request_id': row['request_id'], 'seq': row['seq'],
                'message': row['user_text'], 'created_at': row['created_at'],
                'status': ('interrupted' if row['status'] == 'running'
                           and row['lease_until'] <= self.now else row['status']),
                'response': json.loads(row['response']) if row['response'] else None}

    def _delete(self, db, conversation_id):
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='computer_runs'").fetchone():
            if db.execute("SELECT 1 FROM computer_runs WHERE conversation_id=? AND status='running'",
                          (conversation_id,)).fetchone():
                raise Conflict('cancel_running_actions_before_deleting_conversation')
        for row in db.execute('SELECT id FROM chat_memories WHERE conversation_id=? '
                              'OR source_turn IN (SELECT id FROM chat_turns WHERE conversation_id=?)',
                              (conversation_id, conversation_id)).fetchall():
            if not self.cognitive.retain_independent_source(db,row[0],conversation_id):
                self._forget(db, row[0])
        self.cognitive.deleting_history(db, conversation_id)
        db.execute('DELETE FROM chat_conversations WHERE id=?', (conversation_id,))

    def delete(self, conversation_id):
        identifier(conversation_id)
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('PRAGMA secure_delete=ON')
            self._delete(db, conversation_id)
        return {'deleted': True}

    def begin(self, conversation_id, request_id, message, retry=False):
        identifier(conversation_id)
        identifier(request_id)
        message = text(message, 900)
        digest = hashlib.sha256(message.encode()).hexdigest()
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            self._prune(db)
            if not db.execute('SELECT id FROM chat_conversations WHERE id=?', (conversation_id,)).fetchone():
                raise Missing('conversation_not_found')
            old = db.execute('SELECT * FROM chat_turns WHERE conversation_id=? AND request_id=?',
                             (conversation_id, request_id)).fetchone()
            if old:
                if old['digest'] != digest or old['user_text'] == '[forgotten]':
                    raise Conflict('request_content_changed_or_forgotten')
                if old['status'] == 'complete' or (old['response'] and not retry):
                    return {'replay': json.loads(old['response'])}
                if old['lease_until'] and old['lease_until'] > self.now:
                    raise Busy('turn_in_progress')
                latest = db.execute('SELECT MAX(seq) FROM chat_turns WHERE conversation_id=?',
                                    (conversation_id,)).fetchone()[0]
                if latest != old['seq']:
                    raise Conflict('only_latest_failed_turn_can_retry')
            if db.execute("SELECT 1 FROM chat_turns WHERE status='running' AND lease_until>? LIMIT 1",
                          (self.now,)).fetchone():
                raise Busy('local_model_busy')
            lease, turn_id = uuid.uuid4().hex, old['id'] if old else uuid.uuid4().hex
            if old:
                db.execute("UPDATE chat_turns SET status='running',lease=?,lease_until=?,response=NULL WHERE id=?",
                           (lease, self.now + LEASE_SECONDS, turn_id))
            else:
                if db.execute('SELECT COUNT(*) FROM chat_turns WHERE conversation_id=?',
                              (conversation_id,)).fetchone()[0] >= 2000:
                    raise ValueError('conversation_full_start_new')
                db.execute('''INSERT INTO chat_turns(id,conversation_id,request_id,digest,user_text,
                           status,lease,lease_until,created_at) VALUES(?,?,?,?,?,'running',?,?,?)''',
                           (turn_id, conversation_id, request_id, digest, message, lease,
                            self.now + LEASE_SECONDS, self.now))
            db.execute("UPDATE chat_conversations SET updated_at=?,title=CASE WHEN title='New conversation' "
                       'THEN ? ELSE title END WHERE id=?', (self.now, message[:70], conversation_id))
            db.execute('''INSERT OR IGNORE INTO memory_turn_projects(turn_id,project_id)
                VALUES(?,(SELECT project_id FROM memory_conversations WHERE conversation_id=?))''',
                (turn_id,conversation_id))
            return {'lease': lease, 'turn_id': turn_id}

    def memories(self, conversation_id=None, project_id=None):
        if conversation_id is not None:
            identifier(conversation_id)
        if project_id is not None:
            identifier(project_id)
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            self._prune(db)
            rows = db.execute("SELECT m.*,x.project_id,x.assertion FROM chat_memories m "
                              "JOIN memory_meta x ON x.memory_id=m.id WHERE scope='owner' OR conversation_id=? "
                              'OR (? IS NOT NULL AND x.project_id=?) ORDER BY updated_at DESC,id LIMIT 500',
                              (conversation_id, project_id, project_id)).fetchall()
            return {'items': [dict(r, status='remembered' if r['assertion']=='remembered' else r['assertion']) for r in rows]}

    def save_memory(self, key, content, kind='semantic', conversation_id=None,
                    source_turn=None, revision=0, days=0, project_id=None):
        return self.cognitive.save(key, content, kind, conversation_id,
                                   source_turn, revision, days, project_id=project_id)

    def forget(self, memory_id):
        identifier(memory_id)
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('PRAGMA secure_delete=ON')
            self._forget(db, memory_id)
        return {'deleted': True}

    def context(self, conversation_id, message, turn_id):
        from .cognitive.retrieval import Retrieval
        selected, retrieval = Retrieval(self.cognitive).select(conversation_id, message)
        # Register provenance BEFORE inference so forgetting during generation
        # fences the in-flight turn and prevents resurrecting forgotten output.
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM chat_sources WHERE turn_id=?', (turn_id,))
            for m in selected:
                current = db.execute('SELECT revision FROM chat_memories WHERE id=?', (m['id'],)).fetchone()
                if current is None or current[0] != m['revision']:
                    raise Conflict('memory_changed_retry')
                db.execute('INSERT INTO chat_sources VALUES(?,?)', (turn_id, m['id']))
            rows = db.execute("SELECT * FROM chat_turns WHERE conversation_id=? AND id<>? "
                              "AND status='complete' ORDER BY seq DESC LIMIT 24",
                              (conversation_id, turn_id)).fetchall()
            dependencies = [(r['id'], r['user_text']) for r in rows[:12]]
            dependencies.extend((r['turn_id'],r['owner_excerpt']) for r in retrieval.get('archive_excerpts', []))
            dependencies.extend((r['turn_id'],None) for r in retrieval.get('conversation_checkpoint', []))
            for source_id, excerpt in dependencies:
                if source_id == turn_id:
                    continue
                current = db.execute('SELECT user_text FROM chat_turns WHERE id=?', (source_id,)).fetchone()
                if current is None or (excerpt is not None and not current[0].startswith(excerpt)):
                    raise Conflict('archive_source_changed_retry')
                db.execute('INSERT OR IGNORE INTO memory_turn_sources VALUES(?,?)', (turn_id,source_id))
            for r in rows[:12]:
                db.execute('''INSERT OR IGNORE INTO chat_sources
                    SELECT ?,memory_id FROM chat_sources WHERE turn_id=?''', (turn_id, r['id']))
                db.execute('''INSERT OR IGNORE INTO chat_sources
                    SELECT ?,id FROM chat_memories WHERE source_turn=?''', (turn_id, r['id']))
        recent = []
        for r in reversed(rows[:4]):
            recent.extend([{'role': 'user', 'content': r['user_text']},
                           {'role': 'assistant', 'content': json.loads(r['response'])['answer'][:900]}])
        # Deterministic extractive compaction; never promotes assistant guesses.
        # Rebuilt from source on every call, no independent summary accumulation.
        older = [{'turn_id': r['id'], 'owner_excerpt': r['user_text'][:150]}
                 for r in reversed(rows[4:12])]
        action_receipts=[]
        with self.store.connect() as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='computer_runs'").fetchone():
                action_receipts=[dict(r) for r in db.execute(
                    '''SELECT r.id,r.instruction,r.status,r.created_at,
                    COUNT(s.id) AS total_steps,SUM(CASE WHEN s.status='verified' THEN 1 ELSE 0 END) AS verified_steps
                    FROM computer_runs r LEFT JOIN computer_steps s ON s.run_id=r.id
                    LEFT JOIN chat_turns t ON t.conversation_id=r.conversation_id AND t.request_id=r.request_id
                    LEFT JOIN memory_turn_projects p ON p.turn_id=t.id
                    WHERE (r.conversation_id=? AND ? IS NULL) OR p.project_id=?
                    GROUP BY r.id ORDER BY r.created_at DESC LIMIT 3''',
                    (conversation_id,(retrieval.get('project') or {}).get('id'),
                     (retrieval.get('project') or {}).get('id')))]
        for receipt in action_receipts:
            receipt['instruction']=receipt['instruction'][:160]
            receipt['verified']=bool(receipt['status']=='succeeded' and receipt['total_steps']>0
                                     and receipt['verified_steps']==receipt['total_steps'])
            receipt['source']='computer_execution_receipt'
        return recent, {'action_receipts': action_receipts, 'memories': selected, 'older_owner_excerpts': older,
                        'history_limited': len(rows) >= 12,
                        **retrieval,
                        'memory_assertion': 'owner_statement_not_independently_verified'}

    def finish(self, turn_id, lease, response):
        # Revalidate output at the persistence boundary; never save secret-like
        # output even if a local model mistakenly repeats a credential.
        response = dict(response)
        response['answer'] = text(response['answer'], 1200)
        if SECRET.search(json.dumps(response, ensure_ascii=False)):
            raise ValueError('credential_like_output_rejected')
        response.update(turn_id=turn_id, conversation_saved=True)
        with self.store.connect() as db, db:
            db.execute('BEGIN IMMEDIATE')
            changed = db.execute("UPDATE chat_turns SET response=?,status=?,lease=NULL,lease_until=NULL "
                                 "WHERE id=? AND lease=? AND lease_until>? AND status='running'",
                                 (json.dumps(response, ensure_ascii=False),
                                  'complete' if response['mode'] in {'pinned_local_ollama', 'owner_memory', 'action_plan'} else 'failed',
                                  turn_id, lease, self.now)).rowcount
            if not changed:
                raise Conflict('turn_expired_deleted_or_forgotten')
            self.cognitive.enqueue(db, turn_id)
            if response.get('source')=='explicit_project_clarification':
                db.execute("UPDATE memory_jobs SET status='scope_required' WHERE turn_id=?", (turn_id,))
        return response


def remember_request(message):
    """Only an explicit, structured owner request can propose a memory save."""
    match = re.fullmatch(r'(?:remember|افتكر|احفظ|تذكر)\s*:?\s*([^:\n]{1,80}):\s*(.{1,600})',
                         message, re.IGNORECASE | re.DOTALL)
    return (match[1].strip(), match[2].strip()) if match else None


def respond(store, conversation_id, request_id, message, retry=False, infer=None):
    state = Intelligence(store)
    claim = state.begin(conversation_id, request_id, message, retry)
    if 'replay' in claim:
        return dict(claim['replay'], replayed=True)
    turn_id, lease = claim['turn_id'], claim['lease']
    try:
        from .chat import ask
        from .cognitive.retrieval import Retrieval
        from .cognitive.learning import EXTERNAL
        with store.connect() as db:
            prior = db.execute('SELECT response FROM chat_turns WHERE conversation_id=? AND id<>? ORDER BY seq DESC LIMIT 1',
                               (conversation_id,turn_id)).fetchone()
        choices = (json.loads(prior[0]).get('project_choices',[]) if prior and prior[0] else [])
        choice_text = re.sub(r'^(?:i mean|اقصد|أقصد|قصدي)\s*[:،,]?\s*','',message.strip(),flags=re.I).strip(' .؟?')
        chosen = next((p for p in state.cognitive.projects()['items']
                       if p['name'] in choices and p['name_key']==choice_text.casefold()),None)
        if chosen:
            association = state.cognitive.conversation_state(conversation_id)
            state.cognitive.associate(conversation_id,chosen['id'],association['revision'])
            with store.connect() as db, db:
                db.execute('UPDATE memory_turn_projects SET project_id=?,revision=revision+1 WHERE turn_id=?', (chosen['id'],turn_id))
        # A unique full project name in the owner's own project discussion is
        # an explicit reference, unlike a semantic guess or shared keyword.
        if not EXTERNAL.search(message) and re.search(r'\bproject|\bcontinue|\bresume|نكمل|مشروع',message,re.I):
            project_id, ambiguous = Retrieval(state.cognitive).resolve_project(conversation_id,message)
            association = state.cognitive.conversation_state(conversation_id)
            if project_id and not ambiguous and association['project_id'] is None:
                state.cognitive.associate(conversation_id,project_id,association['revision'])
        history, context = state.context(conversation_id, message, turn_id)
        memory = remember_request(message)
        if context.get('project_ambiguity'):
            response = {'answer': 'Which project do you mean? / تقصد أي مشروع؟ ' +
                        ' · '.join(context['project_ambiguity'])[:700],
                        'proposal': None, 'mode': 'owner_memory', 'saved': False,
                        'source': 'explicit_project_clarification', 'voice_enabled': False,
                        'project_choices': context['project_ambiguity']}
        elif memory:
            key, value = memory
            existing = next((m for m in state.memories()['items'] if m['key'] == key.casefold()), None)
            if existing and existing['content'] != value:
                response = {'answer': 'A saved value already exists. Edit it in Memory / الذاكرة to confirm the correction.',
                            'proposal': None, 'mode': 'owner_memory', 'saved': False,
                            'source': 'owner_memory_policy', 'voice_enabled': False}
            else:
                saved = state.save_memory(key, value, source_turn=turn_id)
                response = {'answer': 'Saved your statement / اتحفظت المعلومة: ' + saved['content'],
                            'proposal': None, 'mode': 'owner_memory', 'saved': False,
                            'source': 'owner_memory_policy', 'voice_enabled': False}
        else:
            from .computer.chat import propose_for_chat
            action = propose_for_chat(store, conversation_id, request_id, message) if infer is None else None
            response = action or ask(store, message, history, infer=infer, memory_context=context)
        response.setdefault('context_sources', [])
        response.setdefault('history_limited', context['history_limited'])
        return state.finish(turn_id, lease, response)
    except Exception:
        with store.connect() as db, db:
            db.execute("UPDATE chat_turns SET status='failed',lease=NULL,lease_until=NULL "
                       "WHERE id=? AND lease=?", (turn_id, lease))
        raise
