"""Restart-safe Gmail history ingestion. No provider writes, no external model calls.

OAuth/Gmail calls and Ollama generation run outside SQLite transactions.
One atomic commit persists the digest, per-message provenance, deduplication and
history checkpoint; a crash before commit replays safely on restart.
"""
from datetime import datetime, timezone
import hashlib
import json
import re
import uuid

from ..models import SummaryInput
from .contracts import MailError, UNREADABLE_CODES
from .state import MailState, fingerprint
from .workflows import source_link

MAX_WINDOW = 31 * 86400
SKIPPED_LABELS = {"SENT", "DRAFT", "SPAM", "TRASH"}
POLL_SECONDS = 300


def safe_cursor(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,32}", value):
        raise MailError("invalid_gmail_history_id")
    return value


class HistoryState:
    def __init__(self, store):
        self.store = store
        with store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS mail_sync_state (
                account TEXT PRIMARY KEY, cursor TEXT NOT NULL,
                checked_at INTEGER NOT NULL, attempted_at INTEGER NOT NULL,
                last_result TEXT NOT NULL, last_error TEXT,
                last_count INTEGER NOT NULL DEFAULT 0
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS mail_sync_seen (
                account TEXT NOT NULL, message_id TEXT NOT NULL,
                PRIMARY KEY(account, message_id)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS mail_sync_insights (
                run_id TEXT NOT NULL REFERENCES runs(id),
                account TEXT NOT NULL, message_id TEXT NOT NULL,
                metadata TEXT NOT NULL, insight TEXT NOT NULL,
                PRIMARY KEY(run_id,message_id)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS mail_sync_quarantine (
                account TEXT NOT NULL, message_id TEXT NOT NULL,
                code TEXT NOT NULL, detected_at INTEGER NOT NULL,
                PRIMARY KEY(account,message_id)
            )""")
            db.execute("""CREATE INDEX IF NOT EXISTS mail_sync_recent
                ON mail_sync_insights(account,run_id)""")
            db.execute("""CREATE TABLE IF NOT EXISTS mail_sync_failures (
                account TEXT PRIMARY KEY, attempted_at INTEGER NOT NULL,
                code TEXT NOT NULL
            )""")

    def current(self, account):
        with self.store.connect() as db:
            r = db.execute(
                "SELECT cursor,checked_at,attempted_at,last_result,last_count "
                "FROM mail_sync_state WHERE account=?", (account.casefold(),)
            ).fetchone()
            return dict(r) if r else None

    def due(self, account, now):
        with self.store.connect() as db:
            attempted = db.execute(
                "SELECT attempted_at FROM mail_sync_failures WHERE account=?",
                (account.casefold(),)
            ).fetchone()
        current = self.current(account)
        last = max(attempted[0] if attempted else 0,
                   current["attempted_at"] if current else 0)
        return now >= last + POLL_SECONDS

    def seen(self, account, ids):
        if not ids:
            return set()
        found = set()
        with self.store.connect() as db:
            for index in range(0, len(ids), 200):
                batch = ids[index:index + 200]
                found.update(r[0] for r in db.execute(
                    "SELECT message_id FROM mail_sync_seen WHERE account=? AND message_id IN ("
                    + ",".join("?" for _ in batch) + ")",
                    [account.casefold(), *batch],
                ))
        return found

    def failure(self, account, code):
        # Error codes are allowlisted; never persist provider error bodies/credentials.
        allowed = {
            "authorization_required", "provider_read_failed", "history_cursor_expired",
            "history_backfill_window_exceeded_manual_review_required",
            "message_budget_exceeded_narrow_interval", "page_budget_exceeded",
            "repeated_page_token", "local_model_unavailable_or_invalid",
            "invalid_model_output", "mail_operation_already_running",
            "digest_output_budget_exceeded_narrow_interval",
        }
        clean = code if code in allowed else "sync_failed_check_local_doctor"
        with self.store.connect() as db, db:
            db.execute("""INSERT INTO mail_sync_failures VALUES(?,?,?)
                ON CONFLICT(account) DO UPDATE SET
                attempted_at=excluded.attempted_at,code=excluded.code""",
                (account.casefold(), int(self.store.clock()), clean))

    def commit(self, account, previous, new_cursor, result, observations, body,
               ignored_ids=(), advance=True, alert=False, quarantines=()):
        """CAS prevents lost updates; both checkpoint and all visible data commit together."""
        account = account.casefold()
        safe_cursor(new_cursor)
        if previous is not None:
            safe_cursor(previous)
            if int(new_cursor) < int(previous):
                raise MailError("history_cursor_regressed")
        if not advance and previous is None:
            raise MailError("initial_sync_cannot_be_partial")
        if not advance:
            new_cursor = previous
        now = int(self.store.clock())
        with self.store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT cursor,checked_at FROM mail_sync_state WHERE account=?", (account,)
            ).fetchone()
            if (row[0] if row else None) != previous:
                raise MailError("history_checkpoint_changed_retry")
            row_checked_at = row[1] if row else now
            run_id = None
            if observations or alert:
                item = SummaryInput(
                    workflow="mail", account_ref=fingerprint(account),
                    occurrence="gmail-history:" + fingerprint(
                        [previous, new_cursor, [m.id for m, _ in observations]]
                    ),
                    title="Gmail Briefing | موجز البريد الذكي",
                    body=body, data_kind="live",
                )
                run_id = uuid.uuid4().hex
                db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)", (
                    run_id, item.workflow, item.account_ref, item.occurrence,
                    fingerprint(item.model_dump()), now, "succeeded",
                ))
                db.execute(
                    "INSERT INTO summaries(run_id,title,body,data_kind) VALUES(?,?,?,?)",
                    (run_id, item.title, item.body, item.data_kind),
                )
            for message, insight in observations:
                db.execute(
                    "INSERT INTO mail_sync_seen(account,message_id) VALUES(?,?)",
                    (account, message.id),
                )
                metadata = message.model_dump(exclude={"body"})
                metadata["body_sha256"] = hashlib.sha256(message.body.encode()).hexdigest()
                db.execute(
                    "INSERT INTO mail_sync_insights VALUES(?,?,?,?,?)",
                    (run_id, account, message.id,
                     json.dumps(metadata, ensure_ascii=False), insight.model_dump_json()),
                )
            for mid in ignored_ids:
                db.execute("INSERT OR IGNORE INTO mail_sync_seen VALUES(?,?)",
                           (account, mid))
            for mid, code in quarantines:
                if code not in UNREADABLE_CODES | {"message_disappeared"}:
                    raise MailError("unapproved_manual_review_code")
                db.execute("INSERT OR IGNORE INTO mail_sync_quarantine VALUES(?,?,?,?)",
                           (account, mid, code, now))
                db.execute("INSERT OR IGNORE INTO mail_sync_seen VALUES(?,?)",
                           (account, mid))
            checked_at = now if advance else row_checked_at
            db.execute("""INSERT INTO mail_sync_state
                (account,cursor,checked_at,attempted_at,last_result,last_error,last_count)
                VALUES(?,?,?,?,?,NULL,?)
                ON CONFLICT(account) DO UPDATE SET cursor=excluded.cursor,
                checked_at=excluded.checked_at,attempted_at=excluded.attempted_at,
                last_result=excluded.last_result,last_error=NULL,
                last_count=excluded.last_count""",
                (account, new_cursor, checked_at, now, result, len(observations)),
            )
            db.execute("DELETE FROM mail_sync_failures WHERE account=?", (account,))
        return {"status": result, "processed": len(observations),
                "run_id": run_id, "checked_at": now}

    def recent(self, account, limit=60):
        return recent_evidence(self.store, account, limit)



def recent_quarantines(store, account, limit=60):
    """Only locally saved manual-review metadata; never fetch Gmail on GET."""
    with store.connect() as db:
        rows = db.execute(
            "SELECT message_id,code,detected_at FROM mail_sync_quarantine "
            "WHERE account=? ORDER BY detected_at DESC,message_id DESC LIMIT ?",
            (account.casefold(), limit),
        ).fetchall()
    return [dict(r) for r in rows]


def recent_evidence(store, account, limit=60):
    """Pure SELECT for GET endpoints, with no migrations or write transactions."""
    with store.connect() as db:
        rows = db.execute("""SELECT i.metadata,i.insight,r.created_at
            FROM mail_sync_insights i JOIN runs r ON r.id=i.run_id
            WHERE i.account=? ORDER BY r.created_at DESC,i.message_id DESC LIMIT ?""",
            (account.casefold(), limit),
        ).fetchall()
    return [{"metadata": json.loads(r[0]), "insight": json.loads(r[1]),
             "created_at": r[2]} for r in rows]


def briefing(account, start, end, observations, deleted=0,
             recovered=False, pending=False, quarantines=()):
    buckets = {"action": [], "information": [], "low_priority": []}
    for message, insight in observations:
        buckets[insight.category].append((message, insight))
    label = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "OKAL • Gmail Briefing | موجز البريد الذكي",
        f"Coverage / الفترة: {label(start)} → {label(end)}",
        f"New / جديد: {len(observations)}  •  Needs action / يتطلب متابعة: {len(buckets['action'])}",
        f"Manual review / مراجعة يدوية: {len(quarantines)}",
        "AI suggestions only / اقتراحات آلية للمراجعة، بدون تنفيذ أو إرسال.",
    ]
    titles = [("action", "🔴 يحتاج متابعة | Action required"),
              ("information", "📨 للعلم | For your information"),
              ("low_priority", "🔕 أولوية منخفضة | Low priority")]
    for key, title in titles:
        group = buckets[key]
        if not group:
            continue
        lines += ["", f"{title} ({len(group)})"]
        for m, insight in group:
            lines.append(f"• {m.subject} — {m.sender}")
            lines.append(f"  {insight.summary}")
            if insight.suggested_action:
                lines.append(f"  Next / المقترح: {insight.suggested_action}")
            if m.attachment_count:
                lines.append(f"  ⚠ {m.attachment_count} unread attachment(s) / مرفقات غير محللة")
            lines.append("  " + source_link(account, m.id))
    if quarantines:
        lines.append("")
        lines.append("⚠ تعذر تحليل بعض الرسائل | Manual review required")
        for mid, code in quarantines:
            lines.append("  " + code + " • " + source_link(account, mid))
    if deleted:
        lines.append(f"⚠ {deleted} Gmail deletion or unavailable-message events; contents may be unavailable.")
    if pending:
        lines.append("⚠ More history messages are queued; this checkpoint is NOT complete yet.")
    if recovered:
        lines.append("⚠ Gmail history expired: visible-mail backfill only; deleted past messages cannot be reconstructed.")
    lines.append("Source emails are untrusted; verify dates, amounts, links and commitments in Gmail.")
    body = "\n".join(lines)
    if len(body) > 12000:
        raise MailError("digest_output_budget_exceeded_narrow_interval")
    return body


def run(store, cfg, api, model):
    """Called under the existing mail operation.lock by the worker or CLI."""
    state = HistoryState(store)
    now = int(store.clock())
    account = cfg.account
    current = state.current(account)
    previous = current["cursor"] if current else None
    recovered = False
    deleted = 0
    pending = False
    ignored_ids = []
    quarantines = []
    try:
        api.check_account(account)
        if previous is None:
            # Cut over from the legacy contiguous digest watermark if it exists.
            # Otherwise use a bounded initial 24-hour baseline. Never silently
            # discard a known last-success time after a shutdown.
            legacy = MailState(store).progress(account)
            start = legacy if legacy is not None else max(0, now - 86400)
            if not 0 <= start < now or now - start > MAX_WINDOW:
                raise MailError("history_backfill_window_exceeded_manual_review_required")
            # Capture cursor *before* fetching so arrivals during backfill replay.
            cursor = api.history_marker()
            messages = api.collect(start, now, cfg.max_messages, quarantine=quarantines)
            result = ("initial_legacy_checkpoint_backfill"
                      if legacy is not None else "initial_24h_backfill")
        else:
            start = current["checked_at"]
            try:
                # A bounded history listing may span several model batches. The
                # cursor stays unchanged until ALL listed IDs are accounted for.
                cursor, ids, deleted = api.history_changes(previous, cfg.max_messages * 10)
                already = state.seen(account, ids)
                pending_ids = [mid for mid in ids if mid not in already]
                batch = pending_ids[:cfg.max_messages]
                pending = len(pending_ids) > len(batch)
                ignored_ids = []
                observed = []
                for mid in batch:
                    try:
                        msg = api.get_optional(mid)
                    except MailError as exc:
                        if str(exc) not in UNREADABLE_CODES:
                            raise
                        quarantines.append((mid, str(exc)))
                        continue
                    if msg is None:
                        deleted += 1
                        ignored_ids.append(mid)
                    elif set(msg.labels) & SKIPPED_LABELS:
                        ignored_ids.append(mid)
                    else:
                        observed.append(msg)
                messages = observed
                result = "history_chunk_pending" if pending else "history_delta"
            except MailError as exc:
                if str(exc) != "history_cursor_expired":
                    raise
                if now - start > MAX_WINDOW:
                    raise MailError("history_backfill_window_exceeded_manual_review_required")
                recovered = True
                cursor = api.history_marker()
                # Overlap guards timestamp resolution/backdated arrivals after failure.
                messages = api.collect(max(0, start - 300), now, cfg.max_messages)
                result = "history_expired_visible_mail_backfill"
        # Existing seen-set is committed with the last cursor; duplicates remain inert.
        unique = {m.id: m for m in messages if not set(m.labels) & SKIPPED_LABELS}
        missing = set(unique) - state.seen(account, list(unique))
        if len(missing) > cfg.max_messages:
            raise MailError("message_budget_exceeded_narrow_interval")
        observations = []
        for mid in sorted(missing, key=lambda k: (unique[k].received_ms, k)):
            msg = unique[mid]
            if msg.truncated:
                quarantines.append(
                    (mid, "message_body_truncated_narrow_scope_or_review_manually")
                )
                continue
            observations.append((msg, model.summarize(msg)))
        body = briefing(account, start, now, observations, deleted if not pending else 0,
                        recovered, pending, quarantines)
        outcome = state.commit(
            account, previous, cursor, result, observations, body,
            ignored_ids=ignored_ids, advance=not pending, quarantines=quarantines,
            alert=(not pending and (recovered or deleted > 0 or bool(quarantines))),
        )
        outcome.update(deleted_or_unavailable=deleted, recovered=recovered,
                       manual_review=len(quarantines))
        return outcome
    except Exception as exc:
        state.failure(account, str(exc) if isinstance(exc, MailError) else "unknown")
        if isinstance(exc, MailError):
            raise
        raise MailError("sync_failed_check_local_doctor") from None


def local_status(store, account):
    """Read-only local evidence, never initialize sync tables or touch provider."""
    result = {"state": "never_run", "last_checked": None, "last_attempt": None,
              "last_count": None, "last_result": None, "last_error": None,
              "cursor_saved": False}
    try:
        with store.connect() as db:
            tables = {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "mail_sync_state" in tables:
                row = db.execute(
                    "SELECT checked_at,attempted_at,last_result,last_count "
                    "FROM mail_sync_state WHERE account=?", (account.casefold(),)
                ).fetchone()
                if row:
                    result.update(state="checkpoint_saved", last_checked=row[0],
                                  last_attempt=row[1], last_result=row[2],
                                  last_count=row[3], cursor_saved=True)
            if "mail_sync_quarantine" in tables:
                result["manual_review_count"] = db.execute(
                    "SELECT COUNT(*) FROM mail_sync_quarantine WHERE account=?",
                    (account.casefold(),),
                ).fetchone()[0]
            if "mail_sync_failures" in tables:
                row = db.execute(
                    "SELECT attempted_at,code FROM mail_sync_failures WHERE account=?",
                    (account.casefold(),)
                ).fetchone()
                if row:
                    result.update(last_attempt=row[0], last_error=row[1],
                                  state="failed_last_attempt")
    except Exception:
        result["state"] = "unavailable"
    return result
