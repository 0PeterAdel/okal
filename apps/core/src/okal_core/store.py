"""Small transactional inbox, not a scheduler or an external-write ledger."""

import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
import uuid

from .models import SummaryInput


class Conflict(ValueError):
    """An existing occurrence has different content; do not overwrite it."""


class InvalidCursor(ValueError):
    pass


def private_directory(path: Path) -> Path:
    path = path.expanduser().absolute()
    if path.is_symlink():
        raise ValueError("state directory must not be a symlink")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("state directory must be owner-only (0700)")
    return path


def private_file(path: Path) -> None:
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise ValueError("database must be an owner-only regular file (0600)")
    finally:
        os.close(fd)


class Store:
    def __init__(self, directory: Path, clock=time.time):
        self.directory = private_directory(directory)
        self.path = self.directory / "core.sqlite3"
        self.clock = clock
        private_file(self.path)
        with self.connect() as db, db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("unsupported database version; do not downgrade")
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, verifier TEXT UNIQUE NOT NULL,
                scope TEXT NOT NULL CHECK(scope='inbox:read'),
                expires_at INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)""")
            db.execute("""CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, workflow TEXT NOT NULL, account_ref TEXT NOT NULL,
                occurrence TEXT NOT NULL, digest TEXT NOT NULL, created_at INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status='succeeded'),
                UNIQUE(workflow, account_ref, occurrence))""")
            db.execute("""CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL UNIQUE
                REFERENCES runs(id), title TEXT NOT NULL, body TEXT NOT NULL,
                data_kind TEXT NOT NULL CHECK(data_kind IN ('fixture','live')))""")
            db.execute("PRAGMA user_version=1")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    def issue_device(self, name: str, days: int = 30) -> dict:
        if (
            not name.strip()
            or len(name) > 80
            or type(days) is not int
            or not 1 <= days <= 90
        ):
            raise ValueError("device name required (1-80 chars), lifetime 1-90 days")
        token = secrets.token_urlsafe(32)
        device = {
            "id": uuid.uuid4().hex,
            "name": name,
            "token": token,
            "expires_at": int(self.clock()) + days * 86400,
            "scope": "inbox:read",
        }
        with self.connect() as db, db:
            db.execute(
                "INSERT INTO devices VALUES(?,?,?,?,?,0)",
                (
                    device["id"],
                    name,
                    hashlib.sha256(token.encode()).hexdigest(),
                    device["scope"],
                    device["expires_at"],
                ),
            )
        return device

    def authenticate(self, token: str) -> bool:
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            return False
        verifier = hashlib.sha256(token.encode("ascii")).hexdigest()
        with self.connect() as db:
            row = db.execute(
                "SELECT verifier FROM devices WHERE verifier=? AND revoked=0 "
                "AND expires_at>? AND scope='inbox:read'",
                (verifier, int(self.clock())),
            ).fetchone()
        return row is not None and secrets.compare_digest(row["verifier"], verifier)

    def revoke_device(self, device_id: str) -> bool:
        with self.connect() as db, db:
            return (
                db.execute(
                    "UPDATE devices SET revoked=1 WHERE id=?", (device_id,)
                ).rowcount
                == 1
            )

    def list_devices(self) -> list:
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id,name,scope,expires_at,revoked FROM devices ORDER BY id"
                )
            ]

    def record_success(self, item: SummaryInput) -> str:
        # Revalidate even instances constructed without Pydantic validation.
        item = SummaryInput.model_validate(item.model_dump())
        digest = hashlib.sha256(
            json.dumps(item.model_dump(), sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        with self.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT id,digest FROM runs WHERE workflow=? AND account_ref=? "
                "AND occurrence=?",
                (item.workflow, item.account_ref, item.occurrence),
            ).fetchone()
            if old:
                if old["digest"] != digest:
                    raise Conflict("occurrence already recorded with different content")
                return old["id"]
            run_id = uuid.uuid4().hex
            db.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
                (
                    run_id,
                    item.workflow,
                    item.account_ref,
                    item.occurrence,
                    digest,
                    int(self.clock()),
                    "succeeded",
                ),
            )
            db.execute(
                "INSERT INTO summaries(run_id,title,body,data_kind) VALUES(?,?,?,?)",
                (run_id, item.title, item.body, item.data_kind),
            )
        return run_id

    def get_run(self, run_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT r.id,r.workflow,r.status,r.created_at,s.id AS summary_id,"
                "s.data_kind FROM runs r JOIN summaries s ON s.run_id=r.id "
                "WHERE r.id=?",
                (run_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_summaries(self, limit: int = 20, cursor: str | None = None) -> dict:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be 1-100")
        with self.connect() as db:
            if cursor is None:
                snapshot = db.execute(
                    "SELECT COALESCE(MAX(id),0) FROM summaries"
                ).fetchone()[0]
                before = snapshot + 1
            else:
                try:
                    if len(cursor) > 160 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
                        raise ValueError()
                    state = json.loads(
                        base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
                    )
                    if (
                        set(state) != {"v", "b", "s"}
                        or type(state["v"]) is not int
                        or state["v"] != 1
                    ):
                        raise ValueError()
                    before, snapshot = state["b"], state["s"]
                    if (
                        type(before) is not int
                        or type(snapshot) is not int
                        or not 0 < before <= snapshot + 1 < 2**63
                    ):
                        raise ValueError()
                except (ValueError, TypeError, KeyError, UnicodeError) as exc:
                    raise InvalidCursor("invalid cursor") from exc
            rows = db.execute(
                "SELECT s.id,s.run_id,s.title,s.body,s.data_kind,r.workflow,r.created_at "
                "FROM summaries s JOIN runs r ON r.id=s.run_id "
                "WHERE s.id<? AND s.id<=? ORDER BY s.id DESC LIMIT ?",
                (before, snapshot, limit + 1),
            ).fetchall()
        items = [dict(r) for r in rows[:limit]]
        next_cursor = None
        if len(rows) > limit:
            state = {"v": 1, "b": items[-1]["id"], "s": snapshot}
            next_cursor = (
                base64.urlsafe_b64encode(json.dumps(state).encode())
                .decode()
                .rstrip("=")
            )
        return {
            "schema_version": 1,
            "items": items,
            "next_cursor": next_cursor,
            "fetched_at": int(self.clock()),
        }

    def backup(self, destination: Path) -> None:
        # Refuse overwrite; use SQLite's backup API, never copy a live DB file.
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        with self.connect() as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
