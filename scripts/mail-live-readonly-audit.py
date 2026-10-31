#!/usr/bin/env python3
"""Owner-only live Gmail read audit. Never sends or mutates the inbox database.

The operator can run this once instead of sending artificial test emails.
This proves current Gmail identity, reconciles local AI/source evidence against
native Gmail metadata and checks the saved history cursor for pending events.
It cannot retrospectively prove a specific outage's exact timing.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps/core/src"))
from okal_core.mail.contracts import Config, Insight, MailError  # noqa: E402
from okal_core.mail.private import read_private  # noqa: E402
from okal_core.mail.provider import Gmail  # noqa: E402


class AuditError(Exception):
    pass


def read_evidence(state, account):
    """SQLite mode=ro; return minimal metadata internally, never raw body."""
    uri = (state / "core.sqlite3").as_uri() + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=10) as db:
            row = db.execute(
                "SELECT cursor,checked_at,attempted_at,last_result,last_count "
                "FROM mail_sync_state WHERE account=?", (account.casefold(),)
            ).fetchone()
            if not row:
                raise AuditError("no_successful_mail_checkpoint")
            failure = db.execute(
                "SELECT code FROM mail_sync_failures WHERE account=?",
                (account.casefold(),)
            ).fetchone()
            total = db.execute(
                "SELECT COUNT(*),COUNT(DISTINCT message_id) "
                "FROM mail_sync_insights WHERE account=?", (account.casefold(),)
            ).fetchone()
            quarantines = db.execute(
                "SELECT COUNT(*) FROM mail_sync_quarantine WHERE account=?",
                (account.casefold(),)
            ).fetchone()[0]
            previous_tests = db.execute(
                "SELECT COUNT(DISTINCT json_extract(metadata,'$.subject')) "
                "FROM mail_sync_insights WHERE account=? AND "
                "json_extract(metadata,'$.subject') LIKE 'OKAL-LIVE-%'",
                (account.casefold(),)
            ).fetchone()[0]
            rows = db.execute(
                "SELECT message_id,metadata,insight FROM mail_sync_insights "
                "WHERE account=? ORDER BY rowid DESC LIMIT 12",
                (account.casefold(),)
            ).fetchall()
    except (sqlite3.Error, OSError):
        raise AuditError("private_mail_database_read_failed") from None
    return {
        "checkpoint": row[0], "checked_at": row[1],
        "attempted_at": row[2], "last_result": row[3],
        "last_count": row[4],
        "last_error": failure[0] if failure else None,
        "insight_rows": total[0], "unique_insight_messages": total[1],
        "quarantines": quarantines, "historic_test_subjects": previous_tests,
        "rows": rows,
    }


def audit(state, cfg, api, now=None):
    """Reconcile recent saved messages with live provider without sending."""
    now = int(time.time()) if now is None else int(now)
    e = read_evidence(state, cfg.account)
    mismatches = 0
    selected = []
    for mid, raw_meta, raw_insight in e["rows"]:
        try:
            stored = json.loads(raw_meta)
            insight = Insight.model_validate_json(raw_insight)
            if insight.source_id != mid or stored["id"] != mid:
                mismatches += 1
                continue
            selected.append((mid, stored))
        except (ValueError, KeyError, TypeError):
            mismatches += 1

    checked = 0
    unavailable = 0
    for mid, stored in selected[:8]:
        try:
            row = api.call(api.service.users().messages().get(
                userId="me", id=mid, format="metadata",
                metadataHeaders=["Subject"]
            ), missing="message_disappeared")
        except MailError as exc:
            if str(exc) == "message_disappeared":
                unavailable += 1
                continue
            raise
        if row.get("id") != mid or not row.get("threadId"):
            mismatches += 1
            continue
        checked += 1

    # Native Gmail HISTORY (read-only) tells us whether the saved cursor needs
    # catch-up. There may be label changes which aren't new incoming mail.
    native_marker, added, deleted = api.history_changes(e["checkpoint"], 10000)
    native_advanced = int(native_marker) >= int(e["checkpoint"])
    if not native_advanced:
        raise AuditError("gmail_history_cursor_regressed")

    # Check only recent visible mail within a *bounded* interval. An unseen
    # item is a pending/background-sync candidate, not automatically a loss.
    query = (
        f"after:{max(0, now - 7200) - 1} before:{now + 1} "
        "-in:sent -in:drafts -in:spam -in:trash"
    )
    recent = api.ids(query, 80)
    seen_recent = set()
    if recent:
        with sqlite3.connect(
            (state / "core.sqlite3").as_uri() + "?mode=ro", uri=True, timeout=10
        ) as db:
            seen_recent = {r[0] for r in db.execute(
                "SELECT message_id FROM mail_sync_seen WHERE account=? "
                "AND message_id IN (" + ",".join("?" for _ in recent) + ")",
                (cfg.account.casefold(), *recent),
            )}
    # The native history list can span older already-processed messages.
    # Compare against the COMPLETE persisted dedupe ledger, not only the
    # last two hours of visible messages.
    unseen_history = 0
    if added:
        with sqlite3.connect(
            (state / "core.sqlite3").as_uri() + "?mode=ro", uri=True, timeout=10
        ) as db:
            for n in range(0, len(added), 200):
                chunk = added[n:n + 200]
                accounted = {r[0] for r in db.execute(
                    "SELECT message_id FROM mail_sync_seen WHERE account=? "
                    "AND message_id IN (" + ",".join("?" for _ in chunk) + ")",
                    (cfg.account.casefold(), *chunk),
                )}
                unseen_history += len(set(chunk) - accounted)
    fresh = now - e["checked_at"] <= 900 and now >= e["checked_at"]
    has_usable_evidence = e["unique_insight_messages"] >= 1 and checked >= 1
    valid_local = (
        mismatches == 0 and e["insight_rows"] == e["unique_insight_messages"]
        and e["last_error"] is None
    )
    return {
        "mode": "existing_mail_readonly_live_audit",
        "gmail_identity_verified": True,  # Gmail.open checked account identity
        "saved_checkpoint_exists": True,
        "last_sync_result": e["last_result"],
        "last_sync_processed": e["last_count"],
        "checkpoint_recent_15min": fresh,
        "stored_unique_insights": e["unique_insight_messages"],
        "stored_duplicate_source_ids": e["insight_rows"] - e["unique_insight_messages"],
        "stored_source_mismatches_in_sample": mismatches,
        "native_gmail_messages_verified": checked,
        "native_sources_no_longer_available": unavailable,
        "historic_live_test_subjects": e["historic_test_subjects"],
        "manual_review_queue_size": e["quarantines"],
        "unprocessed_new_gmail_history_ids": unseen_history,
        "recent_visible_gmail_messages_checked": len(recent),
        "recent_visible_messages_locally_seen": len(seen_recent),
        "recent_visible_messages_not_yet_seen": len(set(recent) - seen_recent),
        "gmail_history_deleted_events": deleted,
        "native_history_cursor_valid": native_advanced,
        "mail_reconciliation_passed": bool(has_usable_evidence and valid_local
                                            and native_advanced),
        "specific_outage_catchup_proven": False,
        "bilingual_summary_quality_reviewed": False,
        "owner_must_send_more_test_messages": False,
        "note": "Live source reconciliation is not a proof of a particular outage or all historical mail.",
    }


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(
        description="Live Gmail audit using existing mail; no new messages needed."
    )
    p.add_argument(
        "--state-dir", type=Path,
        default=Path(os.environ.get("XDG_STATE_HOME",
                                  str(Path.home() / ".local/state"))) / "okal-core"
    )
    args = p.parse_args(argv)
    api = None
    try:
        state = args.state_dir.expanduser().absolute()
        info = state.stat()
        if (state.is_symlink() or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise AuditError("private_state_permissions_invalid")
        cfg = Config.model_validate(read_private(state / "mail" / "config.json"))
        e = read_evidence(state, cfg.account)
        if not e["checkpoint"]:
            raise AuditError("no_successful_mail_checkpoint")
        api = Gmail.open(SimpleNamespace(directory=state), cfg)
        results = audit(state, cfg, api)
        print(json.dumps(results, indent=2, sort_keys=True, ensure_ascii=True))
        return 0 if results["mail_reconciliation_passed"] else 2
    except (AuditError, MailError) as exc:
        print(json.dumps({
            "status": "incomplete",
            "safe_error_code": str(exc) if str(exc) in {
                "no_successful_mail_checkpoint", "private_mail_database_read_failed",
                "private_state_permissions_invalid", "provider_read_failed",
                "authorization_required", "history_cursor_expired",
                "message_budget_exceeded_narrow_interval", "page_budget_exceeded",
                "gmail_history_cursor_regressed",
            } else "live_audit_incomplete",
            "owner_must_send_more_test_messages": False,
        }))
        return 2
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"status": "incomplete",
                          "safe_error_code": "live_audit_incomplete",
                          "owner_must_send_more_test_messages": False}))
        return 2
    finally:
        if api:
            api.close()


if __name__ == "__main__":
    raise SystemExit(main())
