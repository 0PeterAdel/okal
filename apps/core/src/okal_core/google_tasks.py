"""Isolated Google Tasks read-only provider, cached as date-only tasks.

Never reads Calendar/Gmail refresh tokens. Does not create local tasks or call
a Google mutation method. The Google 'due' field has NO time-of-day semantics.
"""
from datetime import date
import json
import re

from .calendar_google import CalendarGoogleError, validate_account
from .mail.private import read_private, write_private
from .store import private_directory

TASKS_SCOPE = "https://www.googleapis.com/auth/tasks.readonly"
SCOPES = [TASKS_SCOPE]
MAX_LISTS = 20
MAX_LIST_PAGES = 4
MAX_TASK_PAGES = 6
TASK_PAGE_SIZE = 100
MAX_RESULTS = 100


class GoogleTasksError(ValueError):
    pass


def private_credentials(store, account="default"):
    return (private_directory(store.directory / "tasks" / "google") /
            (validate_account(account) + ".json"))


def _credentials(store, account):
    data = read_private(private_credentials(store, account))
    if set(data.get("scopes") or []) != set(SCOPES):
        raise GoogleTasksError("tasks_readonly_scope_required")
    from google.oauth2.credentials import Credentials
    creds = Credentials.from_authorized_user_info(data, SCOPES)
    if not creds.valid:
        if not creds.refresh_token:
            raise GoogleTasksError("google_tasks_reauthorization_required")
        from google.auth.transport.requests import Request
        import requests
        try:
            with requests.Session() as session:
                session.trust_env = False
                creds.refresh(Request(session=session))
        except Exception:
            raise GoogleTasksError("google_tasks_reauthorization_required") from None
        write_private(private_credentials(store, account),
                      json.loads(creds.to_json()))
    return creds


def _service(store, account):
    from googleapiclient.discovery import build
    return build("tasks", "v1", credentials=_credentials(store, account),
                 cache_discovery=False)


def _id(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 256 or
            any(ord(c) < 33 or ord(c) > 126 for c in value)):
        raise GoogleTasksError("invalid_google_tasks_identity")
    return value


def _title(value):
    if not isinstance(value, str) or len(value) > 250 or any(
        ord(c) < 32 and c not in "\t" for c in value
    ):
        raise GoogleTasksError("invalid_google_tasks_title")
    return value.strip() or "Untitled task"


def _scheduled_date(value):
    # Google's due field represents a date, not a deadline or exact hour.
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 48:
        raise GoogleTasksError("invalid_google_tasks_scheduled_date")
    try:
        result = date.fromisoformat(value[:10])
    except ValueError:
        raise GoogleTasksError("invalid_google_tasks_scheduled_date") from None
    if len(value) < 20 or value[10] != "T":
        raise GoogleTasksError("invalid_google_tasks_scheduled_date")
    return result.isoformat()


def _pages(resource, base, limit, per_page):
    visited, token = set(), None
    for _ in range(limit):
        args = {**base, "maxResults": per_page}
        if token:
            args["pageToken"] = token
        try:
            response = resource.list(**args).execute(num_retries=0)
        except Exception as exc:
            # Only inspect the HTTP status integer; never persist/echo Google
            # error bodies, account identifiers, query URLs or OAuth tokens.
            http_status = getattr(getattr(exc, "resp", None), "status", None)
            code = {
                401: "google_tasks_reauthorization_required",
                403: "google_tasks_access_denied_or_api_disabled",
                429: "google_tasks_rate_limited",
            }.get(http_status, "google_tasks_read_failed")
            raise GoogleTasksError(code) from None
        if not isinstance(response, dict) or not isinstance(response.get("items", []), list):
            raise GoogleTasksError("invalid_google_tasks_response")
        yield response.get("items", [])
        token = response.get("nextPageToken")
        if not token:
            return
        if not isinstance(token, str) or token in visited:
            raise GoogleTasksError("invalid_google_tasks_pagination")
        visited.add(token)
    raise GoogleTasksError("google_tasks_page_budget_exceeded")


