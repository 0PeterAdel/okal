"""Mail extension in the SAME SQLite database, with atomic inbox completion."""

import hashlib
import json
import uuid

from ..models import SummaryInput
from .contracts import Draft, MailError


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class MailState:
    def __init__(self, store):
        self.store = store
        with store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "CREATE TABLE IF NOT EXISTS mail_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)"
            )
            version = db.execute(
                "SELECT value FROM mail_meta WHERE key='version'"
            ).fetchone()
            if version and version[0] != "1":
                raise MailError("unsupported_mail_schema")
            db.execute("""CREATE TABLE IF NOT EXISTS mail_jobs (
                id TEXT PRIMARY KEY, account TEXT NOT NULL, start INTEGER NOT NULL,
                end INTEGER NOT NULL, status TEXT NOT NULL, run_id TEXT,
                error TEXT, count INTEGER NOT NULL DEFAULT 0, updated INTEGER NOT NULL,
                UNIQUE(account,start,end))""")
            db.execute("""CREATE TABLE IF NOT EXISTS mail_sources (
                job_id TEXT NOT NULL REFERENCES mail_jobs(id) ON DELETE CASCADE,
                message_id TEXT NOT NULL, metadata TEXT NOT NULL, insight TEXT NOT NULL,
                PRIMARY KEY(job_id,message_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS mail_progress (
                account TEXT PRIMARY KEY, through INTEGER NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS mail_drafts (
                id TEXT PRIMARY KEY, account TEXT NOT NULL, payload TEXT NOT NULL,
                digest TEXT NOT NULL, rfc_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
                created INTEGER NOT NULL, previewed INTEGER, provider_id TEXT,
                raw BLOB, receipt TEXT)""")
            db.execute("INSERT OR IGNORE INTO mail_meta VALUES('version','1')")

    def begin(self, account, start, end):
        key = fingerprint([account.casefold(), start, end])
        now = int(self.store.clock())
        with self.store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM mail_jobs WHERE id=?", (key,)).fetchone()
            if old and old["status"] == "succeeded":
                return key, old["run_id"]
            db.execute(
                "INSERT INTO mail_jobs(id,account,start,end,status,updated) VALUES(?,?,?,?,'running',?) "
                "ON CONFLICT(id) DO UPDATE SET status='running',error=NULL,updated=excluded.updated",
                (key, account.casefold(), start, end, now),
            )
        return key, None

    def fail(self, key, code):
        with self.store.connect() as db, db:
            db.execute(
                "UPDATE mail_jobs SET status='failed',error=?,updated=? WHERE id=? AND status='running'",
                (code, int(self.store.clock()), key),
            )

    def complete(self, key, account, start, end, body, sources):
        item = SummaryInput(
            workflow="mail",
            account_ref=fingerprint(account.casefold()),
            occurrence="gmail:" + key,
            title="ملخص البريد — مقترح آلي",
            body=body,
            data_kind="live",
        )
        run_id = uuid.uuid4().hex
        now = int(self.store.clock())
        with self.store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute("SELECT * FROM mail_jobs WHERE id=?", (key,)).fetchone()
            if (
                not job
                or job["status"] != "running"
                or job["account"] != account.casefold()
                or job["start"] != start
                or job["end"] != end
            ):
                raise MailError("job_ownership_mismatch")
            db.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
                (
                    run_id,
                    item.workflow,
                    item.account_ref,
                    item.occurrence,
                    fingerprint(item.model_dump()),
                    now,
                    "succeeded",
                ),
            )
            db.execute(
                "INSERT INTO summaries(run_id,title,body,data_kind) VALUES(?,?,?,?)",
                (run_id, item.title, item.body, item.data_kind),
            )
            for message, insight in sources:
                metadata = message.model_dump(exclude={"body"})
                metadata["body_sha256"] = hashlib.sha256(
                    message.body.encode()
                ).hexdigest()
                db.execute(
                    "INSERT INTO mail_sources VALUES(?,?,?,?)",
                    (
                        key,
                        message.id,
                        json.dumps(metadata, ensure_ascii=False),
                        insight.model_dump_json(),
                    ),
                )
            # Manual overlapping/backfill runs cannot move the watermark backwards.
            previous = db.execute(
                "SELECT through FROM mail_progress WHERE account=?",
                (account.casefold(),),
            ).fetchone()
            if previous and start > previous[0]:
                # A non-contiguous manual interval must not silently skip the gap.
                pass
            else:
                db.execute(
                    "INSERT INTO mail_progress VALUES(?,?) ON CONFLICT(account) DO UPDATE "
                    "SET through=MAX(through,excluded.through)",
                    (account.casefold(), end),
                )
            db.execute(
                "UPDATE mail_jobs SET status='succeeded',run_id=?,count=?,updated=? WHERE id=?",
                (run_id, len(sources), now, key),
            )
        return run_id

    def progress(self, account):
        with self.store.connect() as db:
            row = db.execute(
                "SELECT through FROM mail_progress WHERE account=?",
                (account.casefold(),),
            ).fetchone()
        return row[0] if row else None

    def jobs(self):
        with self.store.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id,start,end,status,run_id,error,count,updated "
                    "FROM mail_jobs ORDER BY updated DESC LIMIT 50"
                )
            ]

    def sources(self, key):
        with self.store.connect() as db:
            return [
                {
                    "message_id": r[0],
                    "metadata": json.loads(r[1]),
                    "insight": json.loads(r[2]),
                }
                for r in db.execute(
                    "SELECT message_id,metadata,insight FROM mail_sources WHERE job_id=?",
                    (key,),
                )
            ]

    def schedule_status(self):
        with self.store.connect() as db:
            return dict(
                db.execute(
                    "SELECT key,value FROM mail_meta WHERE key IN "
                    "('next_due','retry_after','attempts','last_scheduler_result')"
                )
            )

    def new_draft(self, account, draft):
        draft = Draft.model_validate(draft.model_dump())
        if bool(draft.thread_id) != bool(draft.in_reply_to):
            raise MailError("reply_requires_thread_and_message_id")
        key = uuid.uuid4().hex
        digest = fingerprint([account.casefold(), draft.model_dump()])
        with self.store.connect() as db, db:
            db.execute(
                "INSERT INTO mail_drafts(id,account,payload,digest,rfc_id,status,created) "
                "VALUES(?,?,?,?,?,'draft',?)",
                (
                    key,
                    account.casefold(),
                    draft.model_dump_json(),
                    digest,
                    f"<okal-{key}@okal.local>",
                    int(self.store.clock()),
                ),
            )
        return key

    def draft(self, key):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM mail_drafts WHERE id=?", (key,)).fetchone()
        if not row:
            raise MailError("draft_not_found")
        return dict(row)

    def preview(self, key):
        row = self.draft(key)
        if row["status"] != "draft":
            raise MailError("draft_not_sendable")
        with self.store.connect() as db, db:
            db.execute(
                "UPDATE mail_drafts SET previewed=? WHERE id=?",
                (int(self.store.clock()), key),
            )
        return {
            "id": key,
            "from": row["account"],
            "draft": json.loads(row["payload"]),
            "approval_digest": row["digest"],
            "expires_in_seconds": 600,
            "warning": "Verify every recipient, fact and commitment. No attachment or reply-all support.",
        }

    def pending(self, key, account, digest, raw):
        now = int(self.store.clock())
        with self.store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM mail_drafts WHERE id=?", (key,)).fetchone()
            if (
                not row
                or row["account"] != account.casefold()
                or row["digest"] != digest
                or row["status"] != "draft"
                or row["previewed"] is None
                or not 0 <= now - row["previewed"] <= 600
            ):
                raise MailError("approval_expired_or_mismatched")
            db.execute(
                "UPDATE mail_drafts SET status='needs_reconciliation',raw=?,previewed=NULL WHERE id=?",
                (raw, key),
            )

    def receipt(self, key, provider_id, verified):
        with self.store.connect() as db, db:
            db.execute(
                "UPDATE mail_drafts SET status=?,provider_id=?,receipt=? WHERE id=? AND status IN ('needs_reconciliation','accepted_unverified')",
                (
                    "sent_verified" if verified else "accepted_unverified",
                    provider_id,
                    json.dumps(
                        {
                            "provider_id": provider_id,
                            "verified": verified,
                            "checked_at": int(self.store.clock()),
                        }
                    ),
                    key,
                ),
            )

    def drafts(self):
        with self.store.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id,status,created,provider_id FROM mail_drafts ORDER BY created DESC LIMIT 100"
                )
            ]

    def prune(self, before):
        # Explicit owner-invoked deletion of old digest material ONLY. Keep send receipts.
        with self.store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            ids = [
                r[0]
                for r in db.execute(
                    "SELECT run_id FROM mail_jobs WHERE updated<? AND run_id IS NOT NULL",
                    (before,),
                )
            ]
            for run in ids:
                db.execute("DELETE FROM summaries WHERE run_id=?", (run,))
                db.execute("DELETE FROM runs WHERE id=?", (run,))
            # Only old history-generated summaries and message metadata are pruned.
            # Keep mail_sync_seen and the last committed history cursor for idempotency.
            tables = {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            history_ids = []
            if "mail_sync_insights" in tables:
                history_ids = [r[0] for r in db.execute(
                    "SELECT id FROM runs WHERE workflow='mail' "
                    "AND occurrence LIKE 'gmail-history:%' AND created_at<?",
                    (before,),
                )]
                for rid in history_ids:
                    db.execute("DELETE FROM mail_sync_insights WHERE run_id=?", (rid,))
                    db.execute("DELETE FROM summaries WHERE run_id=?", (rid,))
                    db.execute("DELETE FROM runs WHERE id=?", (rid,))
            # Keep the job idempotency tombstone, so pruning cannot republish the interval.
            deleted = db.execute(
                "DELETE FROM mail_sources WHERE job_id IN (SELECT id FROM mail_jobs WHERE updated<?)",
                (before,),
            ).rowcount
        return {
            "source_rows_deleted": deleted,
            "history_briefings_deleted": len(history_ids),
            "inbox_digests_deleted": len(ids),
            "job_tombstones_and_send_receipts_retained": True,
        }
