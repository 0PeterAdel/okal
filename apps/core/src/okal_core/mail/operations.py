"""Owner-reviewed Gmail inbox actions. Read preview and explicit one-use confirm.

Operations: mark_read, mark_unread, archive. Never send, permanently delete,
run arbitrary LLM tools or automatically repeat an uncertain provider write.
Saved AI evidence is not mutated. Gmail stays the source of truth.
"""
from hashlib import sha256
import json
import re
from uuid import uuid4

from .contracts import MailError
from .viewer import allowed_source, _header

MID = re.compile(r"^[a-fA-F0-9]{1,64}$")
ACTIONS = {
    "mark_read": ([], ["UNREAD"]),
    "mark_unread": (["UNREAD"], []),
    "archive": ([], ["INBOX"]),
}
BANNED = {"TRASH", "SPAM", "SENT", "DRAFT"}


def _inputs(ids, action):
    if not isinstance(action, str) or action not in ACTIONS:
        raise MailError("unsupported_gmail_action")
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 20
            or any(not isinstance(mid, str) or not MID.fullmatch(mid) for mid in ids)
            or len(set(ids)) != len(ids)):
        raise MailError("invalid_action_message_ids")
    return sorted(ids)


def init_ledger(db):
    db.execute("""CREATE TABLE IF NOT EXISTS mail_action_events(
        id TEXT PRIMARY KEY, account TEXT NOT NULL, message_id TEXT NOT NULL,
        action TEXT NOT NULL, status TEXT NOT NULL
            CHECK(status IN ('attempting','confirmed')),
        created_at INTEGER NOT NULL, verified_at INTEGER
    )""")
    db.execute("""CREATE INDEX IF NOT EXISTS mail_action_attempts
        ON mail_action_events(account,message_id,action,status)""")


def native(api, mid, saved, action):
    row = api.call(
        api.service.users().messages().get(
            userId="me", id=mid, format="metadata", metadataHeaders=["Subject"]
        ), missing="action_source_unavailable"
    )
    if row.get("id") != mid:
        raise MailError("action_native_identity_changed")
    labels = row.get("labelIds")
    if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
        raise MailError("action_native_labels_invalid")
    labels = set(labels)
    if labels & BANNED:
        raise MailError("action_message_not_in_live_inbox")
    if action == "archive" and "INBOX" not in labels:
        raise MailError("action_already_outside_inbox")
    subject = _header(row.get("payload", {}).get("headers", []), "Subject")
    if not subject or (saved is not None and saved.get("subject") != subject):
        raise MailError("action_source_changed_review_gmail")
    return {"id": mid, "subject": subject[:160], "labels": sorted(labels)}


def preview(store, cfg, api, ids, action):
    mids = _inputs(ids, action)
    account = cfg.account.casefold()
    items = []
    with store.connect() as db:
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        for mid in mids:
            saved = allowed_source(store, account, mid)
            if "mail_action_events" in tables:
                prior = db.execute(
                    "SELECT status FROM mail_action_events WHERE account=? "
                    "AND message_id=? AND action=? AND status='attempting' "
                    "LIMIT 1", (account, mid, action)
                ).fetchone()
                if prior:
                    raise MailError("action_already_attempted_review_gmail")
            items.append(native(api, mid, saved, action))
    digest = sha256(json.dumps(
        [account, action, [(r["id"], r["subject"], r["labels"]) for r in items]],
        ensure_ascii=False, separators=(",",":")
    ).encode()).hexdigest()
    return {"action": action, "items": items, "count": len(items),
            "approval_digest": digest, "status": "approval_required",
            "external_writes": False}


def apply(store, cfg, api, ids, action, digest):
    if not cfg.trash_enabled:
        raise MailError("gmail_modify_scope_required")
    result = preview(store, cfg, api, ids, action)
    if digest != result["approval_digest"]:
        raise MailError("action_native_metadata_changed")
    added, removed = ACTIONS[action]
    succeeded = []
    for item in result["items"]:
        mid = item["id"]
        saved = allowed_source(store, cfg.account.casefold(), mid)
        native(api, mid, saved, action)  # check again before write
        with store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            init_ledger(db)
            exists = db.execute(
                "SELECT 1 FROM mail_action_events WHERE account=? "
                "AND message_id=? AND action=? AND status='attempting' LIMIT 1",
                (cfg.account.casefold(), mid, action)
            ).fetchone()
            if exists:
                raise MailError("action_already_attempted_review_gmail")
            event_id = uuid4().hex
            db.execute(
                "INSERT INTO mail_action_events VALUES(?,?,?,?, 'attempting',?,NULL)",
                (event_id,cfg.account.casefold(),mid,action,int(store.clock()))
            )
        try:
            api.call(api.service.users().messages().modify(
                userId="me", id=mid,
                body={"addLabelIds": added, "removeLabelIds": removed},
            ), write=True)
            check = api.call(
                api.service.users().messages().get(
                    userId="me", id=mid, format="minimal"
                ), missing="action_verify_missing"
            )
            labels = set(check.get("labelIds", []))
            if check.get("id") != mid or (
                (action == "mark_unread" and "UNREAD" not in labels)
                or (action == "mark_read" and "UNREAD" in labels)
                or (action == "archive" and "INBOX" in labels)
            ):
                raise MailError("action_verification_uncertain_check_gmail")
        except Exception:
            raise MailError("action_write_uncertain_check_gmail_no_auto_retry") from None
        with store.connect() as db, db:
            db.execute(
                "UPDATE mail_action_events SET status='confirmed',verified_at=? "
                "WHERE id=? AND status='attempting'",
                (int(store.clock()),event_id)
            )
        succeeded.append(mid)
    return {"status":"confirmed", "action": action, "count": len(succeeded),
            "message_ids": succeeded, "external_writes": True,
            "no_automatic_retry": True}
