"""Explicit recoverable Gmail Trash with local provenance and no auto retries.

Owner selects exact known message IDs; preview is read-only. Applying requires
an interactive terminal and a fresh exact confirmation digest. Local operation
ledger prevents silent duplicate writes after an ambiguous Gmail response.
"""
from hashlib import sha256
import json
import re

from .contracts import Insight, MailError

MID = re.compile(r"^[a-fA-F0-9]{1,64}$")
EXCLUDED = {"SENT", "DRAFT", "SPAM", "TRASH", "IMPORTANT", "STARRED"}
MAX_BATCH = 20


def _ids(ids):
    if (not isinstance(ids, list) or not 1 <= len(ids) <= MAX_BATCH
            or any(not isinstance(m, str) or not MID.fullmatch(m) for m in ids)
            or len(set(ids)) != len(ids)):
        raise MailError("trash_requires_1_to_20_unique_message_ids")
    return sorted(ids)


def init_ledger(db):
    db.execute("""CREATE TABLE IF NOT EXISTS mail_trash_events (
        account TEXT NOT NULL, message_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('attempting','confirmed_trash')),
        attempted_at INTEGER NOT NULL, verified_at INTEGER,
        PRIMARY KEY(account,message_id)
    )""")


def _read_record(store, account, mid):
    with store.connect() as db:
        row = db.execute(
            "SELECT metadata,insight FROM mail_sync_insights "
            "WHERE account=? AND message_id=? ORDER BY rowid DESC LIMIT 1",
            (account, mid),
        ).fetchone()
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        prior = db.execute(
            "SELECT status FROM mail_trash_events WHERE account=? AND message_id=?",
            (account, mid),
        ).fetchone() if "mail_trash_events" in tables else None
    if prior:
        raise MailError("trash_previously_attempted_or_confirmed_review_gmail")
    if row is None:
        raise MailError("trash_source_not_in_saved_inbox")
    try:
        metadata = json.loads(row["metadata"])
        insight = Insight.model_validate_json(row["insight"])
        if metadata["id"] != mid or insight.source_id != mid:
            raise ValueError()
        if insight.category != "information":
            raise MailError("trash_only_information_category")
        if not isinstance(metadata["subject"], str):
            raise ValueError()
        if not isinstance(metadata["labels"], list):
            raise ValueError()
        if set(metadata["labels"]) & EXCLUDED:
            raise MailError("trash_protected_or_outdated_saved_labels")
        return metadata
    except MailError:
        raise
    except (ValueError, KeyError, TypeError):
        raise MailError("trash_untrusted_saved_evidence_invalid") from None


def _native(api, mid, saved):
    """Compare native provider metadata to trusted stored source before write."""
    row = api.call(
        api.service.users().messages().get(
            userId="me", id=mid, format="metadata",
            metadataHeaders=["Subject"],
        ), missing="trash_source_unavailable"
    )
    labels = set(row.get("labelIds", []))
    subjects = [
        h["value"] for h in row.get("payload", {}).get("headers", [])
        if h.get("name", "").casefold() == "subject"
    ]
    if (row.get("id") != mid or labels & EXCLUDED or len(subjects) != 1
            or subjects[0] != saved["subject"]):
        raise MailError("trash_native_metadata_changed_or_protected")
    return labels


def preview(store, cfg, api, selected_ids):
    mids = _ids(selected_ids)
    account = cfg.account.casefold()
    items = []
    for mid in mids:
        saved = _read_record(store, account, mid)
        _native(api, mid, saved)
        items.append({"id": mid, "subject": saved["subject"][:160],
                      "sender": str(saved.get("sender", ""))[:120]})
    digest = sha256(json.dumps(
        [account, [(item["id"], item["subject"]) for item in items]],
        ensure_ascii=False, separators=(",", ":"),
    ).encode()).hexdigest()
    return {"status": "approval_required", "count": len(items),
            "items": items, "approval_digest": digest,
            "warning": "Moves only these Gmail messages to recoverable Trash. Never permanent delete.",
            "external_writes": False}


def apply(store, cfg, api, selected_ids, expected_digest):
    if not cfg.trash_enabled:
        raise MailError("trash_permission_disabled_reauthorize")
    # re-read all existing evidence and provider metadata immediately before
    # each user-confirmed batch; never trust stale browser classifications.
    approval = preview(store, cfg, api, selected_ids)
    if expected_digest != approval["approval_digest"]:
        raise MailError("trash_approval_changed_cancelled")
    done = []
    for item in approval["items"]:
        mid = item["id"]
        # Write an attempt tombstone BEFORE the provider call. If the client
        # crashes or Gmail fails ambiguously, never send the write again.
        with store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            init_ledger(db)
            existing = db.execute(
                "SELECT 1 FROM mail_trash_events WHERE account=? AND message_id=?",
                (cfg.account.casefold(), mid),
            ).fetchone()
            if existing:
                raise MailError("trash_previous_attempt_manual_review_no_retry")
            db.execute(
                "INSERT INTO mail_trash_events VALUES(?,?, 'attempting', ?, NULL)",
                (cfg.account.casefold(), mid, int(store.clock())),
            )
        try:
            api.move_to_trash(mid)  # single no-retry provider write
        except Exception:
            raise MailError("trash_write_uncertain_manual_gmail_review") from None
        with store.connect() as db, db:
            db.execute(
                "UPDATE mail_trash_events SET status='confirmed_trash',verified_at=? "
                "WHERE account=? AND message_id=? AND status='attempting'",
                (int(store.clock()), cfg.account.casefold(), mid),
            )
        done.append(mid)
    return {"status": "confirmed_trash", "moved": len(done),
            "recoverable_in_gmail_trash": True, "permanent_delete": False,
            "note": "Provider-confirmed subset only; review any unconfirmed IDs manually."}
