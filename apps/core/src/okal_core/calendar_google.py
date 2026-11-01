"""Read-only Google Calendar integration for OKAL's local event projection.

OAuth is an operator-only CLI flow. HTTP GETs never call Google.
Provider credentials and cursors must never appear in HTTP/LLM responses.
"""
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import threading
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .calendar_core import CalendarCore
from .mail.private import read_private, write_private
from .store import private_directory

EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"
LIST_SCOPE = "https://www.googleapis.com/auth/calendar.calendarlist.readonly"
SCOPES = [EVENTS_SCOPE, LIST_SCOPE]
ACCOUNT_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
MAX_PAGES = 32
MAX_EVENTS = 8000
PAGE_SIZE = 250


class CalendarGoogleError(ValueError):
    pass


def validate_account(account):
    if not isinstance(account, str) or not ACCOUNT_RE.fullmatch(account):
        raise CalendarGoogleError("invalid_google_calendar_account_alias")
    return account


def validate_calendar_id(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 250
            or any(ord(x) < 33 or ord(x) > 126 for x in value)):
        raise CalendarGoogleError("invalid_google_calendar_id")
    return value


def private_root(store):
    return private_directory(store.directory / "calendar" / "google")


def credential_file(store, account):
    return private_root(store) / (validate_account(account) + ".json")


def has_credentials(store, account):
    path = credential_file(store, account)
    return path.is_file() and not path.is_symlink()


def configured_accounts(store):
    base = private_root(store)
    return sorted(p.stem for p in base.glob("*.json")
                  if ACCOUNT_RE.fullmatch(p.stem) and not p.is_symlink())


@contextmanager
def sync_lock(store, account):
    path = private_root(store) / (validate_account(account) + ".lock")
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as f:
        metadata = os.fstat(f.fileno())
        if (not stat.S_ISREG(metadata.st_mode) or
                metadata.st_uid != os.getuid() or metadata.st_mode & 0o077):
            raise CalendarGoogleError("unsafe_calendar_sync_lock")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CalendarGoogleError("calendar_sync_already_running") from None
        yield


