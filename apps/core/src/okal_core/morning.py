"""Voice-ready morning brief from trusted local task and Gmail provenance.

No generative inventions, Gmail calls, network, external model requests,
calendar claims, or writes. Generated on local read when dashboard opens.
"""
from datetime import datetime, timedelta, timezone
from html import escape
import os
import shutil
import subprocess
import json
from zoneinfo import ZoneInfo

from .tasks import TaskBoard
from .mail.contracts import Insight
from .mail.private import config
from .mail.workflows import source_link

CAIRO = ZoneInfo("Africa/Cairo")


def _short(value, limit=95):
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def morning_brief(store):
    now = datetime.fromtimestamp(int(store.clock()), CAIRO)
    today = now.date()
    hour = now.hour
    greeting = ("صباح الفل!" if 4 <= hour < 12 else
                "مساء الفل!" if 12 <= hour < 19 else "أهلًا بيك!")
    info = {
        "date": today.isoformat(), "timezone": "Africa/Cairo",
        "greeting": greeting, "voice_ready": True,
        "has_verified_calendar": False,
        "data_source": "local_saved_gmail_and_approved_tasks_only",
        "mail_last_sync_at": None,
        "mail_sync_stale": True,
        "today_tasks": [], "overdue_tasks": [],
        "new_action_emails": [], "new_info_emails": [],
        "spoken_text": "", "calendar_note": "Google Calendar مش مربوط لسه.",
        "no_external_actions": True,
    }
    task_rows = TaskBoard(store).list(status="open", limit=100)["items"]
    for task in task_rows:
        if task["due_at"] is None:
            continue
        due = datetime.fromtimestamp(task["due_at"], CAIRO)
        row = {"title": _short(task["title"], 110),
               "time": due.strftime("%H:%M"), "task_id": task["id"],
               "source_link": task["source_link"]}
        if due.date() == today and len(info["today_tasks"]) < 7:
            info["today_tasks"].append(row)
        elif due.date() < today and len(info["overdue_tasks"]) < 5:
            info["overdue_tasks"].append(row)
    try:
        account = config(store).account.casefold()
    except (ValueError, OSError):
        account = None

    if account:
        with store.connect() as db:
            tables = {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if "mail_sync_state" in tables:
                row = db.execute(
                    "SELECT checked_at FROM mail_sync_state WHERE account=?",
                    (account,),
                ).fetchone()
                if row:
                    info["mail_last_sync_at"] = row[0]
                    info["mail_sync_stale"] = (
                        int(store.clock()) - row[0] > 900
                    )
            if "mail_sync_insights" in tables:
                # Last 24 hours of RECEIVED mail only. Never use record
                # creation time as if it were delivery time.
                since_ms = int((now - timedelta(hours=24)).timestamp() * 1000)
                excluded = ""
                if "mail_trash_events" in tables:
                    excluded = """ AND NOT EXISTS (
                        SELECT 1 FROM mail_trash_events e
                        WHERE e.account=i.account AND e.message_id=i.message_id
                          AND e.status='confirmed_trash')"""
                rows = db.execute(
                    """SELECT i.message_id,i.metadata,i.insight
                       FROM mail_sync_insights i
                       WHERE i.account=? AND json_extract(i.metadata,'$.received_ms')>=?
                       """ + excluded +
                    """ ORDER BY json_extract(i.metadata,'$.received_ms') DESC
                        LIMIT 60""", (account, since_ms)
                ).fetchall()
                for row in rows:
                    try:
                        m = json.loads(row["metadata"])
                        insight = Insight.model_validate_json(row["insight"])
                        if insight.source_id != row["message_id"] or m["id"] != row["message_id"]:
                            continue
                        if "TRASH" in m.get("labels", []) or "SENT" in m.get("labels", []):
                            continue
                        item = {
                            "subject": _short(m.get("subject", ""), 110),
                            "sender": _short(m.get("sender", ""), 80),
                            "summary": _short(insight.summary, 190),
                            "source_link": source_link(account, row["message_id"]),
                        }
                        if insight.category == "action" and len(info["new_action_emails"]) < 4:
                            info["new_action_emails"].append(item)
                        elif insight.category == "information" and len(info["new_info_emails"]) < 3:
                            info["new_info_emails"].append(item)
                    except (ValueError, KeyError, TypeError):
                        continue

    sentences = [greeting, "ده ملخص يومك من الحاجات المسجلة عندي."]
    if info["today_tasks"]:
        events = "، ".join(
            f"{i['title']} الساعة {i['time']}" for i in info["today_tasks"][:4]
        )
        sentences.append("النهاردة عندك " + events + ".")
    else:
        sentences.append("مافيش مهام بمواعيد مؤكدة متسجلة عندي للنهاردة.")
    if info["overdue_tasks"]:
        sentences.append(
            "وفيه " + str(len(info["overdue_tasks"])) +
            " مهمة متأخرة محتاجة تبص عليها."
        )
    if info["new_action_emails"]:
        top = info["new_action_emails"][:3]
        sentences.append(
            "في البريد، فيه " + str(len(info["new_action_emails"])) +
            " رسالة محتاجة متابعة، أهمهم: " +
            "؛ ".join(i["summary"] for i in top) + "."
        )
    elif info["mail_sync_stale"]:
        sentences.append("آخر تحديث للبريد قديم، فمش هفترض إن مفيش رسائل جديدة.")
    else:
        sentences.append("مفيش رسائل جديدة محتاجة إجراء ضمن آخر 24 ساعة من اللي اتحفظ.")
    if info["new_info_emails"]:
        sentences.append(
            "وللعلم: " + "؛ ".join(i["summary"]
                                      for i in info["new_info_emails"][:2]) + "."
        )
    sentences.append(
        "المواعيد دي من مهامك المحلية المؤكدة، مش من تقويم Google؛ "
        "وملخصات البريد اقتراحات محتاجة مراجعة."
    )
    info["spoken_text"] = " ".join(sentences)[:1800]
    info["body"] = info["spoken_text"]
    return info


def notify_login_once(store):
    """Optional owner desktop notification, at most one success per Cairo day.

    No arbitrary LLM command execution. All untrusted text is escaped as
    notification markup, and failures do not claim delivery.
    """
    today = datetime.fromtimestamp(int(store.clock()), CAIRO).date().isoformat()
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return {"status": "display_unavailable", "delivered": False}
    if not shutil.which("notify-send"):
        return {"status": "notify_send_unavailable", "delivered": False}
    with store.connect() as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS morning_notifications (
            day TEXT PRIMARY KEY,
            delivered_at INTEGER NOT NULL
        )""")
        if db.execute("SELECT 1 FROM morning_notifications WHERE day=?",
                      (today,)).fetchone():
            return {"status": "already_delivered_today", "delivered": False}
        briefing = morning_brief(store)
        message = escape(briefing["spoken_text"][:700], quote=False)
        try:
            process = subprocess.run(
                ["notify-send", "--app-name=OKAL",
                 "--expire-time=15000",
                 "OKAL · موجز يومك", message],
                check=False, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=8,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {"status": "notification_transport_failed", "delivered": False}
        if process.returncode != 0:
            return {"status": "notification_transport_failed", "delivered": False}
        db.execute(
            "INSERT INTO morning_notifications VALUES(?,?)",
            (today, int(store.clock())),
        )
    return {"status": "delivered", "delivered": True,
            "date": today, "read_only": True}
