"""Scoped hybrid retrieval, always resolved through the authoritative ledger."""
import json
import math
import re

from .process import AdapterUnavailable


def fts_query(query):
    from ..intelligence import terms
    words = sorted(terms(query), key=lambda w: (-len(w), w))[:8]
    return ' OR '.join('"' + word.replace('"', '""') + '"*' for word in words)


def compact(record):
    return {key: record[key] for key in (
        'id', 'revision', 'key', 'kind', 'content', 'scope', 'source', 'source_turn', 'updated_at')}


def behavioral(record):
    return record['key'] in {
        'communication.language','communication.language.technical_docs','communication.style','communication.structure','language','preferred language'}


class Retrieval:
    def __init__(self, ledger):
        self.ledger = ledger
        self.store = ledger.store

    def resolve_project(self, conversation_id, message):
        state = self.ledger.conversation_state(conversation_id)
        projects = self.ledger.projects()['items']
        # Full explicit names only. Similar words never create associations.
        exact = [p for p in projects if re.search(
            r'(?<!\w)' + re.escape(p['name']) + r'(?!\w)', message, re.I)]
        if len(exact) > 1:
            return None, [p['name'] for p in exact]
        if exact:
            if state['project_id'] and exact[0]['id']!=state['project_id']:
                prior=next((p['name'] for p in projects if p['id']==state['project_id']), 'Current project')
                return None,[prior,exact[0]['name']]
            return exact[0]['id'], []
        if state['project_id']:
            return state['project_id'], []
        words = set(re.findall(r'\w+', message.casefold()))
        overlaps = [p for p in projects if words & set(re.findall(r'\w+', p['name_key']))]
        continuation = re.search(r'\bproject|\bcontinue|\bresume|نكمل|مشروع', message, re.I)
        return None, [p['name'] for p in overlaps] if len(overlaps) > 1 and continuation else []

    def archive(self, query, conversation_id=None, project_id=None, before=None, limit=20):
        from ..intelligence import text, identifier
        query = text(query, 300)
        for value in (conversation_id, project_id):
            if value is not None:
                identifier(value)
        if (type(limit) is not int or not 1 <= limit <= 40
                or (before is not None and (type(before) is not int or not 0 < before < 2**63))):
            raise ValueError('invalid_archive_cursor')
        match = fts_query(query)
        if not match:
            return {'items': [], 'next_before': None}
        with self.store.connect() as db:
            rows = db.execute('''SELECT t.id,t.seq,t.conversation_id,t.user_text,t.response,
                t.created_at,t.status,c.title FROM chat_archive_fts f JOIN chat_turns t ON t.seq=f.rowid
                JOIN chat_conversations c ON c.id=t.conversation_id
                LEFT JOIN memory_turn_projects s ON s.turn_id=t.id
                WHERE chat_archive_fts MATCH ? AND t.seq<? AND t.status<>'running'
                AND (? IS NULL OR t.conversation_id=?) AND (? IS NULL OR s.project_id=?)
                ORDER BY t.seq DESC LIMIT ?''', (match, before or 2**63-1,
                conversation_id, conversation_id, project_id, project_id, limit + 1)).fetchall()
            items = []
            for row in rows[:limit]:
                sources = [dict(r) for r in db.execute('''SELECT e.memory_id,e.revision,v.status
                    FROM memory_evidence e JOIN memory_versions v
                    ON v.memory_id=e.memory_id AND v.revision=e.revision WHERE e.turn_id=? LIMIT 8''', (row['id'],))]
                answer = json.loads(row['response']).get('answer', '') if row['response'] else None
                items.append({'turn_id': row['id'], 'seq': row['seq'],
                    'conversation_id': row['conversation_id'], 'title': row['title'],
                    'owner_excerpt': row['user_text'][:500], 'assistant_excerpt': answer[:500] if answer else None,
                    'created_at': row['created_at'], 'memory_versions': sources,
                    'authority': 'original_owner_message_and_unverified_assistant_response'})
            return {'items': items, 'next_before': items[-1]['seq'] if len(rows) > limit else None}

    def select(self, conversation_id, message):
        from ..intelligence import terms
        project_id, ambiguity = self.resolve_project(conversation_id, message)
        if ambiguity:
            return [], {'project_ambiguity': ambiguity, 'memory_selection': 'explicit_project_required'}
        query = terms(message)
        chat_query=bool(re.search(r'this (?:conversation|chat)|المحادثة دي|هذه المحادثة|الشات ده',message,re.I))
        decision_query=bool(re.search(r'database|architecture|why.*(?:cho[o]?se|chose)|قاعدة البيانات|اخترنا|اختيار|معمار',message,re.I))
        pending_query=bool(re.search(r'pending|next|unfinished|متبقي|معلق|الجاية|خطوة|لسه',message,re.I))
        name_query=bool(re.search(r'\bname|address me|call me|اسمي|الاسم|تناديني',message,re.I))
        match = fts_query(message)
        if project_id is None and not chat_query and decision_query and match:
            # A distinctive decision reference can retrieve across projects
            # without changing the conversation association. Multiple matches
            # require clarification; titles or semantic similarity never merge
            # projects or create a write scope.
            with self.store.connect() as db:
                matches=[dict(r) for r in db.execute('''SELECT DISTINCT p.id,p.name
                    FROM memory_fts f JOIN chat_memories m ON m.id=f.memory_id
                    JOIN memory_meta x ON x.memory_id=m.id JOIN memory_projects p ON p.id=x.project_id
                    WHERE memory_fts MATCH ? AND m.kind='decision'
                    AND (m.expires_at=0 OR m.expires_at>?) LIMIT 3''',(match,self.ledger.now))]
            if len(matches)>1:
                return [],{'project_ambiguity':[p['name'] for p in matches],
                           'memory_selection':'explicit_project_required'}
            if matches:project_id=matches[0]['id']
        with self.store.connect() as db:
            related = {r[0] for r in db.execute('SELECT turn_id FROM memory_turn_projects WHERE project_id=?', (project_id,))} if project_id else set()
            eligible = """(m.scope='owner' OR m.conversation_id=? OR (? IS NOT NULL AND (x.project_id=?
                OR (m.kind<>'instruction' AND m.key NOT IN ('communication.language','communication.style','communication.structure','language')
                AND m.source_turn IN (SELECT turn_id FROM memory_turn_projects WHERE project_id=?)))))"""
            parameters = (conversation_id, project_id, project_id, project_id, self.ledger.now)
            # Global behavioral preferences always enter the candidate set,
            # including on a short greeting in a new conversation.
            rows = db.execute('''SELECT m.*,x.assertion,x.project_id,x.effective_seq FROM chat_memories m
                JOIN memory_meta x ON x.memory_id=m.id WHERE ''' + eligible + '''
                AND (m.expires_at=0 OR m.expires_at>?)
                ORDER BY CASE WHEN m.kind='instruction' OR m.key IN
                    ('communication.language','communication.style','communication.structure','language') THEN 0 ELSE 1 END,
                m.updated_at DESC,m.id LIMIT 48''', parameters).fetchall()
            candidates = {r['id']: dict(r) for r in rows}
            lexical_ids = set()
            if match:
                found = db.execute('''SELECT m.*,x.assertion,x.project_id,x.effective_seq FROM memory_fts f
                    JOIN chat_memories m ON m.id=f.memory_id JOIN memory_meta x ON x.memory_id=m.id
                    WHERE memory_fts MATCH ? AND ''' + eligible + '''
                    AND (m.expires_at=0 OR m.expires_at>?) ORDER BY bm25(memory_fts) LIMIT 24''',
                    (match, *parameters)).fetchall()
                for row in found:
                    candidates[row['id']] = dict(row)
                    lexical_ids.add(row['id'])
        vector_scores = {}
        adapter = getattr(self.store, 'memory_adapter', None)
        vector_status = 'not_configured'
        if adapter is not None and adapter.config_path.exists():
            try:
                hits = adapter.call('search', {'query': message, 'limit': 16}, timeout=3, opportunistic=True)
                if not isinstance(hits,list) or any(not isinstance(h,dict)
                        or type(h.get('score')) not in {int,float} or not math.isfinite(h['score'])
                        or not -1 <= h['score'] <= 1.01 for h in hits):
                    raise ValueError('invalid_semantic_results')
                for row in self.ledger.active(hits):
                    if (row['scope'] == 'owner' or row['conversation_id'] == conversation_id
                            or (project_id is not None and row['project_id'] == project_id)
                            or (not behavioral(row) and row['source_turn'] in related)):
                        candidates[row['id']] = row
                        vector_scores[row['id']] = next(h['score'] for h in hits if h['id']==row['id'])
                vector_status = 'current'
            except (AdapterUnavailable,ValueError,TypeError,KeyError):
                vector_status = 'delayed_lexical_fallback'
        def rank(record):
            overlap = len(query & terms(record['key'] + ' ' + record['content']))
            instruction = behavioral(record) and record['assertion'] == 'remembered'
            score = 100 if instruction and record['conversation_id'] == conversation_id else 80 if instruction else 0
            score += 12 if project_id and (record['project_id'] == project_id or record['source_turn'] in related) else 0
            score += (40 if chat_query else 12) if record['conversation_id'] == conversation_id else 0
            score += 20 if decision_query and record['kind']=='decision' else 0
            score += 15 if pending_query and record['kind']=='task' else 0
            score += 40 if name_query and record['key'] in {'profile.name','name','owner.name'} else 0
            score += min(12, 3 * overlap) + (4 if record['id'] in lexical_ids else 0)
            score += max(0, min(1, vector_scores.get(record['id'], 0))) * 10
            score += max(0, 1 - (self.ledger.now-record['updated_at'])/(90*86400))
            tier=(3 if record['conversation_id']==conversation_id else 2 if record['scope'].startswith('project:') else 1) if instruction else 0
            return tier,(record.get('effective_seq',0) if instruction else score),score,record['updated_at'],record['id']
        eligible_candidates=[r for r in candidates.values() if not chat_query or (
            r['scope']=='owner' or r['conversation_id']==conversation_id
            or r['kind'] in {'decision','constraint'} and r['scope'].startswith('project:'))]
        ranked = sorted(eligible_candidates, key=rank, reverse=True)
        # Choose one effective response preference per subject. Lower scope
        # copies must not win through lexical similarity or crowd out facts.
        effective=[];seen=set()
        for record in ranked:
            if behavioral(record):
                key='communication.language' if record['key'] in {'language','preferred language'} else record['key']
                if key in seen:continue
                seen.add(key)
            effective.append(record)
        ranked=effective
        selected = [compact(r) for r in ranked if (
            behavioral(r) or r['conversation_id'] == conversation_id
            or (project_id is not None and r['project_id'] == project_id)
            or (not behavioral(r) and r['source_turn'] in related)
            or (name_query and r['key'] in {'profile.name','name','owner.name'})
            or r['id'] in lexical_ids or vector_scores.get(r['id'], 0) >= .4)][:8]
        state = self.ledger.conversation_state(conversation_id)
        project = next((p for p in self.ledger.projects()['items'] if p['id'] == project_id), None)
        checkpoint = [{**v, 'key': k} for k,v in state['state'].items()][-6:]
        # Project and conversation state are source quotes, never verification
        # that an action actually ran. Computer receipts stay a separate field.
        archive = self.archive(message[:300], project_id=project_id,
                               conversation_id=conversation_id if chat_query or not project_id else None, limit=3)['items']
        return selected, {'memory_selection': 'scoped_hybrid_priority_fts_vector_temporal',
            'semantic_index': vector_status, 'project': project,
            'current_conversation_id':conversation_id,
            'conversation_checkpoint': checkpoint,
            'archive_excerpts': [{k:v for k,v in r.items() if k not in {'assistant_excerpt','title'}} for r in archive]}