def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS google_tasks_cache (
        account_id TEXT NOT NULL, list_id TEXT NOT NULL,
        task_id TEXT NOT NULL, title TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('needsAction','completed')),
        scheduled_day TEXT, parent_id TEXT, updated TEXT,
        PRIMARY KEY(account_id,list_id,task_id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS google_tasks_sync (
        account_id TEXT PRIMARY KEY, last_success INTEGER NOT NULL,
        list_count INTEGER NOT NULL, task_count INTEGER NOT NULL
    )""")


def sync(store, account="default", service=None):
    """Atomic bounded full snapshot; fetch/validate all before mutating cache."""
    validate_account(account)
    if service is None:
        service = _service(store, account)
    lists = []
    for page in _pages(service.tasklists(), {}, MAX_LIST_PAGES, 100):
        for entry in page:
            if not isinstance(entry, dict):
                raise GoogleTasksError("invalid_google_tasks_list")
            lists.append(_id(entry.get("id")))
            if len(lists) > MAX_LISTS:
                raise GoogleTasksError("google_tasks_list_budget_exceeded")
    if len(set(lists)) != len(lists):
        raise GoogleTasksError("duplicate_google_tasks_list")

    snapshot, seen = [], set()
    for list_id in lists:
        for page in _pages(service.tasks(), {
            "tasklist": list_id, "showCompleted": True, "showHidden": True,
            "showDeleted": False,
        }, MAX_TASK_PAGES, TASK_PAGE_SIZE):
            for entry in page:
                if not isinstance(entry, dict):
                    raise GoogleTasksError("invalid_google_tasks_entry")
                if entry.get("deleted") is True:
                    continue
                task_id = _id(entry.get("id"))
                key = (list_id, task_id)
                if key in seen:
                    raise GoogleTasksError("duplicate_google_tasks_identity")
                seen.add(key)
                status = entry.get("status", "needsAction")
                if status not in {"needsAction", "completed"}:
                    raise GoogleTasksError("invalid_google_tasks_status")
                parent = entry.get("parent")
                snapshot.append((
                    account, list_id, task_id, _title(entry.get("title", "")),
                    status, _scheduled_date(entry.get("due")),
                    _id(parent) if parent is not None else None,
                    str(entry.get("updated", ""))[:48],
                ))
                if len(snapshot) > MAX_LISTS * MAX_TASK_PAGES * TASK_PAGE_SIZE:
                    raise GoogleTasksError("google_tasks_snapshot_budget_exceeded")
    with store.connect() as db, db:
        db.execute("BEGIN IMMEDIATE")
        _schema(db)
        db.execute("DELETE FROM google_tasks_cache WHERE account_id=?", (account,))
        db.executemany("INSERT INTO google_tasks_cache VALUES(?,?,?,?,?,?,?,?)",
                       snapshot)
        db.execute("""INSERT INTO google_tasks_sync VALUES(?,?,?,?)
            ON CONFLICT(account_id) DO UPDATE SET
                last_success=excluded.last_success,
                list_count=excluded.list_count, task_count=excluded.task_count""",
                (account, int(store.clock()), len(lists), len(snapshot)))
    return {"status":"complete", "list_count":len(lists),
            "task_count":len(snapshot), "provider_writes":False,
            "local_cache_updated":True, "date_only_semantics":True}



# Record only allowlisted error codes; never persist a provider response or token.
_TASKS_SAFE_ERRORS = frozenset({
    "google_tasks_read_failed",
    "google_tasks_access_denied_or_api_disabled",
    "google_tasks_rate_limited",
    "google_tasks_reauthorization_required",
    "tasks_readonly_scope_required",
    "invalid_google_tasks_response",
    "invalid_google_tasks_pagination",
    "google_tasks_page_budget_exceeded",
    "google_tasks_list_budget_exceeded",
    "google_tasks_snapshot_budget_exceeded",
    "invalid_google_tasks_list",
    "duplicate_google_tasks_list",
    "invalid_google_tasks_entry",
    "invalid_google_tasks_identity",
    "duplicate_google_tasks_identity",
    "invalid_google_tasks_status",
    "invalid_google_tasks_scheduled_date",
    "invalid_google_tasks_title",
})


def _record_sync_attempt(store, account, result, error=None):
    """Last attempt is independent of the last successful cached snapshot."""
    with store.connect() as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS google_tasks_attempts (
            account_id TEXT PRIMARY KEY, last_attempt INTEGER NOT NULL,
            last_result TEXT NOT NULL, last_error TEXT
        )""")
        db.execute("""INSERT INTO google_tasks_attempts VALUES(?,?,?,?)
            ON CONFLICT(account_id) DO UPDATE SET
                last_attempt=excluded.last_attempt,
                last_result=excluded.last_result,
                last_error=excluded.last_error""",
            (account, int(store.clock()), result, error))


