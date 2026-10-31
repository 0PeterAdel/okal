#!/usr/bin/env python3
"""Owner-only Gmail live acceptance: no outgoing email, no secrets in reports.

The two explicit outage commands only stop/start okal-core.service.
The human sends two incoming test messages from ANOTHER Gmail account.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps/core/src"))
from okal_core.mail.private import read_private, write_private  # noqa: E402


class AcceptanceError(Exception):
    pass


def private_state(base):
    state = base.expanduser().absolute()
    if state.is_symlink() or not state.is_dir():
        raise AcceptanceError("private_core_state_directory_missing_or_linked")
    info = state.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise AcceptanceError("core_state_directory_requires_mode_0700")
    return state


def settings(state):
    path = state / "mail" / "config.json"
    if not path.is_file():
        raise AcceptanceError("mail_configuration_missing")
    return read_private(path)


def command(parts, timeout=240):
    try:
        result = subprocess.run(
            parts, cwd=ROOT, capture_output=True, text=True,
            check=False, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired):
        raise AcceptanceError("local_command_unavailable_or_timed_out") from None
    if result.returncode:
        errors = re.findall(r"Mail: ([a-z0-9_]{3,100})", result.stderr)
        raise AcceptanceError(errors[-1] if errors else "local_command_failed")
    return result.stdout


def mail(state, *args):
    raw = command([
        "bash", str(ROOT / "scripts/run-okal-core.sh"),
        "--state-dir", str(state), "mail", *args
    ])
    try:
        return json.loads(raw)
    except ValueError:
        raise AcceptanceError("unexpected_mail_command_response") from None


def status(state, account, subjects=()):
    uri = (state / "core.sqlite3").as_uri() + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5) as db:
            checkpoint = db.execute(
                "SELECT cursor,last_result,last_count FROM mail_sync_state "
                "WHERE account=?", (account.casefold(),)
            ).fetchone()
            error = db.execute(
                "SELECT code FROM mail_sync_failures WHERE account=?",
                (account.casefold(),)
            ).fetchone()
            counts = []
            for subject in subjects:
                rows = db.execute(
                    "SELECT message_id FROM mail_sync_insights "
                    "WHERE account=? AND json_extract(metadata,'$.subject')=?",
                    (account.casefold(), subject)
                ).fetchall()
                counts.append(len({item[0] for item in rows}))
    except sqlite3.Error:
        raise AcceptanceError("local_checkpoint_unavailable_run_baseline_first") from None
    return {
        "cursor": checkpoint[0] if checkpoint else None,
        "last_result": checkpoint[1] if checkpoint else None,
        "last_batch_count": checkpoint[2] if checkpoint else None,
        "last_error": error[0] if error else None,
        "matched_distinct_messages": counts,
    }


def report(data):
    # Never print accounts, message bodies, sender IDs, tokens or private paths.
    print(json.dumps(data, ensure_ascii=True, sort_keys=True, indent=2))


def acceptance_path(state):
    return state / "mail" / "live-acceptance.json"


def load_probe(state):
    path = acceptance_path(state)
    if not path.is_file():
        raise AcceptanceError("run_outage_start_first")
    item = read_private(path)
    if item.get("version") != 1 or item.get("phase") not in ("outage", "resumed"):
        raise AcceptanceError("invalid_acceptance_probe_state")
    return item


def systemd(action):
    if action not in ("stop", "start"):
        raise AcceptanceError("invalid_core_service_action")
    command(["systemctl", "--user", action, "okal-core.service"], timeout=60)
    active = command([
        "systemctl", "--user", "show", "--property=ActiveState",
        "--value", "okal-core.service"
    ], timeout=20).strip()
    if action == "start" and active != "active":
        raise AcceptanceError("core_service_not_active")
    if action == "stop" and active not in ("inactive", "failed"):
        raise AcceptanceError("core_service_not_stopped")



def verify_arrivals(state, cfg, probe):
    """Read only two exact native Gmail probe subjects before restarting Core.

    Never ask Ollama, fetch email bodies, or write a Gmail message.
    Search uses Gmail's own index, then checks exact metadata and arrival time.
    """
    from okal_core.mail.contracts import Config, MailError
    from okal_core.mail.provider import Gmail
    from okal_core.store import Store

    try:
        started_ms = int(datetime.fromisoformat(probe["started_at"]).timestamp() * 1000)
        expected = (probe["ar_subject"], probe["en_subject"])
        if not all(re.fullmatch(r"OKAL-LIVE-[A-F0-9]{12}-(AR|EN)", x) for x in expected):
            raise AcceptanceError("invalid_test_subject_marker")
        api = Gmail.open(Store(state), Config.model_validate(cfg))
        try:
            for subject in expected:
                # Gmail's subject search is approximate, so validate EXACT
                # subject and native internalDate from metadata responses.
                matches = set()
                query = f'subject:"{subject}" -in:sent -in:drafts -in:spam -in:trash'
                for mid in api.ids(query, 10):
                    row = api.call(api.service.users().messages().get(
                        userId="me", id=mid, format="metadata",
                        metadataHeaders=["Subject"],
                    ))
                    labels = set(row.get("labelIds", []))
                    if labels & {"SENT", "DRAFT", "SPAM", "TRASH"}:
                        continue
                    headers = [
                        h.get("value") for h in
                        row.get("payload", {}).get("headers", [])
                        if h.get("name", "").casefold() == "subject"
                    ]
                    if (len(headers) == 1 and headers[0] == subject
                            and int(row.get("internalDate", 0)) >= started_ms):
                        matches.add(mid)
                if len(matches) != 1:
                    raise AcceptanceError(
                        "test_messages_missing_or_not_sent_during_core_outage"
                    )
        finally:
            api.close()
    except AcceptanceError:
        raise
    except (MailError, KeyError, ValueError, TypeError):
        raise AcceptanceError("gmail_arrival_verification_failed") from None


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Private Gmail live acceptance, no outgoing mail"
    )
    p.add_argument(
        "phase", choices=(
            "preflight", "baseline", "outage-start", "outage-finish", "check"
        )
    )
    p.add_argument(
        "--state-dir", type=Path,
        default=Path(os.environ.get(
            "XDG_STATE_HOME", str(Path.home() / ".local/state")
        )) / "okal-core"
    )
    args = p.parse_args(argv)
    try:
        state = private_state(args.state_dir)
        cfg = settings(state)
        account = cfg.get("account")
        if not isinstance(account, str) or not account:
            raise AcceptanceError("invalid_mail_account_configuration")
        creds = state / "mail" / "token.json"

        if args.phase == "preflight":
            if not creds.exists():
                raise AcceptanceError("oauth_token_missing_authorize_locally")
            info = read_private(creds)
            if not info.get("refresh_token"):
                raise AcceptanceError("offline_oauth_refresh_token_missing")
            doctor = mail(state, "doctor")
            report({
                "phase": "preflight",
                "gmail_account_verified": bool(doctor.get("account_matches")),
                "local_model_verified": bool(doctor.get("local_model_matches")),
                "offline_refresh_credential_present": True,
                "send_permission_enabled": bool(cfg.get("send_enabled", False)),
                "live_bilingual_quality_reviewed": False,
            })

        elif args.phase == "baseline":
            doctor = mail(state, "doctor")
            if not (doctor.get("account_matches") and doctor.get("local_model_matches")):
                raise AcceptanceError("doctor_preconditions_failed")
            outcome = mail(state, "sync", "now")
            mail(state, "sync", "on")
            observed = status(state, account)
            if not observed["cursor"] or observed["last_error"]:
                raise AcceptanceError("baseline_checkpoint_not_healthy")
            report({
                "phase": "baseline", "sync_status": outcome.get("status"),
                "processed": outcome.get("processed"), "checkpoint_saved": True,
                "sync_enabled": True, "next": "outage-start",
            })

        elif args.phase == "outage-start":
            if not cfg.get("sync_enabled", False):
                raise AcceptanceError("automatic_sync_must_be_enabled")
            if acceptance_path(state).exists():
                previous_probe = load_probe(state)
                if previous_probe.get("phase") != "resumed":
                    raise AcceptanceError("existing_outage_probe_must_be_finished")
            before = status(state, account)
            if not before["cursor"] or before["last_error"]:
                raise AcceptanceError("healthy_baseline_required")
            systemd("stop")
            nonce = secrets.token_hex(6).upper()
            ar = f"OKAL-LIVE-{nonce}-AR"
            en = f"OKAL-LIVE-{nonce}-EN"
            write_private(acceptance_path(state), {
                "version": 1, "phase": "outage",
                "cursor_before": before["cursor"],
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ar_subject": ar, "en_subject": en,
            })
            report({
                "phase": "outage", "core_service_stopped": True,
                "arabic_test_subject": ar, "english_test_subject": en,
                "instructions": (
                    "Send two INCOMING emails with these exact subjects "
                    "from ANOTHER account, then run outage-finish."
                ),
            })

        elif args.phase == "outage-finish":
            probe = load_probe(state)
            if probe["phase"] != "outage":
                raise AcceptanceError("outage_already_finished")
            # Never resume and invalidate this probe unless BOTH exact subjects
            # have reached Gmail AFTER the outage began. Older tests are inert.
            verify_arrivals(state, cfg, probe)
            systemd("start")
            probe["phase"] = "resumed"
            probe["resumed_at"] = datetime.now(timezone.utc).isoformat()
            write_private(acceptance_path(state), probe)
            report({
                "phase": "resumed", "core_service_active": True,
                "automatic_sync_enabled": bool(cfg.get("sync_enabled", False)),
                "next": "Run check after background sync finishes.",
            })

        else:
            probe = load_probe(state)
            if probe["phase"] != "resumed":
                raise AcceptanceError(
                    "start_core_service_using_outage_finish_first"
                )
            latest = status(state, account, (
                probe["ar_subject"], probe["en_subject"]
            ))
            counts = latest["matched_distinct_messages"]
            cursor_advanced = bool(
                latest["cursor"] and
                int(latest["cursor"]) > int(probe["cursor_before"])
            )
            pending = latest["last_result"] == "history_chunk_pending"
            passed = (
                counts == [1, 1] and latest["last_error"] is None
                and cursor_advanced and not pending
            )
            report({
                "phase": "check", "gmail_sync_probes_passed": passed,
                "arabic_received_and_classified_once": counts[0] == 1,
                "english_received_and_classified_once": counts[1] == 1,
                "cursor_advanced_after_restart": cursor_advanced,
                "pending_batch": pending,
                "safe_error_code": latest["last_error"],
                "human_quality_review_still_required": True,
            })
            if not passed:
                return 2
        return 0
    except (AcceptanceError, OSError, ValueError, KeyError) as exc:
        code = str(exc)
        if not re.fullmatch(r"[a-z0-9_]{3,100}", code):
            code = "live_acceptance_local_error"
        report({"phase": args.phase, "status": "blocked", "safe_error_code": code})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
