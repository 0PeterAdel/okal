#!/usr/bin/env python3
"""Owner-operated online readiness backup; never imports or migrates Core.

The destination contains credentials and owner content. Keep its manifest private.
SQLite is captured by its read-only online backup API. Other durable state must
remain hash-stable during capture; a race fails closed. A later live cutover still
requires a fresh quiesced backup, rather than reusing this readiness snapshot.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import tarfile


def sha(path: Path) -> str:
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def quoted(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def fingerprint(db: sqlite3.Connection) -> dict:
    result = {}
    for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        columns = [row[1] for row in db.execute('PRAGMA table_info(' + quoted(table) + ')')]
        digest = hashlib.sha256()
        count = 0
        for row in db.execute('SELECT * FROM ' + quoted(table) + ' ORDER BY ' + ','.join(map(quoted, columns))):
            values = [{'bytes': value.hex()} if isinstance(value, bytes) else value for value in row]
            raw = json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode()
            digest.update(len(raw).to_bytes(8, 'big') + raw)
            count += 1
        result[table] = {'count': count, 'rows_sha256': digest.hexdigest()}
    return result


def inventory(root: Path) -> dict:
    result = {}
    for directory, folders, files in os.walk(root, followlinks=False):
        for name in sorted(folders + files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if relative in {'core.sqlite3', 'core.sqlite3-wal', 'core.sqlite3-shm', 'core.sqlite3-journal'}:
                continue
            info = path.lstat()
            item = {'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid,
                    'gid': info.st_gid, 'mtime_ns': info.st_mtime_ns}
            if stat.S_ISREG(info.st_mode):
                if info.st_uid != os.getuid():
                    raise ValueError('foreign_owned_state_file')
                item.update(kind='file', size=info.st_size, sha256=sha(path))
            elif stat.S_ISLNK(info.st_mode):
                item.update(kind='symlink', target=os.readlink(path))
            elif stat.S_ISDIR(info.st_mode):
                item.update(kind='directory')
            else:
                raise ValueError('special_state_file_requires_operator_review')
            result[relative] = item
    return result


def save_json(path: Path, value: object) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    path.chmod(0o600)


def snapshot(state: Path, output: Path) -> dict:
    if not state.is_absolute() or state.is_symlink() or not state.is_dir():
        raise ValueError('explicit_owner_state_required')
    info = state.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('state_must_be_owner_private')
    if (not output.is_absolute() or output.exists() or state.resolve() == output.resolve()
            or state.resolve() in output.resolve().parents):
        raise ValueError('fresh_backup_outside_source_required')
    database = state / 'core.sqlite3'
    root_mode = stat.S_IMODE(info.st_mode)
    info = database.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('private_regular_database_required')
    output.mkdir(mode=0o700)
    before = inventory(state)
    database_copy = output / 'core.sqlite3'
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=5)) as source:
        source.execute('BEGIN')
        expected = fingerprint(source)
        with closing(sqlite3.connect(database_copy)) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('backup_integrity_failed')
            if target.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('backup_foreign_keys_failed')
            actual = fingerprint(target)
            if actual != expected:
                raise ValueError('backup_snapshot_mismatch')
    database_copy.chmod(0o600)
    archive = output / 'state-files.tar'
    with tarfile.open(archive, 'x', dereference=False) as bundle:
        for relative in sorted(before):
            bundle.add(state / relative, arcname=relative, recursive=False)
    archive.chmod(0o600)
    with tarfile.open(archive) as bundle:
        for member in bundle:
            expected_file = before[member.name]
            if member.isfile():
                with bundle.extractfile(member) as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                if digest != expected_file['sha256']:
                    raise ValueError('archived_file_hash_mismatch')
            elif member.islnk():
                if expected_file['sha256'] != before[member.linkname]['sha256']:
                    raise ValueError('archived_hardlink_mismatch')
    if inventory(state) != before:
        raise ValueError('live_state_changed_during_backup_retry_with_fresh_destination')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'online_snapshot': True,
              'quiesced_cutover_backup_still_required': True,
              'source_state': str(state), 'root_mode': root_mode,
              'sqlite_integrity': 'ok', 'foreign_key_violations': 0,
              'table_fingerprints': actual, 'files': before,
              'artifacts': {p.name: {'sha256': sha(p), 'bytes': p.stat().st_size,
                                   'mode': stat.S_IMODE(p.stat().st_mode)}
                            for p in (database_copy, archive)}}
    save_json(output / 'manifest-private.json', report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--service', required=True)
    parser.add_argument('--production-repo', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+\.service', args.service):
        parser.error('explicit_local_service_required')
    os.umask(0o077)
    report = snapshot(args.state, args.output)
    unit = subprocess.check_output(['systemctl', '--user', 'cat', args.service])
    (args.output / 'effective-unit-private.txt').write_bytes(unit)
    pid = int(subprocess.check_output(['systemctl', '--user', 'show', args.service, '-p', 'MainPID', '--value']))
    proc = Path('/proc') / str(pid)
    (args.output / 'process-environment-private.bin').write_bytes((proc / 'environ').read_bytes())
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=args.production_repo, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=args.production_repo).strip():
        raise ValueError('production_checkout_not_clean')
    with (args.output / 'baseline-source.tar').open('xb') as stream:
        subprocess.run(['git', 'archive', '--format=tar', head], cwd=args.production_repo, stdout=stream, check=True)
    unit_files = subprocess.check_output(['systemctl', '--user', 'show', args.service, '-p', 'FragmentPath', '--value'], text=True).split()
    unit_files += subprocess.check_output(['systemctl', '--user', 'show', args.service, '-p', 'DropInPaths', '--value'], text=True).split()
    save_json(args.output / 'installed-units-private.json',
              [{'path': value, 'mode': stat.S_IMODE(Path(value).stat().st_mode),
                'content': Path(value).read_text(), 'sha256': sha(Path(value))} for value in unit_files])
    report.update(baseline_head=head, service_pid=pid,
                  process_argv=(proc / 'cmdline').read_bytes().decode().split('\0'),
                  process_cwd=str((proc / 'cwd').resolve()))
    for path in args.output.iterdir():
        path.chmod(0o600)
        if path.name != 'manifest-private.json':
            report['artifacts'][path.name] = {'sha256': sha(path), 'bytes': path.stat().st_size,
                                            'mode': stat.S_IMODE(path.stat().st_mode)}
    # Atomic completion marker; partial directories are never reported verified.
    save_json(args.output / 'verified-private.json', report)
    print(json.dumps({'verified': True, 'integrity': 'ok', 'foreign_key_violations': 0,
                      'private_output': str(args.output), 'state_files': len(report['files'])}))


if __name__ == '__main__':
    main()
