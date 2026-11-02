# Calendar Sync — Partial Failure Recovery (read-only Google)

Owner regression: a Google Calendar `sync --all` returned
`invalid_calendar_event_interval` after the CLI aborted at the first
failing calendar; a subsequent shell JSON parser failed because there was no
JSON on stdout. This is separate from the missing-source coverage PR #72.

## Scope and guarantees

- A failed calendar does **not** stop other calendars in `sync --all`.
  The failed calendar's sync token does not advance; no provider event is
  silently discarded and full-snapshot cleanup does not execute for it.
- The per-calendar `calendar_google_attempts.last_error` records stable,
  allowlisted error codes. Returned `failures` contain **only the ordinal**
  `calendar_number` from the current list, never private calendar names,
  event IDs, titles, credentials or provider HTTP responses.
- `google_calendar_event_nonpositive_interval` means end <= start;
  `google_calendar_event_overlong_interval` means an interval longer
  than the **currently supported** 366 days. These are validation details,
  **not** proof that Google Calendar itself contains invalid data. A
  legitimate longer event might require a subsequent explicit model redesign.
- Each successful calendar still uses the existing read-only Google Calendar
  API permissions, SQLite cache ingestion and checkpointing. No Gmail code,
  OAuth scopes, auto-modification or write APIs changed.
- `sync --all` returns JSON on stdout even with per-calendar failures:
  `sync_status=partial`, per-calendar safe errors, `successful_calendars`,
  `failed_calendars`, `unreadable_calendars`. Exit code **2** indicates
  partial coverage. Exit **0** indicates all eligible listed calendars
  succeeded. Fatal account/listing failures still exit **1** without a
  guaranteed JSON payload; callers must check both status and stdout.
- Existing single-calendar sync keeps exit **1** and a redacted error on
  failure; unchanged behavior for existing shell scripts.

## Read-only coverage audit (new command)

The `calendar audit --days 7` operator command makes a fresh, bounded
Google Events.list query **without syncToken** over the next seven Cairo dates
(`timeMin`/`timeMax`). It does not modify local event rows, sync checkpoints,
or any Google Calendar events. It may refresh the existing local OAuth access
token when necessary. The result is ordinal-based: per calendar, whether
it is the primary calendar, whether it has a saved sync checkpoint,
Google's count of visible Events in the date window, the SQLite cached
count, and aggregate counts by duration shape. **No calendar IDs, names,
event titles, URLs or tokens appear in the audit response.**

Use it *before* trying another sync if a source is missing:

```bash
cd "$HOME/Projects/okal-production"
export OKAL_CORE_PYTHON="$HOME/Projects/okal/.venv-okal-core/bin/python"
# When testing unmerged PR #73, execute the next line from its detached
# review checkout rather than using old production code:
bash scripts/run-okal-core.sh calendar audit --account default --days 7
```

Read `calendar_number` only as a transient index in Google's current list,
not an immutable identity. `primary:true` helps distinguish the primary
calendar without leaking its ID. `zero_duration_timed` versus
`reversed_interval` helps select the *next safe* targeted change.
Google can have non-default event types or account calendars that do not
match the browser session: the audit cannot prove the Firefox account
identity or Google Tasks visibility. If an audit is incomplete, each
calendar's `audit_status` indicates why without exposing provider errors.

Audit limits: 20 calendars, eight pages per calendar, 250 events per page,
1–14 days. The audit is explicit owner action, not a background worker or
dashboard GET, and is not a full historical reconciliation.

## Owner live diagnostic (do not share private full JSON)

Review the Draft PR and tests first. Use a temporary detached git worktree
pointing to the PR head; do not replace the running production executable.
Review code is compatible with the existing state, but **sync writes a cache
and its own cursors in local SQLite**. Back up SQLite before running.
Keep the existing OKAL service on; if it is synchronizing at the same instant,
the lock correctly fails and reports a safe error rather than corrupting state.

Example operator command, run in the PR review worktree:

```bash
export OKAL_CORE_PYTHON="$HOME/Projects/okal/.venv-okal-core/bin/python"
state="$HOME/.local/state/okal-core"
report=$(mktemp "$HOME/okal-calendar-sync-report-XXXXXXXX.json")
if bash scripts/run-okal-core.sh --state-dir "$state" calendar sync --all > "$report"; then
  rc=0
else
  rc=$?
fi
python3 - "$report" "$rc" <<'PY'
import json,sys
from pathlib import Path
path=Path(sys.argv[1])
try:
    data=json.loads(path.read_text())
except json.JSONDecodeError:
    print("No provider JSON; inspect redacted CLI error above; exit:",sys.argv[2])
else:
    rows=data.get("results",[])
    print("exit:",sys.argv[2],"status:",data.get("sync_status"))
    print("successful:",data.get("successful_calendars"))
    print("failed:",data.get("failed_calendars"))
    print("unreadable:",data.get("unreadable_calendars"))
    print("received:",sum(x.get("received",0) for x in rows))
    print("locally written:",sum(x.get("written",0) for x in rows))
    print("failure codes:",[x["error_code"] for x in data.get("failures",[])])
PY
# Private report contains local calendar identifiers: do not paste the file.
```

Afterward compare read-only SQLite counts for the owner's Nov 2 and Nov 3
real calendar events. Missing events in a *failing* calendar remain an open
issue; this fix does not silently invent or recover them. Only owner evidence
can determine whether an overlong interval is valid, an out-of-range cache
invariant, a zero-length provider event, or an account/calendar mismatch.

## Tests

```bash
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests -p test_calendar_cli.py -v
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests -p test_calendar_google.py -v
node --test apps/core/tests/test_inbox_status.cjs
```

Run full GitHub Python 3.12 and 3.14, Governance and Markdown before a merge.
The owner tests the actual provider connection on Omarchy after backing up
private SQLite. A passing CI run cannot attest live Calendar event coverage.
