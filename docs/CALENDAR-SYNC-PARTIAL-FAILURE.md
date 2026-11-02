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

## Safe targeted current-window recovery (new command)

The real owner audit reported **four valid live Events on the primary calendar,
zero cached events, and no primary sync checkpoint**. The six other calendars
already had checkpoints and returned zero incremental changes; a separate
older **nonpositive interval** in the primary prevented a full initial sync.

To restore the required agenda immediately, the new explicit operator command
`calendar recover-window --calendar primary --days 7`:

- Resolves the authenticated account's primary calendar via CalendarList.
- Reads **only the requested 1–14-day Cairo window** using Google Events.list
  `singleEvents=true`, `timeMin`, `timeMax`, and `showDeleted=false`.
  This does not use a sync token; these date filters are **not allowed with
  syncToken** in Google's incremental-sync protocol.
- Downloads all bounded pages and validates every returned event using the
  same strict core model **before** the first SQLite cache insertion. If a
  page or event is invalid, fails closed and does not apply partial results.
- Saves valid events idempotently into the same private SQLite projection used
  by `/api/v1/calendar/plan`. It does NOT create/update sync checkpoints,
  delete events omitted from the window, or claim a historical full sync.
  The preexisting full-sync validation failure remains separately unresolved.
- Requires the already-granted read-only Google OAuth scopes; does not modify
  provider calendars, Gmail, attendee invitations or OAuth permissions.
- Restricts outputs to aggregate `received`, `written`, `date`, `days`,
  `source_coverage=selected_calendar_window_only`, and safety flags. Does
  not print event titles, calendar IDs or tokens.

**Owner real-device acceptance from a separate PR checkout (before merge):**

1. Ensure `okal-core.service` is active; retain original service binary.
2. Back up `~/.local/state/okal-core/core.sqlite3` with Python's SQLite
   `Connection.backup` (not a raw copy of a live WAL file).
3. Fetch PR #73, create a detached worktree and set
   `OKAL_CORE_PYTHON=$HOME/Projects/okal/.venv-okal-core/bin/python`.
4. Run `PYTHONPATH=apps/core/src "$OKAL_CORE_PYTHON" -m unittest discover
   -s apps/core/tests -p test_calendar_window_recovery.py -v`.
5. Run `bash scripts/run-okal-core.sh --state-dir
   "$HOME/.local/state/okal-core" calendar recover-window
   --account default --calendar primary --days 7` within the **review
   checkout** (not the old production checkout). This writes only the
   private local event projection; it never updates Google.
6. Verify success reports `received` approximately matching audit's four
   valid events, `source_coverage=selected_calendar_window_only`, and
   `sync_cursor_advanced=false`.
7. Refresh `http://127.0.0.1:8766/#calendar-section` in Firefox with
   Ctrl+Shift+R and compare event titles/times for **Nov 2 and Nov 3** with
   Google Calendar. Note any independent Google Tasks not yet supported.
8. Run `calendar audit --days 7` again to verify that **cached counts**
   match live counts for the primary in the window. A failed full historical
   sync must still appear as incomplete and must NOT be reported as fully
   connected. Review PR #72 separately for its coverage UI warnings.

Full historical sync, ambiguous zero-length event semantics, complete
cross-provider source coverage and Google Tasks integration are not solved
by this date-bounded repair. In particular, no new automation can treat the
window-only cache as verified free time.

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
