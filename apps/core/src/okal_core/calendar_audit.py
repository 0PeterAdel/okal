"""Owner-invoked, read-only Google Calendar coverage audit.

Never prints account/calendar/event identities, titles, descriptions, credentials
or OAuth values. Does not modify event cache, sync cursors, or checkpoints.
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .calendar_google import _event_time, _service, list_calendars, validate_account

ZONE = ZoneInfo("Africa/Cairo")
MAX_PAGES = 8
PAGE_SIZE = 250
MAX_CALENDARS = 20


def _event_shape(item, fallback_timezone):
    if not isinstance(item, dict):
        return "invalid_time"
    try:
        start, _, start_day = _event_time(item.get("start"), fallback_timezone)
        end, _, end_day = _event_time(item.get("end"), fallback_timezone)
        if start_day != end_day:
            return "invalid_time"
        begin = datetime.fromisoformat(start).astimezone(timezone.utc)
        finish = datetime.fromisoformat(end).astimezone(timezone.utc)
        delta = finish - begin
        if delta < timedelta():
            return "reversed_interval"
        if delta == timedelta():
            return "nonpositive_all_day" if start_day else "zero_duration_timed"
        if delta > timedelta(days=366):
            return "overlong_interval"
        return "valid"
    except (ValueError, TypeError, KeyError):
        return "invalid_time"


def audit_google_calendar(store, account="default", days=7, service=None):
    """Live bounded date-window probe; reports only aggregates and ordinals.

    Intended for an explicit operator command, not the HTTP dashboard. Uses
    read-only Events.list without syncToken; never advances an existing cursor.
    """
    validate_account(account)
    if type(days) is not int or not 1 <= days <= 14:
        raise ValueError("invalid_calendar_audit_window")
    if service is None:
        service = _service(store, account)
    calendars = list_calendars(service)
    if len(calendars) > MAX_CALENDARS:
        raise ValueError("too_many_calendars_select_individually")
    date = datetime.fromtimestamp(store.clock(), ZONE).date()
    start = datetime.combine(date, time.min, ZONE)
    end = datetime.combine(date + timedelta(days=days), time.min, ZONE)
    first, last = start.isoformat(), end.isoformat()
    begin_ts, end_ts = int(start.timestamp()), int(end.timestamp())

    with store.connect() as db:
        cache_exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='calendar_source_events'"
        ).fetchone()
        checkpoints_exist = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='calendar_google_sync'"
        ).fetchone()
        out = []
        for number, cal in enumerate(calendars, start=1):
            result = {
                "calendar_number": number, "primary": bool(cal["primary"]),
                "readable": cal["access"] in {
                    "owner", "writer", "reader", "freeBusyReader"
                },
                "live_events_in_window": None,
                "cached_events_in_window": 0,
                "has_sync_checkpoint": False,
                "interval_shapes": None,
                "audit_status": "not_readable",
            }
            if cache_exists:
                result["cached_events_in_window"] = db.execute(
                    "SELECT count(*) FROM calendar_source_events "
                    "WHERE provider='google' AND account_id=? AND calendar_id=? "
                    "AND cancelled=0 AND start_ts<? AND end_ts>?",
                    (account, cal["id"], end_ts, begin_ts),
                ).fetchone()[0]
            if checkpoints_exist:
                result["has_sync_checkpoint"] = db.execute(
                    "SELECT 1 FROM calendar_google_sync "
                    "WHERE account_id=? AND calendar_id=?",
                    (account, cal["id"]),
                ).fetchone() is not None
            out.append(result)

    for number, (cal, result) in enumerate(zip(calendars, out), start=1):
        if not result["readable"]:
            continue
        page_token, pages = None, 0
        seen_page_tokens = set()
        counts = {key: 0 for key in (
            "valid", "zero_duration_timed", "reversed_interval",
            "nonpositive_all_day", "overlong_interval", "invalid_time"
        )}
        count = 0
        try:
            while pages < MAX_PAGES:
                args = {
                    "calendarId": cal["id"],
                    "timeMin": first, "timeMax": last,
                    "singleEvents": True, "showDeleted": False,
                    "maxResults": PAGE_SIZE,
                }
                if page_token:
                    args["pageToken"] = page_token
                page = service.events().list(**args).execute(num_retries=0)
                if not isinstance(page, dict) or not isinstance(page.get("items"), list):
                    raise ValueError("invalid_audit_page")
                for event in page["items"]:
                    counts[_event_shape(event, cal["timezone"])] += 1
                    count += 1
                pages += 1
                token = page.get("nextPageToken")
                if not token:
                    result["live_events_in_window"] = count
                    result["interval_shapes"] = counts
                    result["audit_status"] = "complete"
                    break
                if not isinstance(token, str) or token in seen_page_tokens:
                    raise ValueError("invalid_audit_pagination")
                seen_page_tokens.add(token)
                page_token = token
            else:
                result["audit_status"] = "page_limit"
        except Exception:
            # Do not serialize the provider's error or exception body.
            result["audit_status"] = "provider_read_failed"
    return {
        "date": date.isoformat(),
        "days": days,
        "calendars_listed": len(calendars),
        "calendars": out,
        "complete": all(item["audit_status"] == "complete" for item in out),
        "cache_mutated": False,
        "sync_cursor_mutated": False,
        "external_writes": False,
    }
