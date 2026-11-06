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
        from .ledger import CREDENTIAL_CATEGORY
        return not CREDENTIAL_CATEGORY.search(record['key']+' '+record['content']) and (record['scope']=='owner' or record['scope'].startswith('project:')
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
            try:
                metadata[key] = json.loads(value)
            except json.JSONDecodeError:
                # Obsidian Properties may emit ordinary unquoted YAML scalars.
                # Accept only our inert identifiers; never evaluate YAML tags,
                # aliases, multiline values or arbitrary object constructors.
                if not re.fullmatch(r'[a-zA-Z0-9_:-]{1,100}',value):
                    raise ValueError('invalid_vault_scalar') from None
                metadata[key] = value
        identity = 'project_id' if 'project_id' in metadata else 'memory_id'
        if set(metadata) != {'okal', identity, 'revision', 'scope', 'base_sha256', 'source_turn'}:
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

    def _write(self, path, metadata, title, content, links=''):
        title = html.escape(title).translate(str.maketrans({'\n':' ','#':'','[':'',']':''}))
        raw = '---\n' + '\n'.join(k + ': ' + json.dumps(v, ensure_ascii=False)
                                   for k,v in metadata.items()) + '\n---\n# ' + title + '\n'
        fence='`'*max(3,1+max((len(v) for v in re.findall(r'`+',content)),default=0))
        raw += links + '\nOwner statement; not independently verified.\n\n## Owner statement\n\n'
        raw += fence+'text\n'+content+'\n'+fence+'\n'
        temporary = path.with_name('.' + uuid.uuid4().hex + '.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)

    def _project(self, db, project_id):
        from ..intelligence import identifier, Missing
        identifier(project_id)
        row=db.execute('SELECT * FROM memory_projects WHERE id=?',(project_id,)).fetchone()
        if row is None: raise Missing('project_not_found')
        return dict(row)

    def export_project(self, project_id):
        with self.ledger._transaction() as db:
            record=self._project(db,project_id)
            path=private_directory(self.root/'projects')/('project-'+project_id+'.md')
            if path.exists() or path.is_symlink():
                metadata,content=self._read(path)
                if metadata.get('project_id')!=project_id:
                    raise Conflict('vault_identity_conflict')
                if (digest(content)!=metadata['base_sha256'] and content!=record['description']
                        or metadata['revision']>record['revision']):
                    raise Conflict('vault_owner_edit_requires_import_or_discard')
            ids=[r[0] for r in db.execute('''SELECT m.id FROM chat_memories m
                JOIN memory_meta x ON x.memory_id=m.id WHERE x.project_id=?
                AND (m.expires_at=0 OR m.expires_at>?) ORDER BY m.updated_at DESC,m.id LIMIT 40''',
                (project_id,self.ledger.now))]
            # Only ledger-controlled IDs occur in active links. Descriptions
            # and titles cannot inject Markdown or cause network requests.
            links='\n## Current knowledge\n\n'+'\n'.join('- [[memory-'+v+']]' for v in ids)+'\n'
            metadata={'okal':2,'project_id':project_id,'revision':record['revision'],
                'scope':'project:'+project_id,'base_sha256':digest(record['description']),'source_turn':None}
            self._write(path,metadata,record['name'],record['description'],links)
            return {'project_id':project_id,'revision':record['revision'],'status':'current'}

    def preview_project(self, project_id):
        with self.ledger.store.connect() as db:
            record=self._project(db,project_id)
        path=private_directory(self.root/'projects')/('project-'+project_id+'.md')
        metadata,content=self._read(path)
        if (metadata.get('project_id')!=project_id or metadata['revision']!=record['revision']
                or metadata['base_sha256']!=digest(record['description'])):
            raise Conflict('vault_stale_project_no_import')
        from ..intelligence import text
        content=text(content,600) if content else ''
        return {'project_id':project_id,'revision':record['revision'],'content':content,
                'content_sha256':digest(content),
                'changed':content!=record['description']}

    def import_project(self, project_id, revision, content_sha256):
        preview=self.preview_project(project_id)
        if (type(revision) is not int or revision!=preview['revision']
                or content_sha256!=preview['content_sha256']):
            raise Conflict('vault_revision_conflict')
        with self.ledger.store.connect() as db:
            record=self._project(db,project_id)
        if preview['changed']:
            record=self.ledger.save_project(record['name'],preview['content'],project_id,revision)
            self.export_project(project_id)
        return {'project_id':project_id,'revision':record['revision'],'changed':preview['changed']}

    def export(self, record):
        with self.ledger._transaction() as db:
            current = db.execute('SELECT revision,content FROM chat_memories WHERE id=?', (record['id'],)).fetchone()
            if current is None or current['revision'] != record['revision'] or current['content'] != record['content']:
                raise Conflict('vault_stale_or_deleted_no_export')
            return self._export(record)

    def _export(self, record):
        prior_paths=self._locate(record['id'])
        for prior_path in prior_paths:
            metadata, content = self._read(prior_path)
            if metadata['memory_id'] != record['id']:
                raise Conflict('vault_identity_conflict')
            if digest(content) != metadata['base_sha256'] and content != record['content']:
                raise Conflict('vault_owner_edit_requires_import_or_discard')
            if metadata['revision'] > record['revision']:
                raise Conflict('vault_newer_revision_conflict')
        if not self.curated(record):
            self.delete(record['id'])
            return {'memory_id':record['id'],'revision':record['revision'],'status':'not_curated'}
        path = self._path(record)
        metadata = {'okal': 2, 'memory_id': record['id'], 'revision': record['revision'],
                    'scope': record['scope'], 'base_sha256': digest(record['content']),
                    'source_turn': record.get('source_turn')}
        titles={'communication.language':'Reply language','communication.style':'Communication style',
                'communication.structure':'Response structure','architecture.database':'Database decision'}
        title = titles.get(record['key'],record['key'].replace('_',' ').replace('.',' '))
        link = '\nProject: [[project-' + record['scope'][8:] + ']]\n' if record['scope'].startswith('project:') else ''
        # Literal text fences prevent an automatically extracted remote image,
        # HTML tag or link from making Obsidian fetch private URLs on open.
        self._write(path,metadata,title,record['content'],link)
        # A kind correction can move the same stable ID between folders.
        # Validate every previous note before removing an obsolete projection;
        # an independently edited note requires owner conflict resolution.
        for prior_path in prior_paths:
            if prior_path!=path:prior_path.unlink()
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
                'content_sha256':digest(content),
                'content': content, 'changed': content != records[0]['content']}

    def import_revision(self, memory_id, revision, content_sha256):
        preview = self.preview(memory_id)
        if (type(revision) is not int or preview['revision'] != revision
                or content_sha256!=preview['content_sha256']):
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
