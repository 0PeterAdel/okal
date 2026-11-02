# OKAL Calendar V2 — review-only scheduling and Gmail event drafts

Related task: [#68](https://github.com/0PeterAdel/okal/issues/68).
Depends on read-only Unified Calendar Draft PR
[#67](https://github.com/0PeterAdel/okal/pull/67).
Do not merge this stacked feature ahead of #67. After #67 is merged,
retarget and reconcile using normal (non-force) history, then rerun CI.

## What was implemented

1. `GET /api/v1/calendar/review-plan?days=1|7` proposes a hypothetical
   30-minute work block before each local, owner-confirmed task deadline.
   The proposal checks locally cached busy Google Calendar intervals,
   reserves each proposed block to prevent scheduling multiple tasks into
   the same period, never assigns a block after the deadline, and returns
   an unplaced count for tasks without a valid slot. It uses **illustrative
   09:00–18:00 Africa/Cairo hours**, not the owner's learned working schedule.
   Nothing is written to Google or to TaskPlanner.

2. `POST /api/v1/calendar/mail-proposal` is invoked ONLY after clicking
   **اقتراح موعد بالـ AI** in the original Gmail reader. The request is
   same-origin JSON, restricted to the existing privileged owner gesture,
   and bound to a message ID that OKAL has saved and can verify against
   native Gmail. The trusted local pinned Ollama model reads one source
   message and returns a possible event title plus a direct quote.
   The server checks that quote is a literal substring of the original
   message. **Only explicit timezone-aware ISO 8601 instants in that quote**
   may be copied into the resulting draft. A natural-language date without
   a complete time+offset is never silently converted to a specific date.
   Missing/truncated body, fabricated quotes or source-ID mismatch fail
   closed. No mail is sent or modified, and no event is created.

3. Dashboard Calendar task-block review and on-demand Gmail candidate review
   display the source, caveats and uncertainty as text, not executable HTML.
   Calendar connect permissions remain read-only.

## Operational boundaries

- The 30-minute block is an *assumed review placeholder*, not an estimate of
  task duration. Existing reminders and deadlines are unchanged.
- A recent Google checkpoint does not prove all calendars, external sources
  or bookings are present. At the 200-event/100-task source caps, or after
  a stale/missing sync, scheduling suggestions fail closed.
- The first candidate ignores times in non-ISO prose (e.g., `next Tuesday`);
  the owner must verify those manually. If there is one ISO instant, no
  end time is invented. If two are in reverse order or ambiguous, no times
  are promoted.
- No reusable persisted email event draft, provider write approval token,
  autopilot permission, or Google Calendar `events.insert` operation exists.
  Any future create/update/delete functionality requires a separate
  security-reviewed PR and explicit Google OAuth scope opt-in.
- The source Gmail body is sent only to the configured **local** Ollama model,
  with the same existing digest/local-only verification as Gmail drafts.
  No third-party model, remote API, token in browser, or automatic pull.

## Tests

```bash
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests -p 'test_calendar_*proposals.py' -v
node --test apps/core/tests/test_inbox_status.cjs
bash scripts/validate-governance.sh
```

Review all exact-head Python 3.12/3.14, JavaScript, Governance and
Markdown checks. Then test in a trusted owner Firefox session using one
noncritical Gmail invitation, one local task, and a real busy Google
meeting. Confirm that the UI never claims the candidate was created.
Never share real subjects, mail bodies, tokens or private SQLite data.

Do not deploy a stacked Draft PR into `~/Projects/okal-production`
before owner review, an out-of-tree SQLite backup, and an approved merge.
