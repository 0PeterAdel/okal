# OKAL Unified Calendar — read-only first slice

Task: [#66](https://github.com/0PeterAdel/okal/issues/66)

## Delivered in this slice

1. **Unified day/week agenda** reads Google's cached event projection and the
   owner's confirmed local tasks into one Cairo-time view. Events preserve
   provider/account/calendar/occurrence identity; task deadlines are points,
   **not** busy blocks. Completed tasks are not shown. Unscheduled/overdue task
   sample counts remain visible without assigning an invented time.
2. **Potential conflict analysis** distinguishes overlapping busy events from
   deadlines that fall inside a busy event. Transparent/cancelled events do not
   block time. Repeated/duplicated external calendars can create apparent
   overlaps: every result is labelled *potential*, not a definite error.
   Candidate 30-minute slots are illustrative, calculated in a **placeholder
   09:00–18:00 Africa/Cairo window**. These are not personalized work hours or
   guaranteed free time; no slot is emitted without a recent successful saved
   Google sync or when the event response hits its limit.
3. **Dashboard** has a day/week switch, source-aware list, potential conflicts,
   candidate slots, and a warning on missing/stale/limited sync. The browser
   inserts untrusted event titles using `textContent` only. No provider URLs,
   external scripts, fonts, libraries, or browser persistence are introduced.

## Endpoint and authority

`GET /api/v1/calendar/plan?days=1` or `?days=7` is a loopback-only
read API. With protected browsing enabled, it requires the existing authenticated
read key/session. Its entire response derives from private SQLite; **GET never
contacts Google, runs Ollama, sends notifications, or writes an external event**.
The API exposes source metadata, event names and local task names to the
authenticated localhost reader only. Never paste private responses into issues.

The pre-existing `/api/v1/calendar/agenda`, `/availability`, `/planner`
and task write endpoints stay unchanged. Google Calendar OAuth remains
read-only; Gmail permissions and operations are untouched.

## Known limits

- Google events are capped at 200 and local open tasks at 100. The plan
  explicitly warns at the limit; resulting counts and detected conflicts may be
  incomplete. Conflict details are capped at 40, slot proposals at eight.
- Cached provider sync age over two hours is treated as stale for candidate
  slots. Even a recent sync does **not** prove all calendars/accounts are synced.
- Candidate slots ignore tasks without durations and any calendars not locally
  synced, so they must never trigger an automated booking or an external action.
- Current provider-agnostic calendar projection is read-only. No Google
  create/update/delete, no conflict resolution, no AI optimization, no auto
  invitations, and no Microsoft/Apple connector are included.

## Verification and rollout

Run existing Governance, Markdown, Python 3.12/3.14 and JS tests; in particular:

```bash
PYTHONPATH=apps/core/src python -m unittest apps.core.tests.test_calendar_planning -v
node --test apps/core/tests/test_inbox_status.cjs
bash scripts/validate-governance.sh
```

**Owner acceptance:** first inspect the PR and passing exact-head checks.
Preserve the running `~/Projects/okal-production` checkout and private state;
do not deploy a review branch into the production Core. Test on a separate
local checkout/state or after an approved deployment with SQLite backup.
In Firefox, open the Calendar tab, compare at least two real meetings and one
local deadline with Google Calendar, switch day/week, check Arabic/English RTL,
keyboard focus and 375px/768px/desktop widths, and simulate stale sync. Check
that no external Google write occurs.

This PR must remain Draft until code/CI checks, a genuine owner Solo Maintainer
review, and local acceptance are recorded. No PR merge or production deployment
is implied by committing the implementation.
