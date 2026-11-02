"""Owner-reviewed local day planning, not Google Calendar automation.

No provider reads/writes, Ollama calls or guessed task durations. Calendar
availability is incomplete by design: every proposal is TENTATIVE.
"""
from datetime import date, datetime, time, timedelta
import hashlib
import json
import re
import secrets
import threading
from zoneinfo import ZoneInfo

from .calendar_core import CalendarCore
from .task_planner import TaskPlanner

CAIRO = ZoneInfo("Africa/Cairo")
CHOICES = frozenset({15, 30, 45, 60, 90, 120, 180, 240})
PRIORITY = {"high": 0, "normal": 1, "low": 2}
TASK_CAP = 12
CALENDAR_CAP = 200
TASK_SAMPLE_CAP = 100
MAX_TICKETS = 16
TICKET_SECONDS = 600


def _hhmm(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value
    ):
        raise ValueError("invalid_work_hour")
    h, m = map(int, value.split(":"))
    if m % 15:
        raise ValueError("work_minutes_must_be_quarters")
    return time(h, m)


def _choose_day(store, value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("invalid_plan_date")
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise ValueError("invalid_plan_date") from None
    today = datetime.fromtimestamp(store.clock(), CAIRO).date()
    if not today <= day < today + timedelta(days=7):
        raise ValueError("plan_date_outside_cached_week")
    return day


def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS owner_local_day_plans (
        id TEXT PRIMARY KEY, day TEXT NOT NULL, created_at INTEGER NOT NULL,
        digest TEXT NOT NULL, payload TEXT NOT NULL
    )""")


def _plan(store, payload):
    if type(payload) is not dict or set(payload) != {
        "date", "work_start", "work_end", "tasks"
    }:
        raise ValueError("invalid_day_plan_fields")
    day = _choose_day(store, payload["date"])
    begin = _hhmm(payload["work_start"])
    finish = _hhmm(payload["work_end"])
    if (datetime.combine(day, finish, CAIRO)
            - datetime.combine(day, begin, CAIRO)) not in (
            timedelta(hours=n) for n in range(1, 13)):
        # No overnight work shifts in the first review-only planner.
        # Use explicit daytime intervals of 1 to 12 exact hours.
        raise ValueError("invalid_daily_work_window")
    day_start = int(datetime.combine(day, begin, CAIRO).timestamp())
    day_end = int(datetime.combine(day, finish, CAIRO).timestamp())
    now = int(store.clock())
    selected = payload["tasks"]
    if not isinstance(selected, list) or not 1 <= len(selected) <= TASK_CAP:
        raise ValueError("invalid_selected_task_count")

    selections = {}
    for task in selected:
        if type(task) is not dict or set(task) != {
            "task_id", "minutes", "priority"
        }:
            raise ValueError("invalid_day_task_selection")
        key = task["task_id"]
        if (not isinstance(key, str) or
                not re.fullmatch(r"[a-f0-9]{32}", key) or key in selections or
                type(task["minutes"]) is not int or
                task["minutes"] not in CHOICES or
                task["priority"] not in PRIORITY):
            raise ValueError("invalid_day_task_estimate")
        selections[key] = task

    local = TaskPlanner(store).list("open", TASK_SAMPLE_CAP)
    if local["total_in_sample"] >= TASK_SAMPLE_CAP:
        raise ValueError("incomplete_task_sample")
    tasks = {item["id"]: item for item in local["items"]}
    if any(key not in tasks for key in selections):
        raise ValueError("task_closed_or_not_found")
    # Preserve provenance & compare selected task metadata on confirm.
    chosen = [tasks[key] for key in selections]
    calendar = CalendarCore(store).agenda(days=7, limit=CALENDAR_CAP)
    if calendar["count"] >= CALENDAR_CAP:
        raise ValueError("incomplete_calendar_event_sample")
    events = calendar["items"]
    busy = sorted(
        (max(int(e["start_ts"]), day_start),
         min(int(e["end_ts"]), day_end))
        for e in events if e["busy"]
        and e["start_ts"] < day_end and e["end_ts"] > day_start
    )
    occupied = [(start, end) for start, end in busy if end > start]
    # Rounded future time prevents planning into today's past hours.
    initial = max(day_start, ((now + 899) // 900) * 900) if (
        day == datetime.fromtimestamp(now, CAIRO).date()
    ) else day_start

    chosen.sort(key=lambda t: (
        PRIORITY[selections[t["id"]]["priority"]],
        t["due_at"] if t["due_at"] is not None else 2**62,
        t["id"],
    ))
    blocks, unplaced = [], []
    for task in chosen:
        opts = selections[task["id"]]
        duration = opts["minutes"] * 60
        deadline = task["due_at"]
        latest_end = min(day_end, deadline) if deadline is not None else day_end
        cursor = initial
        placed = False
        while cursor + duration <= latest_end:
            conflicts = [(start, end) for start, end in occupied
                         if start < cursor + duration and cursor < end]
            if not conflicts:
                blocks.append({
                    "task_id": task["id"], "title": task["title"],
                    "start_ts": cursor, "end_ts": cursor + duration,
                    "minutes": opts["minutes"], "priority": opts["priority"],
                    "status": "tentative_local_only",
                })
                occupied.append((cursor, cursor + duration))
                occupied.sort()
                placed = True
                break
            cursor = max(cursor + 900, max(end for _, end in conflicts))
            cursor = ((cursor + 899) // 900) * 900
        if not placed:
            unplaced.append({
                "task_id": task["id"], "title": task["title"],
                "reason": "deadline_or_window_too_short"
                    if latest_end < day_end else "no_slot_in_cached_events",
            })

    # Selected input and all calendar occupied events bind the approval
    # digest. New provider edits and task status/due changes invalidate it.
    source = {
        "input": payload, "task_revisions": [
            [task["id"], task["title"], task["due_at"],
             task["updated_at"], task["status"]] for task in chosen
        ],
        "busy_evidence": sorted(
            [e["provider"], e["account_id"], e["calendar_id"],
             e["event_id"], e["instance_id"], e["start_ts"],
             e["end_ts"], bool(e["busy"]), e["title"]]
            for e in events
        ),
        "blocks": blocks, "unplaced": unplaced,
    }
    digest = hashlib.sha256(
        json.dumps(source, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "date": day.isoformat(), "work_start": payload["work_start"],
        "work_end": payload["work_end"],
        "blocks": blocks, "unplaced": unplaced,
        "owner_review_required": True,
        "availability_verified": False,
        "coverage_status": "cached_sources_unverified",
        "source": "explicit_owner_estimates_and_local_google_cache",
        "external_reads": False, "external_writes": False,
        "ai_actions_executed": False,
        "plan_digest": digest,
    }


class DayPlanManager:
    """Single-user one-time preview/confirm; local database save only."""

    def __init__(self, store):
        self.store = store
        self._tickets = {}
        self._lock = threading.Lock()

    def preview(self, payload):
        result = _plan(self.store, payload)
        ticket = secrets.token_urlsafe(24)
        now = int(self.store.clock())
        with self._lock:
            self._tickets = {
                k: v for k, v in self._tickets.items() if v["expires"] > now
            }
            if len(self._tickets) >= MAX_TICKETS:
                raise ValueError("too_many_pending_plans")
            self._tickets[ticket] = {
                "payload": payload, "digest": result["plan_digest"],
                "expires": now + TICKET_SECONDS,
            }
        return {**result, "confirmation_token": ticket,
                "expires_seconds": TICKET_SECONDS}

    def confirm(self, ticket, confirmed):
        if confirmed is not True or not isinstance(ticket, str):
            raise ValueError("explicit_plan_confirmation_required")
        with self._lock:
            pending = self._tickets.pop(ticket, None)
        if pending is None or pending["expires"] <= int(self.store.clock()):
            raise ValueError("plan_preview_expired_or_consumed")
        latest = _plan(self.store, pending["payload"])
        if latest["plan_digest"] != pending["digest"]:
            raise ValueError("day_plan_sources_changed_retry_preview")
        plan_id = secrets.token_hex(16)
        with self.store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            _schema(db)
            db.execute(
                "INSERT INTO owner_local_day_plans VALUES(?,?,?,?,?)",
                (plan_id, latest["date"], int(self.store.clock()),
                 latest["plan_digest"],
                 json.dumps({k: v for k, v in latest.items()
                             if k != "plan_digest"}, ensure_ascii=False)),
            )
        return {
            "status": "saved_locally_only", "plan_id": plan_id,
            "date": latest["date"], "blocks_saved": len(latest["blocks"]),
            "unplaced_count": len(latest["unplaced"]),
            "external_writes": False, "google_events_created": 0,
            "task_deadlines_changed": 0,
            "source_coverage_verified": False,
        }

    def saved(self):
        with self.store.connect() as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='owner_local_day_plans'"
            ).fetchone()
            if not exists:
                return {"items": [], "external_writes": False}
            rows = db.execute(
                "SELECT id,day,created_at,payload FROM owner_local_day_plans "
                "ORDER BY created_at DESC,id DESC LIMIT 5"
            ).fetchall()
        return {
            "items": [
                {"id": row["id"], "date": row["day"],
                 "created_at": row["created_at"], **json.loads(row["payload"])}
                for row in rows
            ],
            "source": "owner_approved_private_sqlite",
            "external_writes": False,
        }
