"""Explicit bounded Google Calendar recovery for missing *current* events.

Read-only provider calls; writes valid events to existing private SQLite cache.
Deliberately does not create a provider sync checkpoint or delete older rows.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .calendar_core import CalendarCore, _clean_event
from .calendar_google import (
    CalendarGoogleError, MAX_EVENTS, MAX_PAGES, PAGE_SIZE, _event_identity,
    _service, list_calendars, normalize, sync_lock, validate_account,
    validate_calendar_id,
)

CAIRO = ZoneInfo("Africa/Cairo")


def recover_window(store, account="default", calendar="primary", days=7,
                   service=None):
    """Restore bounded next-week events despite unrelated historical invalidity.

    Resolve calendar from Google's list, fetch every requested page, validate
    *all* events before the first local write, then upsert idempotently.
    Never advance a Calendar syncToken or claim full-source synchronization.
    """
    validate_account(account)
    if type(days) is not int or not 1 <= days <= 14:
        raise CalendarGoogleError("invalid_calendar_recovery_window")
    if calendar != "primary":
        validate_calendar_id(calendar)
    if service is None:
        service = _service(store, account)
    calendars = list_calendars(service)
    matches = [item for item in calendars if (
        item["primary"] if calendar == "primary" else item["id"] == calendar
    )]
    if len(matches) != 1 or matches[0]["access"] not in {
        "reader", "writer", "owner"
    }:
        raise CalendarGoogleError("calendar_not_accessible_select_id_from_calendars")

    target = matches[0]
    today = datetime.fromtimestamp(store.clock(), CAIRO).date()
    first = datetime.combine(today, time.min, CAIRO)
    last = datetime.combine(today + timedelta(days=days), time.min, CAIRO)
    all_events, seen = [], set()
    page_token = None
    visited_pages = set()

    with sync_lock(store, account):
        for _ in range(MAX_PAGES):
            args = {
                "calendarId": target["id"],
                "timeMin": first.isoformat(),
                "timeMax": last.isoformat(),
                "singleEvents": True,
                "showDeleted": False,
                "maxResults": PAGE_SIZE,
            }
            if page_token:
                args["pageToken"] = page_token
            try:
                page = service.events().list(**args).execute(num_retries=0)
            except Exception:
                raise CalendarGoogleError(
                    "google_calendar_provider_request_failed"
                ) from None
            if not isinstance(page, dict) or not isinstance(page.get("items", []), list):
                raise CalendarGoogleError("google_calendar_invalid_response")
            for event in page.get("items", []):
                # Skip provider cancellation records from a non-deletion
                # projection. Never prune or overwrite old data here.
                if not isinstance(event, dict):
                    raise CalendarGoogleError("invalid_google_calendar_event")
                if event.get("status") == "cancelled":
                    continue
                identity = _event_identity(event)
                if identity in seen:
                    raise CalendarGoogleError(
                        "duplicate_google_calendar_event_in_snapshot"
                    )
                seen.add(identity)
                normalized = normalize(event, target["timezone"])
                if normalized is None:
                    continue
                # Clean with precisely the same validation as durable ingest.
                # No partial inserts if a later page contains an invalid event.
                _clean_event(normalized)
                all_events.append(normalized)
                if len(all_events) > MAX_EVENTS:
                    raise CalendarGoogleError("google_calendar_event_budget_exceeded")

            page_token = page.get("nextPageToken")
            if not page_token:
                break
            if not isinstance(page_token, str) or page_token in visited_pages:
                raise CalendarGoogleError("google_calendar_pagination_invalid")
            visited_pages.add(page_token)
        else:
            raise CalendarGoogleError("google_calendar_event_page_budget_exceeded")

        core = CalendarCore(store)
        written = 0
        for offset in range(0, len(all_events), 200):
            outcome = core.ingest(
                "google", account, target["id"], all_events[offset:offset + 200]
            )
            written += outcome["written"]

        # Google date-window query is authoritative *only* for this bounded
        # interval. Reconcile locally deleted/cancelled instances here so
        # polling reflects removals, without changing any historical rows
        # outside this window or advancing the full-sync cursor.
        with store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            core._init(db)
            current = list(db.execute(
                """SELECT event_id,instance_id FROM calendar_source_events
                   WHERE provider='google' AND account_id=? AND calendar_id=?
                   AND ((start_ts<? AND end_ts>?) OR
                        (start_ts=end_ts AND start_ts>=? AND start_ts<?))""",
                (account, target["id"], int(last.timestamp()),
                 int(first.timestamp()), int(first.timestamp()),
                 int(last.timestamp())),
            ))
            current_ids = {
                (event["id"], event.get("instance_id") or "")
                for event in all_events
            }
            deleted = 0
            for row in current:
                if (row["event_id"], row["instance_id"]) not in current_ids:
                    db.execute(
                        "DELETE FROM calendar_source_events WHERE provider='google' "
                        "AND account_id=? AND calendar_id=? AND event_id=? "
                        "AND instance_id=?",
                        (account, target["id"], row["event_id"], row["instance_id"]),
                    )
                    deleted += 1
            db.execute("""CREATE TABLE IF NOT EXISTS calendar_google_window_recovery (
                account_id TEXT NOT NULL, calendar_id TEXT NOT NULL,
                last_success INTEGER NOT NULL, window_start INTEGER NOT NULL,
                window_end INTEGER NOT NULL, event_count INTEGER NOT NULL,
                PRIMARY KEY (account_id,calendar_id)
            )""")
            db.execute("""INSERT INTO calendar_google_window_recovery
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(account_id,calendar_id) DO UPDATE SET
                last_success=excluded.last_success,
                window_start=excluded.window_start,window_end=excluded.window_end,
                event_count=excluded.event_count""", (
                account, target["id"], int(store.clock()),
                int(first.timestamp()), int(last.timestamp()), len(all_events)
            ))

    return {
        "mode": "bounded_window_recovery",
        "account_alias": account,
        "calendar_role": "primary" if target["primary"] else "selected",
        "date": today.isoformat(),
        "window_days": days,
        "received": len(all_events),
        "written": written,
        "removed_from_window": deleted,
        "source_coverage": "selected_calendar_window_only",
        "full_sync_complete": False,
        "sync_cursor_advanced": False,
        "external_writes": False,
        "note": "Valid current events restored locally; historical sync remains unresolved.",
    }
