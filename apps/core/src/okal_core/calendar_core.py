"""Local-first, provider-neutral Calendar cache and deterministic AI policy.

No network calls, OAuth credentials or calendar writes. Provider adapters in
future PRs must run outside the HTTP request path and persist complete,
validated, versioned provider changes through ingest().
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PROVIDERS = frozenset({"google", "microsoft", "icloud", "caldav", "local"})
ACTIONS = frozenset({"read", "summarize", "propose", "create", "update", "delete"})
MAX_EVENTS_PER_BATCH = 200
ZONE = ZoneInfo("Africa/Cairo")


class CalendarConflict(ValueError):
    """Equal or older provider revision must not replace a different event."""


def _text(value, field, maximum, *, nullable=False):
    if nullable and value is None:
        return ""
    if not isinstance(value, str) or not value or len(value) > maximum or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        raise ValueError("invalid_calendar_" + field)
    return value


def _instant(value, field):
    if not isinstance(value, str) or len(value) > 48:
        raise ValueError("invalid_calendar_" + field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("invalid_calendar_" + field) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("calendar_timezone_offset_required")
    return parsed.astimezone(timezone.utc)


def _clean_event(item):
    if not isinstance(item, dict) or set(item) - {
        "id", "title", "start", "end", "updated", "timezone",
        "instance_id", "all_day", "busy", "cancelled"
    }:
        raise ValueError("invalid_calendar_event_fields")
    eid = _text(item.get("id"), "event_id", 200)
    title = _text(item.get("title"), "event_title", 250)
    instance = _text(item.get("instance_id"), "instance_id", 200, nullable=True)
    tz = _text(item.get("timezone"), "timezone", 100)
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("invalid_calendar_timezone") from None
    start = _instant(item.get("start"), "start")
    end = _instant(item.get("end"), "end")
    updated = _instant(item.get("updated"), "updated")
    # Timed zero-duration events are valid instantaneous markers, not booked
    # intervals. All-day events still require an exclusive end date.
    if (end < start or end - start > timedelta(days=366)
            or (end == start and item.get("all_day", False))):
        raise ValueError("invalid_calendar_event_interval")
    for field in ("all_day", "busy", "cancelled"):
        if type(item.get(field, False)) is not bool:
            raise ValueError("invalid_calendar_" + field)
    result = {
        "id": eid, "instance_id": instance, "title": title,
        "start_utc": start.isoformat(), "end_utc": end.isoformat(),
        "start_ts": int(start.timestamp()), "end_ts": int(end.timestamp()),
        "updated_us": int(updated.timestamp() * 1_000_000),
        "timezone": tz, "all_day": item.get("all_day", False),
        "busy": (item.get("busy", True) and end > start), "cancelled": item.get("cancelled", False),
    }
    result["digest"] = hashlib.sha256(
        json.dumps(result, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return result


class CalendarCore:
    """SQLite projection of provider-owned calendar events; no provider I/O."""

    def __init__(self, store):
        self.store = store

    @staticmethod
    def _init(db):
        db.execute("""CREATE TABLE IF NOT EXISTS calendar_source_events (
            provider TEXT NOT NULL, account_id TEXT NOT NULL,
            calendar_id TEXT NOT NULL, event_id TEXT NOT NULL,
            instance_id TEXT NOT NULL, title TEXT NOT NULL,
            start_utc TEXT NOT NULL, end_utc TEXT NOT NULL,
            start_ts INTEGER NOT NULL, end_ts INTEGER NOT NULL,
            timezone TEXT NOT NULL, all_day INTEGER NOT NULL,
            busy INTEGER NOT NULL, cancelled INTEGER NOT NULL,
            updated_us INTEGER NOT NULL, digest TEXT NOT NULL,
            PRIMARY KEY (provider, account_id, calendar_id, event_id, instance_id)
        )""")
        db.execute("""CREATE INDEX IF NOT EXISTS calendar_source_time
            ON calendar_source_events(start_ts, end_ts)""")

    def ingest(self, provider, account_id, calendar_id, items):
        """Adapter-only ingestion, atomically rejects collisions and stale data.

        Incremental batches are NOT replacement snapshots: omitted events are
        preserved. Providers must explicitly send cancelled/tombstone events.
        Cursor checkpoints belong to provider-specific adapters and must only
        advance after every page has been ingested successfully.
        """
        if provider not in PROVIDERS:
            raise ValueError("invalid_calendar_provider")
        account_id = _text(account_id, "account", 200)
        calendar_id = _text(calendar_id, "calendar", 250)
        if not isinstance(items, list) or len(items) > MAX_EVENTS_PER_BATCH:
            raise ValueError("invalid_calendar_batch")
        cleaned = [_clean_event(item) for item in items]
        if len({(x["id"], x["instance_id"]) for x in cleaned}) != len(cleaned):
            raise ValueError("duplicate_calendar_batch_event")
        written = 0
        skipped = 0
        with self.store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._init(db)
            for event in cleaned:
                identity = (provider, account_id, calendar_id, event["id"], event["instance_id"])
                prior = db.execute("""SELECT updated_us,digest
                    FROM calendar_source_events WHERE provider=? AND account_id=?
                    AND calendar_id=? AND event_id=? AND instance_id=?""", identity).fetchone()
                if prior is not None:
                    if prior["updated_us"] > event["updated_us"]:
                        skipped += 1
                        continue
                    if prior["updated_us"] == event["updated_us"]:
                        if prior["digest"] != event["digest"]:
                            raise CalendarConflict("calendar_revision_collision")
                        skipped += 1
                        continue
                db.execute("""INSERT INTO calendar_source_events VALUES
                    (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(provider,account_id,calendar_id,event_id,instance_id)
                    DO UPDATE SET title=excluded.title,start_utc=excluded.start_utc,
                    end_utc=excluded.end_utc,start_ts=excluded.start_ts,
                    end_ts=excluded.end_ts,timezone=excluded.timezone,
                    all_day=excluded.all_day,busy=excluded.busy,
                    cancelled=excluded.cancelled,updated_us=excluded.updated_us,
                    digest=excluded.digest""",
                    identity + (event["title"], event["start_utc"], event["end_utc"],
                                event["start_ts"], event["end_ts"], event["timezone"],
                                int(event["all_day"]), int(event["busy"]),
                                int(event["cancelled"]), event["updated_us"], event["digest"]))
                written += 1
        return {"written": written, "unchanged_or_stale": skipped, "external_writes": False}

    def agenda(self, days=14, limit=200):
        if type(days) is not int or not 1 <= days <= 31:
            raise ValueError("invalid_calendar_window")
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("invalid_calendar_limit")
        today = datetime.fromtimestamp(int(self.store.clock()), ZONE).date()
        start = datetime.combine(today, datetime.min.time(), tzinfo=ZONE)
        end = datetime.combine(today + timedelta(days=days), datetime.min.time(), tzinfo=ZONE)
        start_ts, end_ts = int(start.timestamp()), int(end.timestamp())
        with self.store.connect() as db, db:
            self._init(db)
            rows = [dict(row) for row in db.execute(
                """SELECT provider,account_id,calendar_id,event_id,instance_id,
                    title,start_utc,end_utc,timezone,all_day,busy,start_ts,end_ts
                    FROM calendar_source_events
                    WHERE cancelled=0 AND ((start_ts<? AND end_ts>?) OR (start_ts=end_ts AND start_ts>=? AND start_ts<?))
                    ORDER BY start_ts,provider,account_id,calendar_id,event_id
                    LIMIT ?""", (end_ts, start_ts, start_ts, end_ts, limit)
            )]
        for row in rows:
            row["all_day"] = bool(row["all_day"])
            row["busy"] = bool(row["busy"])
        from .local_calendar import LocalCalendar
        for item in LocalCalendar(self.store).list(window=(start_ts, end_ts))["items"]:
            if item["kind"] != "event" or item["start_ts"] >= end_ts or item["end_ts"] <= start_ts:
                continue
            rows.append({
                "provider": "local", "account_id": "owner", "calendar_id": "okal",
                "event_id": item["id"], "instance_id": "", "title": item["title"],
                "start_ts": item["start_ts"], "end_ts": item["end_ts"],
                "start_utc": datetime.fromtimestamp(item["start_ts"], timezone.utc).isoformat(),
                "end_utc": datetime.fromtimestamp(item["end_ts"], timezone.utc).isoformat(),
                "timezone": "Africa/Cairo", "all_day": False, "busy": True,
            })
        rows = sorted(rows, key=lambda r: (r["start_ts"], r["provider"], r["event_id"]))[:limit]
        with self.store.connect() as db:
            has_sync = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='calendar_google_sync'"
            ).fetchone()
            checkpoint = db.execute(
                "SELECT max(last_success) FROM calendar_google_sync"
            ).fetchone()[0] if has_sync else None
        return {
            "timezone": "Africa/Cairo", "date": today.isoformat(), "window_days": days,
            "items": rows, "count": len(rows),
            "connected_providers": ["google"] if checkpoint is not None else [],
            "provider_status": ("cached_google_synced" if checkpoint is not None
                                else "not_connected_in_foundation"),
            "cache_last_success": checkpoint,
            "source": "local_provider_projection",
            "external_reads": False, "external_writes": False,
        }

    def availability(self, days=14):
        agenda = self.agenda(days=days)
        busy = sorted((r["start_ts"], r["end_ts"]) for r in agenda["items"] if r["busy"])
        merged = []
        for start, end in busy:
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(end, merged[-1][1])
            else:
                merged.append([start, end])
        return {
            "timezone": agenda["timezone"], "date": agenda["date"],
            "window_days": days, "busy_intervals_utc": merged,
            "limited_to_loaded_projection": True,
            "source": agenda["source"], "external_reads": False, "external_writes": False,
        }


def assess_ai_action(action, *, scope="propose_only", owner_granted=False,
                     ai_created=False, recurring=False, has_attendees=False,
                     has_conflict=False):
    """Pure policy advice; never executes a write or infers an owner grant."""
    if action not in ACTIONS:
        raise ValueError("invalid_calendar_action")
    if scope not in {"propose_only", "scoped_auto"}:
        raise ValueError("invalid_calendar_scope")
    for flag in (owner_granted, ai_created, recurring, has_attendees, has_conflict):
        if type(flag) is not bool:
            raise ValueError("invalid_calendar_policy_flag")
    if action in {"read", "summarize", "propose"}:
        return {"eligible_for_auto": True, "requires_approval": False,
                "reason": "local_read_or_proposal_only", "executed": False}
    allowed = (
        scope == "scoped_auto" and owner_granted and
        not recurring and not has_attendees and not has_conflict and
        (action != "delete" or ai_created)
    )
    return {"eligible_for_auto": allowed, "requires_approval": not allowed,
            "reason": "scoped_owner_grant" if allowed else "owner_review_required",
            "executed": False}
