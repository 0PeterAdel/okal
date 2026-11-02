"""Review-only, conservative work-block suggestions from cached local data.

A local task deadline is not an estimate of task duration. Proposals use a
hypothetical 30-minute block inside illustrative Cairo work hours; never
modify local tasks or Google Calendar and never guarantee actual availability.
"""
from datetime import datetime, time, timedelta

from .calendar_planning import CAIRO, MAX_LOCAL_TASKS, unified_plan

MAX_TASK_PROPOSALS = 12
BLOCK_SECONDS = 1800


def propose_task_blocks(store, days=7):
    if type(days) is not int or days not in (1, 7):
        raise ValueError("invalid_task_proposal_window")
    view = unified_plan(store, days=days)
    coverage = view["coverage"]
    safe_to_suggest = (
        coverage["recent_successful_sync"]
        and not coverage["calendar_limit_reached"]
        and not coverage["task_limit_reached"]
    )
    now = int(store.clock())
    tasks = sorted(
        (x for x in view["items"]
         if x["kind"] == "local_task" and x["start_ts"] > now),
        key=lambda x: (x["start_ts"], x["id"]),
    )
    if not safe_to_suggest:
        return {
            "status": "blocked_by_missing_or_limited_calendar_evidence",
            "proposals": [], "unplaced_tasks": 0,
            "assumed_block_minutes": 30, "assumed_work_hours": "09:00-18:00",
            "all_suggestions_require_owner_review": True,
            "coverage": coverage, "external_reads": False, "external_writes": False,
        }

    busy = [
        (event["start_ts"], event["end_ts"])
        for event in view["items"]
        if event["kind"] == "calendar_event" and event["busy"]
    ]
    slots = []
    today = datetime.fromtimestamp(now, CAIRO).date()
    for day in range(days):
        date = today + timedelta(days=day)
        start = int(datetime.combine(date, time(9), CAIRO).timestamp())
        end = int(datetime.combine(date, time(18), CAIRO).timestamp())
        instant = start
        while instant + BLOCK_SECONDS <= end:
            if instant >= now and all(
                instant + BLOCK_SECONDS <= begin or instant >= finish
                for begin, finish in busy
            ):
                slots.append((instant, instant + BLOCK_SECONDS))
            instant += BLOCK_SECONDS

    output = []
    unplaced = 0
    for task in tasks[:MAX_TASK_PROPOSALS]:
        due = task["start_ts"]
        chosen = next(
            ((start, end) for start, end in slots if end <= due), None
        )
        if chosen is None:
            unplaced += 1
            continue
        slots.remove(chosen)  # Prevent overlapping proposals in this plan.
        output.append({
            "task_id": task["id"], "title": task["title"],
            "due_at": due, "start_ts": chosen[0], "end_ts": chosen[1],
            "status": "illustrative_owner_review_only",
            "duration_is_assumed": True,
            "basis": "confirmed_task_deadline_and_cached_google_busy_intervals",
        })
    return {
        "status": "tentative_local_plan",
        "proposals": output,
        "unplaced_tasks": unplaced,
        "task_proposal_limit_reached": len(tasks) > MAX_TASK_PROPOSALS,
        "assumed_block_minutes": 30, "assumed_work_hours": "09:00-18:00",
        "all_suggestions_require_owner_review": True,
        "availability_verified": False,
        "coverage": coverage, "external_reads": False, "external_writes": False,
    }
