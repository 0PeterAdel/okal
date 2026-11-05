"""Clean, optional Obsidian-compatible projection; no Basic Memory code.

Only owner-confirmed imports can revise SQLite. Stale notes never create facts.
Stable ID filenames avoid path construction from owner text or model output.
"""
import hashlib
import html
import json
import os
from pathlib import Path
import stat
import re
import uuid

from ..store import Conflict, private_directory

START, END = '<!-- okal:content -->', '<!-- /okal:content -->'
FOLDERS = ('preferences', 'projects', 'decisions', 'research', 'goals', 'lessons', 'constraints')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Vault:
    def __init__(self, ledger):
        self.ledger = ledger
        self.root = private_directory(private_directory(ledger.store.directory / 'cognitive') / 'vault')

    def _path(self, record):
        from ..intelligence import identifier
        identifier(record['id'])
        folder = {'decision': 'decisions', 'goal': 'goals', 'lesson': 'lessons',
                  'constraint': 'constraints'}.get(record['kind'],
                  'preferences' if record['scope'] == 'owner' else 'projects')
        return private_directory(self.root / folder) / ('memory-' + record['id'] + '.md')

    def curated(self, record):
        return (record['scope']=='owner' or record['scope'].startswith('project:')
                or record['kind']=='lesson') and record['kind'] in {
                    'semantic','instruction','decision','goal','constraint','lesson'}

    def _read(self, path):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 16_000:
                raise ValueError('invalid_vault_note')
            with os.fdopen(fd, 'r', encoding='utf-8', closefd=False) as stream:
                raw = stream.read(16_001)
        finally:
            os.close(fd)
        if not raw.startswith('---\n'):
            raise ValueError('invalid_vault_frontmatter')
        header, body = raw[4:].split('\n---\n', 1)
        metadata = {}
        for line in header.splitlines():
            key, value = line.split(': ', 1)
            if key in metadata:
                raise ValueError('duplicate_vault_metadata')
            metadata[key] = json.loads(value)
        if set(metadata) != {'okal', 'memory_id', 'revision', 'scope', 'base_sha256', 'source_turn'}:
            raise ValueError('invalid_vault_metadata')
        if type(metadata['okal']) is not int or metadata['okal'] not in {1,2} or type(metadata['revision']) is not int:
            raise ValueError('invalid_vault_note_contract')
        if metadata['okal']==1:
            if body.count(START)!=1 or body.count(END)!=1:
                raise ValueError('invalid_vault_note_contract')
            content = body.split(START, 1)[1].split(END, 1)[0].strip()
        else:
            prefix,separator,statement=body.partition('\n## Owner statement\n\n')
            match=re.fullmatch(r'(`{3,})text\n(.*)\n\1\n?',statement,re.S) if separator else None
            if match is None:
                raise ValueError('edit_inside_vault_statement_block')
            content=match[2].strip()
        return metadata, content

    def export(self, record):
        with self.ledger._transaction() as db:
            current = db.execute('SELECT revision,content FROM chat_memories WHERE id=?', (record['id'],)).fetchone()
            if current is None or current['revision'] != record['revision'] or current['content'] != record['content']:
                raise Conflict('vault_stale_or_deleted_no_export')
            return self._export(record)

    def _export(self, record):
        if not self.curated(record):
            self.delete(record['id'])
            return {'memory_id':record['id'],'revision':record['revision'],'status':'not_curated'}
        path = self._path(record)
        if path.exists() or path.is_symlink():
            metadata, content = self._read(path)
            if metadata['memory_id'] != record['id']:
                raise Conflict('vault_identity_conflict')
            if digest(content) != metadata['base_sha256'] and content != record['content']:
                raise Conflict('vault_owner_edit_requires_import_or_discard')
            if metadata['revision'] > record['revision']:
                raise Conflict('vault_newer_revision_conflict')
        metadata = {'okal': 2, 'memory_id': record['id'], 'revision': record['revision'],
                    'scope': record['scope'], 'base_sha256': digest(record['content']),
                    'source_turn': record.get('source_turn')}
        titles={'communication.language':'Reply language','communication.style':'Communication style',
                'communication.structure':'Response structure','architecture.database':'Database decision'}
        title = html.escape(titles.get(record['key'],record['key'].replace('_',' ').replace('.',' ')))
        title = title.replace('\n',' ').replace('#','').replace('[','').replace(']','')
        link = '\nProject: [[project-' + record['scope'][8:] + ']]\n' if record['scope'].startswith('project:') else ''
        raw = '---\n' + '\n'.join(k + ': ' + json.dumps(v, ensure_ascii=False)
                                   for k,v in metadata.items()) + '\n---\n# ' + title + '\n'
        # Literal text fences prevent an automatically extracted remote image,
        # HTML tag or link from making Obsidian fetch private URLs on open.
        fence='`'*max(3,1+max((len(v) for v in re.findall(r'`+',record['content'])),default=0))
        raw += link + '\nOwner statement; not independently verified.\n\n## Owner statement\n\n'
        raw += fence+'text\n'+record['content']+'\n'+fence+'\n'
        temporary = path.with_name('.' + uuid.uuid4().hex + '.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return {'memory_id': record['id'], 'revision': record['revision'], 'status': 'current'}

    def _locate(self, memory_id):
        from ..intelligence import identifier
        identifier(memory_id)
        found = []
        for folder in FOLDERS:
            directory = self.root / folder
            if not directory.exists():
                continue
            private_directory(directory)  # Reject symlinked/nonprivate directories.
            path = directory / ('memory-' + memory_id + '.md')
            if path.exists() or path.is_symlink():
                found.append(path)
        return found

    def delete(self, memory_id):
        for path in self._locate(memory_id):
            # Unlinking a symlink never follows it; no read of forgotten text.
            path.unlink()
        return {'memory_id': memory_id, 'status': 'deleted'}

    def preview(self, memory_id):
        paths = self._locate(memory_id)
        if len(paths) != 1:
            raise Conflict('vault_note_missing_or_ambiguous')
        metadata, content = self._read(paths[0])
        if metadata['memory_id'] != memory_id:
            raise Conflict('vault_identity_conflict')
        records = self.ledger.active([{'id': memory_id, 'revision': metadata['revision']}])
        if len(records) != 1 or digest(records[0]['content']) != metadata['base_sha256']:
            raise Conflict('vault_stale_or_deleted_no_import')
        from ..intelligence import text
        content = text(content, 600)
        return {'memory_id': memory_id, 'revision': metadata['revision'],
                'content': content, 'changed': content != records[0]['content']}

    def import_revision(self, memory_id, revision):
        preview = self.preview(memory_id)
        if type(revision) is not int or preview['revision'] != revision:
            raise Conflict('vault_revision_conflict')
        current = self.ledger.active([{'id': memory_id, 'revision': revision}])[0]
        if not preview['changed']:
            return {'memory_id': memory_id, 'revision': revision, 'changed': False}
        record = self.ledger.save(current['key'], preview['content'], current['kind'],
            conversation_id=current['conversation_id'], project_id=current['project_id'],
            revision=revision, extractor='owner-confirmed-vault-edit')
        # Preserve the already-confirmed edit while replacing its base revision.
        self.export(record)
        return {'memory_id': memory_id, 'revision': record['revision'], 'changed': True}
