# OKAL Plan My Day — local review-first time blocking

Scope issue: [#78](https://github.com/0PeterAdel/okal/issues/78).

## Purpose

Turn the working Calendar Day Focus into an *actionable* daily planning
tool, based on explicit owner choices, not speculative LLM-generated time
estimates. A tentative plan is **not** proof that a time slot is free when
some Google Calendar or Google Tasks sources are incomplete.

## First three capabilities

1. **Plan My Day:** choose one of the locally loaded next seven Cairo dates,
   select up to 12 open local tasks, provide an explicit 15–240 minute
   duration for every selected task, choose normal/high/low priority and a
   work window (one to twelve hours on quarter-hour boundaries). The UI
   pre-fills example hours 09:00–18:00 but these are **examples to review,
   not owner preferences**. No invented task duration, no LLM call.
2. **Constrained deterministic time blocking:** sorts selected tasks by
   owner-set priority and confirmed due time, and finds whole contiguous
   windows around cached busy events. Blocks never start in the past, extend
   beyond a task's due time, overlap each other, or overlap a locally known
   busy Calendar event. All-day busy intervals block their full range;
   zero-duration events are non-busy. Tasks that don't fit appear under
   `unplaced` with explicit explanations. Source coverage stays unverified;
   **all blocks are tentative**.
3. **Preview → owner confirm → local save:** the UI shows suggested times
   before exposing a separate **"I approve — save locally only"** action.
   A random one-use 10-minute ticket binds the preview input and current
   selected task/calendar evidence. At commit the server recomputes and
   rejects stale/changed inputs or a completed task. Approved blocks are
   saved in a *new private SQLite table* and can be revisited. Neither
   Google Calendar nor Gmail is contacted, no meeting is created, and
   task deadlines remain unchanged.

## Boundaries and limitations

- Optimizer is intentionally **deterministic**, not a claimed autonomous AI
  scheduling agent. There is no unseen model inference or paid API.
- It is a read of **existing cached** Google events and local tasks. Partial
  provider/account coverage is not solved here. Even saved plans are private
  owner-reviewed *intent*, not confirmed reservations or busy provider slots.
- There is no auto-replan or silently adjusted Google event/attendees.
  The current Calendar write OAuth remains read-only.
- Saved plans don't yet auto-update if an event changes after saving:
  owner must review again. No task editing or Google writes happen.
- JS uses text nodes for user and calendar labels; no HTML injection or
  browser localStorage. All calls are to existing protected same-origin
  `/api/v1/calendar/day-plan/...` endpoints.

## Quick testing

```bash
PYTHONPATH=apps/core/src python -m unittest discover \
  -s apps/core/tests -p test_day_planner.py -v
node --test apps/core/tests/test_inbox_status.cjs
bash scripts/validate-governance.sh
```

Before deployment back up production SQLite and keep `okal-core.service`
and OAuth credentials intact. After approved PR merge, fast-forward the
running production checkout, restart and wait for HTTP health. In Firefox:

1. Open the Calendar tab, choose today, add two local tasks if needed.
2. Check the tasks, select durations 30 and 60 minutes and review or
   explicitly edit the work-window inputs.
3. Preview; see two proposed blocks (or an explicit unplaced explanation)
   avoiding actual cached Google events. Verify "tentative" labels.
4. Click "I approve — save locally only" **once** and open "saved plans".
   Reopen after restart and check private plan persists.
5. Change a task or calendar event after preview and confirm: server must
   refuse the stale proposal, requiring a fresh preview.
6. Confirm Google Calendar shows **no new or modified events**, Gmail
   untouched, RTL/keyboard/mobile layout still usable.

Tests/CI are synthetic; owner live Firefox check is required before
calling daily planning accepted.