def sync_recorded(store, account="default"):
    """Explicit owner sync: exclusive across CLI and HTTP background workers."""
    import fcntl
    import os

    account = validate_account(account)
    lock = private_directory(store.directory / "tasks" / "google") / (
        account + ".sync.lock")
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "rb") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise GoogleTasksError("google_tasks_sync_already_running") from None
            _record_sync_attempt(store, account, "running")
            try:
                result = sync(store, account)
            except Exception as exc:
                code = str(exc) if isinstance(exc, GoogleTasksError) else ""
                if code not in _TASKS_SAFE_ERRORS:
                    code = "google_tasks_read_failed"
                _record_sync_attempt(store, account, "failed", code)
                raise GoogleTasksError(code) from None
            _record_sync_attempt(store, account, "complete")
            return result
    except OSError:
        raise GoogleTasksError("google_tasks_sync_lock_failed") from None


def sync_in_background(store):
    """OAuth callback / button: never leak provider exceptions to HTTP logs."""
    try:
        sync_recorded(store)
    except (GoogleTasksError, OSError):
        # Failure is persisted as a safe code in status for owner inspection.
        pass


def status(store, account="default"):
    validate_account(account)
    with store.connect() as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                            "AND name='google_tasks_sync'").fetchone()
        row = db.execute(
            "SELECT last_success,list_count,task_count FROM google_tasks_sync "
            "WHERE account_id=?", (account,)
        ).fetchone() if exists else None
    path = private_credentials(store, account)
    with store.connect() as db:
        attempt_exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='google_tasks_attempts'").fetchone()
        attempt = db.execute(
            "SELECT last_attempt,last_result,last_error FROM google_tasks_attempts "
            "WHERE account_id=?", (account,)
        ).fetchone() if attempt_exists else None
    return {"last_attempt": attempt["last_attempt"] if attempt else None,
            "last_result": attempt["last_result"] if attempt else None,
            "last_error": attempt["last_error"] if attempt else None,
            "credentials_present": path.is_file(),
            "authorization": "configured_not_verified"
            if path.is_file() and row is None else "cached"
            if row is not None else "not_connected",
            "last_success": row["last_success"] if row else None,
            "list_count": row["list_count"] if row else 0,
            "task_count": row["task_count"] if row else 0,
            "read_only_scope": True, "external_reads": False,
            "external_writes": False}


def cached(store, account="default", limit=MAX_RESULTS):
    validate_account(account)
    if type(limit) is not int or not 1 <= limit <= MAX_RESULTS:
        raise GoogleTasksError("invalid_google_tasks_limit")
    with store.connect() as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                            "AND name='google_tasks_cache'").fetchone()
        if not exists:
            return {"items":[], "connected":False, "date_only":True,
                    "external_reads":False, "external_writes":False}
        rows = db.execute(
            "SELECT list_id,task_id,title,status,scheduled_day,parent_id "
            "FROM google_tasks_cache WHERE account_id=? "
            "AND status='needsAction' "
            "ORDER BY CASE WHEN scheduled_day IS NULL THEN 1 ELSE 0 END, "
            "scheduled_day,list_id,task_id LIMIT ?",
            (account, limit),
        ).fetchall()
    return {
        "items":[{"source":"google_tasks_cache","list_id":row["list_id"],
                  "task_id":row["task_id"],"title":row["title"],
                  "status":row["status"], "scheduled_day":row["scheduled_day"],
                  "parent_id":row["parent_id"],
                  "has_exact_due_time":False,"is_deadline":False}
                 for row in rows],
        "connected": True, "date_only":True,
        "external_reads":False,"external_writes":False,
    }
