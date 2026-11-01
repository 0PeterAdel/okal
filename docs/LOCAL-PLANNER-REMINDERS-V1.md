# OKAL Local Planner V1 — SQLite tasks, Gmail and desktop reminders

This is a **stacked Draft** implementation on top of Mail Agent PR #49.
No Calendar OAuth, no network calendar integration and no paid API.

## Owner workflow

Open the local OKAL Dashboard at http://127.0.0.1:8766 and use **مهامي
ومواعيدي**.

- Create a manual task with title, optional notes, optional explicit
  date/time and optional reminder lead time.
- All dates typed into the dashboard are converted from the browser's local
  timezone into a timezone-aware UTC ISO timestamp before being saved. The
  agenda and reminders are displayed for Africa/Cairo. Check the device's
  timezone if you are outside Egypt; no date/time is inferred from email/AI.
- Click **Done**, **Edit**, **Dismiss**, or open the history list to **Reopen**
  a finished/dismissed task. Edits are owner actions only.
- A Gmail message can be converted to a task from the original message viewer,
  with optional owner-entered due date and local reminder. Duplicate conversion
  of the same source email returns the existing task ID; never clones tasks.
- The weekly local overview shows **today**, **overdue**, **upcoming** and
  **unscheduled** counts. The morning brief continues to surface explicitly
  approved tasks, not invented events.

## Reminders

Reminder offsets: at due time; 5, 15 or 60 minutes before; or 24 hours
before. Local reminders are opt-in per task, recorded in private SQLite table
`task_reminders`. The Core user service runs a thread that polls the private
database around every 30 seconds, even when Gmail isn't connected. It invokes
`notify-send` directly (no shell) if installed and if a Linux notification
session is available. No cloud notifications, no external calendar writes.

The worker transactionally claims an event before invoking `notify-send`.
It **never automatically retries** a possibly delivered notification after
a crash. Very old reminders (>15 minutes past their scheduled fire time) are
marked missed, not surfaced late as urgent. When done/dismissed, an unsent
reminder is cancelled. Reopening a task never silently reschedules an expired
reminder; edit the task and opt in again. Notification delivery can fail
when desktop D-Bus is unavailable; the UI then shows the failure rather than
claiming a notification was delivered.

No calendar or task information leaves the local machine.

## CLI

```bash
cd /home/okal/Projects/okal

bash scripts/run-okal-core.sh tasks agenda

bash scripts/run-okal-core.sh tasks add \
  --title "راجع نتائج المشروع" \
  --due "2026-11-03T15:30:00+02:00" \
  --remind-minutes 15

bash scripts/run-okal-core.sh tasks list
bash scripts/run-okal-core.sh tasks done TASK_ID
bash scripts/run-okal-core.sh tasks reopen TASK_ID

bash scripts/run-okal-core.sh tasks from-mail GMAIL_MESSAGE_ID \
  --approve --due "2026-11-04T12:00:00+02:00" \
  --remind-minutes 60
```

`--due` must include a timezone offset. CLI preview of from-mail without
`--approve` doesn't write anything.

## Review boundaries and acceptance

- SQLite content persists across service restart; there is no DB reset.
- All browser writes use JSON, are same-origin and loopback-only, and are
  rejected from nonlocal or cross-origin requests. Protected mode still
  requires the user's session.
- Browser GET endpoints only query SQLite and do not call Gmail or Ollama.
- No task automation sends Gmail messages or executes AI-suggested commands.
- The feature needs testing with one real owner-created task, Desktop
  notifications on Omarchy/Hyprland, and a restart.
- Source-code CI and mocked notification checks do not prove that a
  desktop notification will be displayed by the actual user's compositor.
- Stacked PRs remain Draft until local acceptance; don't merge a chain of
  unreviewed PRs based solely on CI.
