"""Owner-owned commitments in SQLite; no provider, model or schedule inference."""
from datetime import date
from hashlib import sha256
import json

from .tasks import ID_PATTERN, due_timestamp, validated_title, validated_notes
from .task_planner import validate_lead


class LocalCalendarConflict(ValueError):
    pass


def identity(value):
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ValueError("invalid_local_calendar_id")
    return value


class LocalCalendar:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def _init(db):
        db.execute("""CREATE TABLE IF NOT EXISTS local_commitments (
            id TEXT PRIMARY KEY, create_digest TEXT NOT NULL,
            kind TEXT NOT NULL, title TEXT NOT NULL, notes TEXT NOT NULL,
            start_ts INTEGER, end_ts INTEGER, target_date TEXT,
            reminder_minutes INTEGER, reminder_status TEXT NOT NULL,
            status TEXT NOT NULL, revision INTEGER NOT NULL,
            created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS local_commitments_time "
                   "ON local_commitments(status,start_ts,target_date)")

    def list(self, include_closed=False, window=None):
        with self.store.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='local_commitments'").fetchone():
                return {"items": [], "limit_reached": False, "external_writes": False}
            where = [] if include_closed else ["status='open'"]
            parameters = ()
            if window is not None:
                where.append("(kind='goal' OR (end_ts>? AND start_ts<?))")
                parameters = tuple(window)
            rows = [dict(r) for r in db.execute(
                "SELECT id,kind,title,notes,start_ts,end_ts,target_date,reminder_minutes,"
                "reminder_status,status,revision,created_at,updated_at FROM local_commitments "
                + ("WHERE " + " AND ".join(where) + " " if where else "")
                + "ORDER BY COALESCE(start_ts,253402300799),target_date,id LIMIT 501", parameters
            )]
        return {"items": rows[:500], "limit_reached": len(rows) > 500,
                "external_writes": False}

    def save(self, payload):
        required = {"id", "revision", "kind", "title", "notes", "start", "end",
                    "target_date", "reminder_minutes"}
        if not isinstance(payload, dict) or set(payload) != required:
            raise ValueError("invalid_local_calendar_fields")
        key = identity(payload["id"])
        revision = payload["revision"]
        if type(revision) is not int or revision < 0:
            raise ValueError("invalid_local_calendar_revision")
        kind = payload["kind"]
        title, notes = validated_title(payload["title"]), validated_notes(payload["notes"])
        target = payload["target_date"]
        start, end, lead = None, None, None
        if kind == "event":
            start, end = due_timestamp(payload["start"]), due_timestamp(payload["end"])
            if start is None or end is None or not 0 < end - start <= 366 * 86400 or target is not None:
                raise ValueError("invalid_local_event_interval")
            lead = validate_lead(payload["reminder_minutes"], start)
        elif kind == "goal":
            if any(payload[k] is not None for k in ("start", "end", "reminder_minutes")):
                raise ValueError("goal_has_no_clock_time")
            if target is not None:
                if not isinstance(target, str) or len(target) != 10 or date.fromisoformat(target).isoformat() != target:
                    raise ValueError("invalid_goal_date")
        else:
            raise ValueError("invalid_local_calendar_kind")
        values = (kind, title, notes, start, end, target, lead)
        digest = sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()
        now = int(self.store.clock())
        with self.store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._init(db)
            prior = db.execute("SELECT * FROM local_commitments WHERE id=?", (key,)).fetchone()
            if revision == 0:
                if prior:
                    if prior["create_digest"] != digest:
                        raise LocalCalendarConflict("local_calendar_request_changed")
                    return {"id": key, "revision": prior["revision"], "replayed": True}
                db.execute("INSERT INTO local_commitments VALUES(?,?,?,?,?,?,?,?,?,?,'open',1,?,?)",
                           (key, digest, *values, "scheduled" if lead is not None else "none", now, now))
            else:
                if not prior or prior["revision"] != revision or prior["status"] != "open":
                    raise LocalCalendarConflict("local_calendar_revision_changed")
                # A notes/title edit must not re-arm a reminder already attempted.
                reminder = (prior["reminder_status"] if start == prior["start_ts"] and lead == prior["reminder_minutes"]
                            else "scheduled" if lead is not None else "none")
                db.execute("UPDATE local_commitments SET kind=?,title=?,notes=?,start_ts=?,end_ts=?,"
                           "target_date=?,reminder_minutes=?,reminder_status=?,revision=revision+1,"
                           "updated_at=? WHERE id=?", (*values, reminder, now, key))
        return {"id": key, "revision": revision + 1, "replayed": False, "external_writes": False}

    def transition(self, key, revision, status):
        identity(key)
        if type(revision) is not int or revision < 1 or status not in {"done", "cancelled"}:
            raise ValueError("invalid_local_calendar_transition")
        with self.store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._init(db)
            changed = db.execute("UPDATE local_commitments SET status=?,revision=revision+1,"
                                 "reminder_status='cancelled',updated_at=? WHERE id=? AND revision=? AND status='open'",
                                 (status, int(self.store.clock()), key, revision)).rowcount
            if not changed:
                raise LocalCalendarConflict("local_calendar_revision_changed")
        return {"id": key, "status": status, "external_writes": False}

    def claim_due(self):
        now = int(self.store.clock())
        with self.store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._init(db)
            rows = db.execute("SELECT id,title,revision,reminder_minutes,start_ts FROM local_commitments "
                              "WHERE status='open' AND reminder_status='scheduled' "
                              "AND start_ts-reminder_minutes*60<=? ORDER BY start_ts LIMIT 10", (now,)).fetchall()
            claimed = []
            for row in rows:
                state = "missed" if now - (row["start_ts"] - row["reminder_minutes"] * 60) > 900 else "attempting"
                db.execute("UPDATE local_commitments SET reminder_status=? WHERE id=?", (state, row["id"]))
                if state == "attempting":
                    claimed.append(dict(row))
            return claimed

    def finish_notification(self, key, revision, success):
        with self.store.connect() as db, db:
            db.execute("UPDATE local_commitments SET reminder_status=? "
                       "WHERE id=? AND revision=? AND reminder_status='attempting'",
                       ("sent" if success else "failed", key, revision))