def _init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS calendar_google_sync (
        account_id TEXT NOT NULL, calendar_id TEXT NOT NULL,
        sync_token TEXT NOT NULL, last_success INTEGER NOT NULL,
        event_count INTEGER NOT NULL, PRIMARY KEY(account_id,calendar_id)
    )""")


def status(store, account="default"):
    """No credentials, refresh tokens, user profile or cursors in returned data."""
    validate_account(account)
    found = has_credentials(store, account)
    with store.connect() as db:
        _init(db)
        rows = list(db.execute(
            """SELECT calendar_id,last_success,event_count
               FROM calendar_google_sync WHERE account_id=? ORDER BY calendar_id""",
            (account,),
        ))
    return {
        "account_alias": account,
        "authorization": "configured_not_verified" if found else "not_configured",
        "last_sync": [
            {"calendar_id": x["calendar_id"], "last_success": x["last_success"],
             "event_count": x["event_count"]} for x in rows
        ] if found else [],
        "read_only_scopes": True,
        "connected": bool(found and rows),
        "external_writes": False,
    }


def authorize(store, client_secrets, account="default"):
    """User-interactive consent in a local browser; never remotely invokable."""
    validate_account(account)
    secret_path = Path(client_secrets).expanduser().resolve(strict=True)
    # Verify the user-supplied desktop client file, not a project credential.
    read_private(secret_path)
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
    credentials = flow.run_local_server(
        host="127.0.0.1", port=0, open_browser=True, access_type="offline",
        prompt="consent",
    )
    if not credentials.refresh_token:
        raise CalendarGoogleError("google_calendar_offline_consent_missing")
    if not set(SCOPES).issubset(set(credentials.scopes or [])):
        raise CalendarGoogleError("google_calendar_scopes_missing")
    write_private(credential_file(store, account), json.loads(credentials.to_json()))
    return {"account_alias": account, "authorization": "configured_not_verified",
            "scopes": "read_only", "browser_consent_completed": True,
            "external_writes": False}


def _credentials(store, account):
    data = read_private(credential_file(store, account))
    if not set(SCOPES).issubset(set(data.get("scopes") or [])):
        raise CalendarGoogleError("google_calendar_scopes_missing")
    from google.oauth2.credentials import Credentials
    credentials = Credentials.from_authorized_user_info(data, SCOPES)
    if not credentials.valid:
        if not credentials.refresh_token:
            raise CalendarGoogleError("google_calendar_reauthorization_required")
        from google.auth.transport.requests import Request
        import requests
        from google.auth.exceptions import RefreshError
        try:
            with requests.Session() as session:
                session.trust_env = False
                credentials.refresh(Request(session=session))
        except RefreshError:
            raise CalendarGoogleError("google_calendar_reauthorization_required") from None
        write_private(credential_file(store, account),
                      json.loads(credentials.to_json()))
    return credentials


def _service(store, account):
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=_credentials(store, account),
                 cache_discovery=False)


def list_calendars(service):
    calendars, page_token = [], None
    visited = set()
    for _ in range(10):
        args = {"maxResults": 100}
        if page_token:
            args["pageToken"] = page_token
        page = service.calendarList().list(**args).execute(num_retries=0)
        if not isinstance(page, dict) or not isinstance(page.get("items", []), list):
            raise CalendarGoogleError("google_calendar_list_invalid")
        for item in page.get("items", []):
            if not isinstance(item, dict):
                raise CalendarGoogleError("google_calendar_list_invalid")
            calendar_id = validate_calendar_id(item.get("id"))
            calendars.append({
                "id": calendar_id,
                "name": str(item.get("summary") or calendar_id)[:150],
                "primary": item.get("primary") is True,
                "access": str(item.get("accessRole") or "")[:30],
            })
        page_token = page.get("nextPageToken")
        if not page_token:
            return calendars
        if not isinstance(page_token, str) or page_token in visited:
            raise CalendarGoogleError("google_calendar_pagination_invalid")
        visited.add(page_token)
    raise CalendarGoogleError("google_calendar_list_page_budget_exceeded")


def _event_identity(item):
    if not isinstance(item, dict):
        raise CalendarGoogleError("invalid_google_calendar_event")
    event_id = item.get("id")
    if not isinstance(event_id, str) or not 1 <= len(event_id) <= 200:
        raise CalendarGoogleError("invalid_google_calendar_event_id")
    original = item.get("originalStartTime") or {}
    if not isinstance(original, dict):
        raise CalendarGoogleError("invalid_google_recurring_instance")
    instance = original.get("dateTime") or original.get("date") or ""
    if not isinstance(instance, str) or len(instance) > 200:
        raise CalendarGoogleError("invalid_google_recurring_instance")
    return event_id, instance


def _event_time(value, fallback_timezone):
    if not isinstance(value, dict):
        raise CalendarGoogleError("invalid_google_calendar_time")
    tz = value.get("timeZone") or fallback_timezone
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        raise CalendarGoogleError("invalid_google_calendar_timezone") from None
    if "dateTime" in value:
        raw = value["dateTime"]
        if not isinstance(raw, str):
            raise CalendarGoogleError("invalid_google_calendar_time")
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            raise CalendarGoogleError("invalid_google_calendar_time") from None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise CalendarGoogleError("google_calendar_time_missing_offset")
        return parsed.isoformat(), tz, False
    if "date" in value:
        try:
            parsed_date = date.fromisoformat(value["date"])
        except (ValueError, TypeError):
            raise CalendarGoogleError("invalid_google_calendar_date") from None
        return datetime.combine(parsed_date, time.min, zone).isoformat(), tz, True
    raise CalendarGoogleError("invalid_google_calendar_time")


def normalize(item, default_timezone, prior=None):
    """Expand Google list events to CalendarCore's strict format.

    Cancelled recurrence exceptions often include ONLY id/recurringEventId;
    preserve previously known fields for a tombstone, never invent a time.
    Unknown cancelled events need no row in a fresh projection.
    """
    event_id, instance_id = _event_identity(item)
    cancelled = item.get("status") == "cancelled"
    if cancelled and (not item.get("start") or not item.get("end")):
        if prior is None:
            return None
        return {
            "id": event_id, "instance_id": instance_id, "title": prior["title"],
            "start": prior["start_utc"], "end": prior["end_utc"],
            "timezone": prior["timezone"], "all_day": bool(prior["all_day"]),
            "busy": bool(prior["busy"]), "cancelled": True,
            "updated": item.get("updated"),
        }
    start, tz, all_day = _event_time(item.get("start"), default_timezone)
    end, _, end_all_day = _event_time(item.get("end"), default_timezone)
    if all_day != end_all_day:
        raise CalendarGoogleError("invalid_google_calendar_all_day_interval")
    updated = item.get("updated")
    if not isinstance(updated, str):
        raise CalendarGoogleError("missing_google_calendar_updated_timestamp")
    return {
        "id": event_id, "instance_id": instance_id,
        "title": str(item.get("summary") or "(بدون عنوان)")[:250],
        "start": start, "end": end, "timezone": tz, "all_day": all_day,
        "busy": item.get("transparency") != "transparent",
        "cancelled": cancelled, "updated": updated,
    }


def _pages(service, calendar_id, sync_token):
    """Fetch complete bounded result before touching the stored sync token."""
    events, page_token, visited = [], None, set()
    for _ in range(MAX_PAGES):
        args = {
            "calendarId": calendar_id, "maxResults": PAGE_SIZE,
            "singleEvents": True, "showDeleted": True,
        }
        if sync_token:
            args["syncToken"] = sync_token
        if page_token:
            args["pageToken"] = page_token
        try:
            page = service.events().list(**args).execute(num_retries=0)
        except Exception as exc:
            if getattr(getattr(exc, "resp", None), "status", None) == 410 and sync_token:
                raise CalendarGoogleError("google_calendar_sync_token_expired") from None
            raise CalendarGoogleError("google_calendar_provider_request_failed") from None
        if not isinstance(page, dict) or not isinstance(page.get("items", []), list):
            raise CalendarGoogleError("google_calendar_invalid_response")
        events.extend(page.get("items", []))
        if len(events) > MAX_EVENTS:
            raise CalendarGoogleError("google_calendar_event_budget_exceeded")
        page_token = page.get("nextPageToken")
        if not page_token:
            token = page.get("nextSyncToken")
            if not isinstance(token, str) or not token:
                raise CalendarGoogleError("google_calendar_missing_sync_token")
            return events, token
        if not isinstance(page_token, str) or page_token in visited:
            raise CalendarGoogleError("google_calendar_pagination_invalid")
        visited.add(page_token)
    raise CalendarGoogleError("google_calendar_event_page_budget_exceeded")


def sync_calendar(store, account="default", calendar_id="primary", service=None,
                  calendar_timezone="Africa/Cairo"):
    """Replay-safe sync. Cursor changes only after all pages and inserts succeed."""
    validate_account(account)
    validate_calendar_id(calendar_id)
    with sync_lock(store, account):
        if service is None:
            service = _service(store, account)
        core = CalendarCore(store)
        with store.connect() as db:
            _init(db)
            core._init(db)
            current = db.execute(
                "SELECT sync_token FROM calendar_google_sync "
                "WHERE account_id=? AND calendar_id=?", (account, calendar_id)
            ).fetchone()
            cursor = current["sync_token"] if current else None
        try:
            events, new_cursor = _pages(service, calendar_id, cursor)
            full = cursor is None
        except CalendarGoogleError as exc:
            if str(exc) != "google_calendar_sync_token_expired":
                raise
            events, new_cursor = _pages(service, calendar_id, None)
            full = True
        # Read existing cache only after successful page fetch. This handles
        # provider cancellation records lacking start/end without guessing.
        with store.connect() as db:
            prior = {
                (row["event_id"], row["instance_id"]): dict(row)
                for row in db.execute(
                    "SELECT * FROM calendar_source_events WHERE provider='google' "
                    "AND account_id=? AND calendar_id=?", (account, calendar_id)
                )
            }
        normalized, seen = [], set()
        for event in events:
            identity = _event_identity(event)
            if identity in seen:
                raise CalendarGoogleError("duplicate_google_calendar_event_in_snapshot")
            seen.add(identity)
            item = normalize(event, calendar_timezone, prior.get(identity))
            if item is not None:
                normalized.append(item)
        # Individual idempotent chunks. If any chunk fails, cursor never moves
        # and a subsequent run replays the entire delta safely.
        written = 0
        for index in range(0, len(normalized), 200):
            outcome = core.ingest(
                "google", account, calendar_id, normalized[index:index + 200]
            )
            written += outcome["written"]
        with store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            _init(db)
            if full:
                # A complete new full snapshot supersedes old deleted entries,
                # including when Google reports 410 Gone.
                for identity in set(prior) - seen:
                    db.execute(
                        "DELETE FROM calendar_source_events "
                        "WHERE provider='google' AND account_id=? AND calendar_id=? "
                        "AND event_id=? AND instance_id=?",
                        (account, calendar_id, *identity),
                    )
            db.execute(
                """INSERT INTO calendar_google_sync
                (account_id,calendar_id,sync_token,last_success,event_count)
                VALUES(?,?,?,?,?)
                ON CONFLICT(account_id,calendar_id) DO UPDATE SET
                sync_token=excluded.sync_token,
                last_success=excluded.last_success,event_count=excluded.event_count""",
                (account, calendar_id, new_cursor, int(store.clock()), len(events)),
            )
        return {
            "account_alias": account, "calendar_id": calendar_id,
            "result": "full_sync" if full else "history_delta",
            "received": len(events), "written": written,
            "last_success": int(store.clock()), "external_writes": False,
        }


class CalendarWorker:
    """Best-effort read-only polling; worker failure never breaks local Core."""
    def __init__(self, store, period_seconds=1800):
        self.store, self.period = store, period_seconds
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        if self.thread:
            return
        self.thread = threading.Thread(
            target=self._loop, name="okal-google-calendar-read-sync", daemon=True
        )
        self.thread.start()

    def _loop(self):
        # Initial small delay keeps desktop service bootstrap fast.
        if self.stop_event.wait(20):
            return
        while not self.stop_event.is_set():
            for account in configured_accounts(self.store):
                if self.stop_event.is_set():
                    break
                try:
                    sync_calendar(self.store, account=account)
                except (CalendarGoogleError, OSError, ValueError):
                    # Operator can inspect 'calendar status' / manual sync.
                    continue
            if self.stop_event.wait(self.period):
                return

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)
