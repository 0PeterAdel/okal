# Owner-local calendar and concise briefing

Implements issue #109 and the owner's November 4 direction. This describes code
capability, not verified deployment on the owner's laptop.

## Contract

The Calendar panel contains an owner-local form for appointments and goals.
Appointments require explicit start/end instants. The form uses the device's
local timezone and sends offset-bearing UTC; display uses Africa/Cairo. Goals
may have a target date and do not occupy busy time. No model or Google account
is required. Notes/titles are plain text. Complete/cancel preserves the record;
there is no permanent-delete endpoint or automatic external write.

SQLite `local_commitments` is created transactionally on the first write (or
reminder-worker startup). It lives in the existing private state database.
GET `/api/v1/calendar/local` lists at most 500 open records. POST `/save` under
that path requires id (32 hex), revision (0 for create), kind (event/goal), title,
notes, start, end, target_date and reminder_minutes, with null for unused values.
POST `/transition` requires id, revision and status (done/cancelled). Creates use
a payload digest for retry safety; edits/transitions use revision comparison.
A conflicting retry returns 409 rather than overwriting or duplicating data.
The existing loopback/Host/origin/JSON/session boundaries also protect these
routes. A read-only bearer key does not authorize writes. The save body is capped
at 16 KB to accommodate Arabic notes; existing routes retain their original caps.

The existing reminder worker claims due event reminders in SQLite before calling
the local notifier. No repeated attempt after failure or ambiguous interruption;
reminders over 15 minutes late are marked missed. Editing text does not rearm a
reminder. Editing its start/lead explicitly reschedules it. Notifications require
the running Core process, an active desktop session and notify-send. The code
cannot wake a powered-off laptop and does not promise exactly-once delivery.

## Brief and refresh

Dashboard and `bash scripts/run-okal-core.sh morning` share up to five concise
points, expandable saved details and `spoken_text`. Local appointments join the
unified agenda and request-only availability planner. Goals remain date-only.
The brief includes saved provider events and Google Tasks with cache provenance;
provider caches never prove live completeness. Gmail keeps the existing failed /
pending / stale warning. Existing validated Ollama editorial cache may select a
mail highlight; GET never invokes the model. Voice remains disabled.

The overview/inbox re-read local data every 90 seconds while visible and idle,
on return to the page, on explicit refresh and after local changes. This does
not call Google or Ollama and does not replace an open mail review/Trash dialog.
Background Gmail/provider sync stays with the existing bounded workers. The
existing once-per-Cairo-day login notification uses the same brief.

Details are a bounded seven-day appointment view plus open goals/tasks and saved
mail highlights. Truncation is disclosed. This is an expandable detail view, not
yet conversational natural-language follow-up or appointment extraction. Goal
reminders, recurring local meetings, reopen/archive UI and voice remain future
work. Local event reminders are implemented; goals never invent clock times.

## Validation and owner acceptance

Automated tests cover persistence, idempotency, concurrent stale edits,
notification failure/restart, cancellation, missed reminders, stale callback
protection, date-only goals, local busy intervals, read-only rendering, Unicode
payloads, origin boundaries and browser form serialization/text rendering.
The cloud browser could not reach the local preview server (connection refused),
so visual browser acceptance remains unverified in this environment.

After updating the reviewed main and restarting okal-core.service:

1. Add a clearly labelled test appointment and a date-only goal in Calendar.
2. Reload; verify both persist, and only the appointment occupies agenda time.
3. Expand the daily details; check source/time and the stale-mail warning.
4. Edit the appointment, then complete the fixtures. Verify they leave open lists.
5. Test a near-future reminder in an active desktop session if notifications are
   desired. Confirm no repeated alert after restarting Core.

For `authorization_required`, use the existing Gmail connect/reconnect control
on the owner's local dashboard, then verify sync status. Preserve the state DB,
OAuth files and history cursor; do not delete them to force a fresh sync. No
code-only test proves that the owner's Gmail authorization has recovered.

Before upgrading, stop Core and back up the private state directory locally.
Rollback to the prior reviewed code preserves this additive table; older code
ignores local commitments, so its brief/reminders will not include them. Restore
new code to regain access. Do not publish private backups or command output.
