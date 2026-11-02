# Google Tasks read-only source — separate OAuth and local cache

Issue #80; no changes to existing Gmail or Calendar tokens/scopes.

## Key Google API constraint

Google Tasks `due` is **a date on the calendar, not a clock time or a
deadline**; the Google Tasks API discards the time portion. OKAL stores
`scheduled_day=YYYY-MM-DD`, `has_exact_due_time=false`,
`is_deadline=false` and never creates a busy slot or auto-places the task
at midnight. Google Task items are independent records; *do not duplicate*
them into `local_tasks`.

Official docs: [Google Tasks resource](https://developers.google.com/workspace/tasks/reference/rest/v1/tasks)
and [Tasks.list method](https://developers.google.com/workspace/tasks/reference/rest/v1/tasks/list)

## Operator / owner connection

Google Tasks needs an **independent OAuth consent** for
`https://www.googleapis.com/auth/tasks.readonly`. The existing Gmail
Desktop OAuth CLIENT ID/secret can be reused **only as client identity**:
no Gmail/Calendar token reuse, scope escalation or mutation. The OKAL
Integrations tile opens a separate one-use PKCE flow, stores its own
owner-only token at `state/tasks/google/default.json`, and kicks off
the first sync after successful OAuth callback. Google Tasks API access
may require enabling Google Tasks API for that OAuth project; incomplete
OAuth setup must never appear as connected.

CLI from production checkout after approval/deployment:

```bash
export OKAL_CORE_PYTHON="$HOME/Projects/okal/.venv-okal-core/bin/python"
bash scripts/run-okal-core.sh tasks-google status
bash scripts/run-okal-core.sh tasks-google sync
bash scripts/run-okal-core.sh tasks-google list --limit 50
```

The `tasks-google list` CLI includes private titles; don't share raw output.
The `status` and `sync` CLI print aggregate counts only. `sync` is
operator-initiated, NOT automatically triggered on dashboard GET or by
Ollama. Explicit initial OAuth callback may start a provider read in the
FastAPI background task; no writes to Google. A periodic refresh policy
requires separate acceptance.

## Technical model

Bounded full snapshot: max 20 task lists, 4 list pages, 6 × 100 tasks
per list. Read all lists/pages and validate identifiers, statuses and
dates **before** one SQLite transaction replaces the owner's old cache.
Cancelled/deleted tasks don't survive the fresh snapshot. Failed page,
duplicated IDs or invalid status abort without deleting the old cache.
Historical completion remains Google-owned. Owner-visible cached GET
returns active tasks and date-only metadata; it never calls Google.
No new calendar conflict calculations, deadline conversion or time blocks.

Privacy: local-only API, same-origin OAuth initiation and callback state,
no browser tokens/localStorage, strict CSP for self-hosted UI JS, all
user-authored titles rendered via text nodes, status-only unauthenticated
information limited to explicit local auto-unlock mode.

## Tests and acceptance

```bash
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests -p 'test_google_tasks.py' -v
node --test apps/core/tests/test_inbox_status.cjs
```

Run full GitHub CI (Python 3.12 and 3.14 plus JS, governance, Markdown).
On owner Omarchy with private SQLite backup, explicitly approve Tasks-only
Google consent and verify cached date-only items match Google Tasks on
Nov 2–3, and that no fake 00:00 timed blocks appear. Verify reload shows
data without network provider GET and Gmail/Calendar OAuth remains working.
Pending real owner signoff, do not assert live Tasks synced.
