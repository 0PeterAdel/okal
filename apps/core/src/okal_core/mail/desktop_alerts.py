"""Opt-in aggregate desktop notice after successful *incremental* Gmail sync.

No mail title/sender/account/body, no provider/LLM request, no extra polling.
Claim each committed history run once before best-effort notify-send to avoid
duplicates after systemd restarts. This is NOT instant Gmail Push.
"""
import re
import shutil
import subprocess

_ALLOWED = frozenset({"history_delta", "history_chunk_pending"})
_RUN_ID = re.compile(r"^[a-f0-9]{32}$")


def claim_new_mail_notice(store, outcome):
    if not isinstance(outcome, dict):
        return False
    status = outcome.get("status")
    count = outcome.get("processed")
    run_id = outcome.get("run_id")
    if (status not in _ALLOWED or type(count) is not int or
            not 1 <= count <= 100 or
            not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id)):
        return False
    with store.connect() as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS mail_desktop_alert_claims (
            run_id TEXT PRIMARY KEY, claimed_at INTEGER NOT NULL
        )""")
        cursor = db.execute(
            "INSERT OR IGNORE INTO mail_desktop_alert_claims VALUES(?,?)",
            (run_id, int(store.clock())),
        )
        # Bound table size; cursor/run IDs are never revealed in notifications.
        db.execute("DELETE FROM mail_desktop_alert_claims WHERE claimed_at<?",
                   (int(store.clock()) - 90 * 86400,))
        return cursor.rowcount == 1


def desktop_new_mail_notice(count):
    """One generic local OS notification; no email content and no shell."""
    if type(count) is not int or not 1 <= count <= 100:
        return False
    exe = shutil.which("notify-send")
    if not exe:
        return False
    noun = "رسالة" if count == 1 else "رسائل"
    try:
        done = subprocess.run(
            [exe, "--app-name=OKAL", "--expire-time=8000",
             "OKAL · بريد جديد",
             "وصلتك " + str(count) + " " + noun +
             " جديدة تمت مراجعتها محليًا. افتح OKAL للاطلاع."],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=3, check=False,
        )
        return done.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def maybe_notify(store, outcome, *, enabled, deliver=desktop_new_mail_notice):
    if enabled is not True:
        return False
    if not claim_new_mail_notice(store, outcome):
        return False
    try:
        # A notification failure never rolls back Gmail history or repeats.
        return bool(deliver(outcome["processed"]))
    except Exception:
        return False
