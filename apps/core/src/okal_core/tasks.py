"""Owner-controlled local task board over saved Gmail evidence.

No Google Tasks/Calendar writes, Gmail operations, automation tool execution,
or Ollama generation. All state changes require explicit local CLI commands.
"""
from datetime import datetime, timezone
import json
import re
import sqlite3
from uuid import uuid4

from .mail.contracts import Insight
from .mail.workflows import source_link


TASK_STATES = frozenset({"open", "done", "dismissed"})
ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
MID_PATTERN = re.compile(r"^[a-fA-F0-9]{1,64}$")


def validated_title(title):
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 180:
        raise ValueError("task_title_required_max_180")
    if any(ord(c) < 32 or ord(c) == 127 for c in title):
        raise ValueError("task_title_control_characters_forbidden")
    return title.strip()


def validated_notes(notes):
    if not isinstance(notes, str) or len(notes) > 2000:
        raise ValueError("task_notes_max_2000")
    return notes


def due_timestamp(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 50:
        raise ValueError("due_requires_iso8601_timezone")
    try:
        due = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if due.tzinfo is None or due.utcoffset() is None:
            raise ValueError()
        ts = int(due.astimezone(timezone.utc).timestamp())
        if not 0 <= ts <= 4102444800:
            raise ValueError()
        return ts
    except (ValueError, OverflowError):
        raise ValueError("due_requires_iso8601_timezone") from None


class TaskBoard:
    def __init__(self, store):
        self.store = store

    def _exists(self):
        with self.store.connect() as db:
            return db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='local_tasks'"
            ).fetchone() is not None

    def _init(self, db):
        db.execute("""CREATE TABLE IF NOT EXISTS local_tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            notes TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('open','done','dismissed')),
            due_at INTEGER,
            source_type TEXT NOT NULL CHECK(source_type IN ('manual','gmail')),
            account TEXT,
            source_id TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            CHECK((source_type='manual' AND account IS NULL AND source_id IS NULL)
                  OR (source_type='gmail' AND account IS NOT NULL AND source_id IS NOT NULL))
        )""")
        db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS local_tasks_unique_mail
            ON local_tasks(account,source_id) WHERE source_type='gmail'""")
        db.execute("""CREATE INDEX IF NOT EXISTS local_tasks_by_due
            ON local_tasks(status,due_at,created_at)""")

    def list(self, status="open", limit=100):
        if status not in TASK_STATES | {"all"} or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("invalid_task_filter")
        if not self._exists():
            return {"items": [], "total_in_sample": 0, "status_filter": status,
                    "external_writes": False, "provider_connections": False}
        query = """SELECT id,title,notes,status,due_at,source_type,account,
                          source_id,created_at,updated_at FROM local_tasks"""
        args = []
        if status != "all":
            query += " WHERE status=?"
            args.append(status)
        query += """ ORDER BY CASE WHEN status='open' THEN 0 ELSE 1 END,
                       CASE WHEN due_at IS NULL THEN 1 ELSE 0 END,
                       due_at ASC, created_at DESC, id DESC LIMIT ?"""
        args.append(limit)
        with self.store.connect() as db:
            rows = [dict(r) for r in db.execute(query, args)]
        for row in rows:
            row["source_link"] = (
                source_link(row["account"], row["source_id"])
                if row["source_type"] == "gmail" else None
            )
            row.pop("account", None)
        now = int(self.store.clock())
        return {
            "items": rows, "total_in_sample": len(rows),
            "status_filter": status, "external_writes": False,
            "provider_connections": False,
            "overdue_in_sample": sum(
                r["status"] == "open" and r["due_at"] is not None
                and r["due_at"] < now for r in rows
            ),
            "note": "Owner-approved local tasks only. No external reminders or Google Calendar events created.",
        }

    def add(self, title, notes="", due=None):
        title = validated_title(title)
        notes = validated_notes(notes)
        when = due_timestamp(due)
        now = int(self.store.clock())
        key = uuid4().hex
        with self.store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._init(db)
            db.execute(
                "INSERT INTO local_tasks VALUES(?,?,?,'open',?,'manual',NULL,NULL,?,?)",
                (key, title, notes, when, now, now),
            )
        return {"task_id": key, "status": "open", "source": "manual",
                "external_writes": False}

    def from_mail(self, account, message_id, title=None, due=None, approve=False):
        # A user must explicitly approve adding an identified source email.
        # We never copy untrusted model instructions into executable actions.
        if not MID_PATTERN.fullmatch(message_id):
            raise ValueError("invalid_source_message_id")
        if title is not None:
            title = validated_title(title)
        when = due_timestamp(due)
        with self.store.connect() as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mail_sync_insights'"
            ).fetchone()
            if not exists:
                raise ValueError("no_saved_gmail_insights")
            row = db.execute(
                "SELECT metadata,insight FROM mail_sync_insights "
                "WHERE account=? AND message_id=? ORDER BY rowid DESC LIMIT 1",
                (account.casefold(), message_id),
            ).fetchone()
        if row is None:
            raise ValueError("source_email_not_in_local_history")
        try:
            metadata = json.loads(row["metadata"])
            insight = Insight.model_validate_json(row["insight"])
            if metadata["id"] != message_id or insight.source_id != message_id:
                raise ValueError()
            subject = metadata["subject"]
            if not isinstance(subject, str):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise ValueError("untrusted_source_provenance_invalid") from None
        safe_subject = subject[:140].replace("\n", " ").replace("\r", " ")
        proposed_title = validated_title(title or ("Review email: " + safe_subject))
        if not approve:
            return {
                "status": "approval_required",
                "proposed_title": proposed_title,
                "source_link": source_link(account, message_id),
                "due_at": when,
                "warning": "Verify in Gmail. --approve records a local task only; no mail is sent.",
            }

        now = int(self.store.clock())
        key = uuid4().hex
        with self.store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._init(db)
            existing = db.execute(
                "SELECT id FROM local_tasks WHERE source_type='gmail' "
                "AND account=? AND source_id=?",
                (account.casefold(), message_id),
            ).fetchone()
            if existing:
                return {"task_id": existing["id"], "status": "already_recorded",
                        "external_writes": False}
            try:
                db.execute(
                    "INSERT INTO local_tasks VALUES(?,?,?,'open',?,'gmail',?,?,?,?)",
                    (key, proposed_title, "", when, account.casefold(),
                     message_id, now, now),
                )
            except sqlite3.IntegrityError:
                # A concurrent approval won. Never duplicate Gmail tasks.
                row = db.execute(
                    "SELECT id FROM local_tasks WHERE source_type='gmail' "
                    "AND account=? AND source_id=?",
                    (account.casefold(), message_id),
                ).fetchone()
                if row:
                    return {"task_id": row["id"], "status": "already_recorded",
                            "external_writes": False}
                raise
        return {"task_id": key, "status": "open", "source": "gmail",
                "external_writes": False}

    def transition(self, task_id, status):
        if status not in {"done", "dismissed"} or not ID_PATTERN.fullmatch(task_id):
            raise ValueError("invalid_task_transition")
        if not self._exists():
            raise ValueError("task_not_found")
        with self.store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            updated = db.execute(
                "UPDATE local_tasks SET status=?, updated_at=? "
                "WHERE id=? AND status='open'",
                (status, int(self.store.clock()), task_id),
            ).rowcount
            if not updated:
                old = db.execute(
                    "SELECT status FROM local_tasks WHERE id=?", (task_id,)
                ).fetchone()
                if old and old["status"] == status:
                    return {"task_id": task_id, "status": status, "replayed": True}
                raise ValueError("task_not_open_or_not_found")
        return {"task_id": task_id, "status": status, "replayed": False}
