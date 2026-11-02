"""Read-only unified agenda and cautious scheduling hints from local evidence.

Never contacts a calendar provider, calls an LLM, estimates task duration,
grants permissions, or treats a candidate slot as verified free time.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .calendar_core import CalendarCore
from .task_planner import TaskPlanner

CAIRO = ZoneInfo("Africa/Cairo")
MAX_CALENDAR_EVENTS = 200
MAX_LOCAL_TASKS = 100
MAX_CONFLICTS = 40
MAX_SLOTS = 8
SYNC_STALE_SECONDS = 7200


def _merge(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return merged


def _calendar_items(events):
    items = []
    for event in events:
        items.append({
            "kind": "calendar_event",
            "id": [event["provider"], event["account_id"], event["calendar_id"],
                   event["event_id"], event["instance_id"]],
            "provider": event["provider"],
            "title": event["title"],
            "start_ts": event["start_ts"],
            "end_ts": event["end_ts"],
            "busy": bool(event["busy"]),
            "all_day": bool(event["all_day"]),
            "source": "provider_cache",
        })
    return items


def _task_items(tasks, window_start, window_end):
    timed, unscheduled, overdue = [], 0, 0
    for task in tasks:
        due = task["due_at"]
        if due is None:
            unscheduled += 1
        elif due < window_start:
            overdue += 1
        elif due < window_end:
            timed.append({
                "kind": "local_task",
                "id": task["id"],
                "title": task["title"],
                "start_ts": due,
                "end_ts": None,  # A deadline is a point, NOT a busy interval.
                "source": "owner_confirmed_local_task",
            })
    return timed, unscheduled, overdue


def _conflicts(calendar_items, task_items):
    """Return bounded *possible* overlaps, not adjudicated scheduling errors."""
    busy = sorted(
        (item for item in calendar_items if item["busy"]),
        key=lambda row: (row["start_ts"], row["end_ts"], row["id"])
    )
    conflicts = []
    truncated = False
    for index, left in enumerate(busy):
        for right in busy[index + 1:]:
            if right["start_ts"] >= left["end_ts"]:
                break
            if len(conflicts) >= MAX_CONFLICTS:
                truncated = True
                break
            conflicts.append({
                "kind": "potential_event_overlap",
                "first": left["id"], "second": right["id"],
                "start_ts": max(left["start_ts"], right["start_ts"]),
                "end_ts": min(left["end_ts"], right["end_ts"]),
            })
        if truncated:
            break
    if not truncated:
        for task in task_items:
            for event in busy:
                if event["start_ts"] <= task["start_ts"] < event["end_ts"]:
                    if len(conflicts) >= MAX_CONFLICTS:
                        truncated = True
                        break
                    conflicts.append({
                        "kind": "deadline_during_busy_event",
                        "task_id": task["id"], "event": event["id"],
                        "start_ts": task["start_ts"],
                    })
            if truncated:
                break
    return conflicts, truncated


def _candidate_slots(calendar_items, first_day, days, now):
    """Illustrative 30-minute windows in Cairo 09:00-18:00, never guarantees."""
    busy = _merge([
        (item["start_ts"], item["end_ts"])
        for item in calendar_items if item["busy"]
    ])
    slots = []
    for offset in range(days):
        date = first_day + timedelta(days=offset)
        start = int(datetime.combine(date, time(9), CAIRO).timestamp())
        end = int(datetime.combine(date, time(18), CAIRO).timestamp())
        # Round to a local half hour; Cairo's UTC offset is whole hours.
        candidate = max(start, ((now + 1799) // 1800) * 1800)
        day_found = 0
        while candidate + 1800 <= end and day_found < 2:
            if all(candidate + 1800 <= begin or candidate >= stop
                   for begin, stop in busy):
                slots.append({
                    "start_ts": candidate, "end_ts": candidate + 1800,
                    "status": "candidate_not_verified",
                })
                day_found += 1
                if len(slots) >= MAX_SLOTS:
                    return slots
            candidate += 1800
    return slots


def unified_plan(store, days=7):
    """Build a bounded read-only day/week plan from a private SQLite snapshot."""
    if type(days) is not int or days not in (1, 7):
        raise ValueError("invalid_unified_plan_window")
    now = int(store.clock())
    today = datetime.fromtimestamp(now, CAIRO).date()
    start = int(datetime.combine(today, time.min, CAIRO).timestamp())
    end = int(datetime.combine(today + timedelta(days=days), time.min, CAIRO).timestamp())

    calendar = CalendarCore(store).agenda(days=days, limit=MAX_CALENDAR_EVENTS)
    task_data = TaskPlanner(store).list("open", MAX_LOCAL_TASKS)
    calendar_items = _calendar_items(calendar["items"])
    task_items, unscheduled, overdue = _task_items(task_data["items"], start, end)
    items = sorted(
        calendar_items + task_items,
        key=lambda item: (item["start_ts"], item["kind"], str(item["id"])),
    )
    conflicts, conflicts_truncated = _conflicts(calendar_items, task_items)
    calendar_limited = calendar["count"] >= MAX_CALENDAR_EVENTS
    tasks_limited = task_data["total_in_sample"] >= MAX_LOCAL_TASKS

    last_sync = calendar["cache_last_success"]
    age = max(0, now - last_sync) if last_sync is not None else None
    fresh = age is not None and age <= SYNC_STALE_SECONDS
    warnings = ["availability_not_guaranteed_from_cached_sources"]
    if last_sync is None:
        warnings.append("no_successful_google_calendar_sync")
    elif not fresh:
        warnings.append("google_calendar_cache_stale")
    if calendar_limited:
        warnings.append("calendar_event_limit_reached")
    if tasks_limited:
        warnings.append("local_task_limit_reached")
    if conflicts_truncated:
        warnings.append("conflict_limit_reached")

    return {
        "timezone": "Africa/Cairo",
        "date": today.isoformat(),
        "window_days": days,
        "items": items,
        "counts": {
            "calendar_events": len(calendar_items),
            "scheduled_local_tasks": len(task_items),
            "unscheduled_local_tasks_in_sample": unscheduled,
            "overdue_local_tasks_in_sample": overdue,
            "potential_conflicts": len(conflicts),
        },
        "conflicts": conflicts,
        "candidate_slots": (
            _candidate_slots(calendar_items, today, days, now)
            if fresh and not calendar_limited else []
        ),
        "coverage": {
            "provider_status": calendar["provider_status"],
            "last_sync": last_sync,
            "sync_age_seconds": age,
            "recent_successful_sync": fresh,
            "calendar_limit_reached": calendar_limited,
            "task_limit_reached": tasks_limited,
            "conflicts_truncated": conflicts_truncated,
            "availability_verified": False,
            "warnings": warnings,
        },
        "external_reads": False,
        "external_writes": False,
        "ai_actions_executed": False,
    }
