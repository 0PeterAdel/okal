"""Short, speech-ready daily facts with on-demand details; no inferred plans."""
from datetime import datetime, timedelta, time

from .morning import CAIRO, _short
from .morning_ai import view as editorial_view
from .local_calendar import LocalCalendar
from .task_planner import TaskPlanner
from .google_tasks import cached


def view(store):
    base = editorial_view(store)
    now = int(store.clock())
    today = datetime.fromtimestamp(now, CAIRO).date()
    end = int(datetime.combine(today + timedelta(days=7), time.min, CAIRO).timestamp())
    tomorrow = int(datetime.combine(today + timedelta(days=1), time.min, CAIRO).timestamp())
    local = LocalCalendar(store).list(window=(now, end))
    details = []
    for row in local["items"]:
        if row["kind"] == "event" and row["end_ts"] > now and row["start_ts"] < end:
            when = datetime.fromtimestamp(row["start_ts"], CAIRO).strftime("%Y-%m-%d %H:%M")
            details.append({"ref": "local:" + row["id"], "kind": "event", "title": row["title"],
                            "when": when, "notes": row["notes"], "source": "OKAL",
                            "start_ts": row["start_ts"], "reminder": row["reminder_status"]})
        elif row["kind"] == "goal":
            details.append({"ref": "local:" + row["id"], "kind": "goal", "title": row["title"],
                            "when": row["target_date"] or "بدون تاريخ", "notes": row["notes"],
                            "source": "OKAL", "date_only": True})
    tasks = TaskPlanner(store).list()["items"]
    for row in tasks:
        if row["due_at"] is None or row["due_at"] < end:
            when = datetime.fromtimestamp(row["due_at"], CAIRO).strftime("%Y-%m-%d %H:%M") if row["due_at"] else "بدون موعد"
            details.append({"ref": "task:" + row["id"], "kind": "task", "title": row["title"],
                            "when": when, "notes": row["notes"], "source": "OKAL Tasks"})
    with store.connect() as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        events = list(db.execute(
            "SELECT provider,account_id,calendar_id,instance_id,event_id,title,start_ts,all_day FROM calendar_source_events WHERE cancelled=0 "
            "AND end_ts>? AND start_ts<? ORDER BY start_ts LIMIT 50", (now, end)
        )) if "calendar_source_events" in tables else []
        checkpoints = list(db.execute("SELECT last_success FROM calendar_google_sync")) if "calendar_google_sync" in tables else []
        errors = list(db.execute("SELECT last_error FROM calendar_google_attempts")) if "calendar_google_attempts" in tables else []
        task_check = db.execute("SELECT last_success FROM google_tasks_sync WHERE account_id='default'").fetchone() if "google_tasks_sync" in tables else None
        task_error = db.execute("SELECT last_error FROM google_tasks_attempts WHERE account_id='default'").fetchone() if "google_tasks_attempts" in tables else None
    for row in events:
        details.append({"ref": "calendar:" + ":".join(str(row[k]) for k in ("provider", "account_id", "calendar_id", "event_id", "instance_id")),
                        "kind": "event", "title": row["title"],
                        "when": datetime.fromtimestamp(row["start_ts"], CAIRO).strftime("%Y-%m-%d" if row["all_day"] else "%Y-%m-%d %H:%M"),
                        "date_only": bool(row["all_day"]), "notes": "نسخة محفوظة؛ راجع حالة تحديث المصدر.", "source": row["provider"],
                        "start_ts": row["start_ts"]})
    google_tasks = cached(store)
    for row in google_tasks["items"]:
        if row["scheduled_day"] is None or row["scheduled_day"] <= (today + timedelta(days=7)).isoformat():
            details.append({"ref": "google-task:" + row["list_id"] + ":" + row["task_id"],
                            "kind": "task", "title": row["title"], "when": row["scheduled_day"] or "بدون تاريخ",
                            "notes": "تاريخ فقط، مش موعد بساعة محددة.", "source": "Google Tasks", "date_only": True})
    for row in base["new_action_emails"] + base["new_info_emails"]:
        details.append({"ref": row["source_link"], "kind": "mail", "title": row["subject"],
                        "when": "بريد محفوظ", "notes": row["summary"], "source": "Gmail"})
    events_today = sorted((r for r in details if r["kind"] == "event" and r["start_ts"] < tomorrow), key=lambda r: r["start_ts"])
    goals = [r for r in details if r["kind"] == "goal"]
    points = []
    if base["mail_sync_stale"]:
        points.append("تحديث البريد غير مؤكد أو غير مكتمل؛ ممكن يكون فيه جديد مش ظاهر.")
    if events:
        points.append("مواعيد المصادر الخارجية نسخ محفوظة؛ تحديثها مش ضمان إنها كاملة أو حديثة.")
    if events_today:
        first = events_today[0]
        points.append(f"موعد اليوم أو الجاري: {_short(first['title'], 90)} · {first['when']} ({first['source']}).")
    else:
        upcoming = sorted((r for r in details if r["kind"] == "event"), key=lambda r: r["start_ts"])
        points.append(f"الموعد القادم المحفوظ: {_short(upcoming[0]['title'], 90)} · {upcoming[0]['when']}." if upcoming else "مفيش موعد قادم ظاهر في بيانات الأسبوع المحفوظة.")
    if base["today_tasks"] or base["overdue_tasks"]:
        points.append(f"مهام محلية اليوم: {len(base['today_tasks'])}؛ المتأخر الظاهر: {len(base['overdue_tasks'])}.")
    if goals:
        points.append(f"أهدافك المفتوحة الظاهرة: {len(goals)}. منها: {_short(goals[0]['title'], 80)} · {goals[0]['when']}.")
    selected = [row for link in base["evidence_links"] for row in details if row["kind"] == "mail" and row["ref"] == link]
    if selected:
        points.append("من البريد المحفوظ: " + _short(selected[0]["title"], 100) + ".")
    elif base["new_action_emails"]:
        points.append("بريد محتاج مراجعة: " + _short(base["new_action_emails"][0]["subject"], 100) + ".")
    if not goals and not base["today_tasks"] and not base["overdue_tasks"]:
        points.append("تقدر تضيف موعد أو هدف محلي؛ ترتيب يومك هيبدأ فقط لما تطلبه.")
    sources = {
        "local": "saved_on_device",
        "gmail": "unverified" if base["mail_sync_stale"] else "recent_checkpoint",
        "google_calendar": "recent_cache" if checkpoints and all(0 <= now-r[0] <= 10800 for r in checkpoints) and not any(r[0] for r in errors) else "unverified_cache",
        "google_tasks": "recent_cache" if task_check and 0 <= now-task_check[0] <= 10800 and not (task_error and task_error[0]) else "unverified_cache",
    }
    base.update(brief_points=points[:5], details=details[:50], sources=sources,
                details_limited=len(details)>50 or local["limit_reached"] or len(tasks)>=100 or len(events)>=50 or len(google_tasks["items"])>=100,
                calendar_note="تقويم OKAL محلي مستقل؛ مصادر Google اختيارية وتظهر كنسخ محفوظة.",
                data_source="owner_local_commitments_and_saved_sources",
                local_calendar_available=True, planning_requested=False, voice_ready=True, voice_enabled=False)
    base["spoken_text"] = base["greeting"] + " " + " ".join(points[:5])
    base["body"] = base["spoken_text"]
    return base
