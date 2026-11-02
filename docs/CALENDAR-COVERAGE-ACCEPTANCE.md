# Calendar cache-coverage gate and owner acceptance

Task: [#71](https://github.com/0PeterAdel/okal/issues/71). The follow-up
Google Tasks connector remains separate: [#70](https://github.com/0PeterAdel/okal/issues/70).

## What changed

- OKAL's read-only unified-plan endpoint counts **saved** Google Calendar
  checkpoints, recent/stale checkpoints, recorded sync errors, and Google
  provider events in the current view and complete local cache. This is
  aggregate metadata only: no private event title, calendar ID, account alias,
  OAuth token, cursor, or email is disclosed by `coverage.source_evidence`.
- Recent success for *one* calendar is explicitly distinguished from proof that
  every desired account/calendar (and Google Tasks) is represented. No such
  authoritative inventory / owner's coverage confirmation exists today.
- Candidate free-time proposals are **disabled** until such confirmation
  exists. A recent successful sync and zero cached events cannot justify
  telling the owner they are free. Conflicts are still *potential*, derived
  only from cached events, and may be missing.
- The Arabic dashboard labels unverified coverage, missing cached events,
  sync failures and stale checkpoints without claiming Google Calendar is empty.

This PR does not fetch new events, change OAuth, grant additional scopes, sync
Google Tasks, create/write a calendar event, or modify a running service.

## Real owner-device diagnosis (safe, no titles in shared output)

On the owner's Omarchy system, the service was running from
`~/Projects/okal-production`, at merged main `f17ce39`. Its first one-shot
`curl` immediately after restart failed while `systemctl is-active`
returned `active`; a later screenshot displayed the UI. Check the HTTP
readiness separately before assuming the service is down.

The owner can check the **current** state with a sanitized locally computed
summary without exposing private values:

```bash
cd ~/Projects/okal-production
curl -fsS http://127.0.0.1:8766/api/v1/calendar/plan?days=7 |
python3 -c 'import json,sys; d=json.load(sys.stdin); c=d["coverage"]; print("calendar events in view:",d["counts"]["calendar_events"]); print("candidate slots:",len(d["candidate_slots"])); print("coverage summary:",json.dumps(c.get("source_evidence",{}),indent=2))'
```

If the owner finds missing real Google Calendar *events*, check the connected
OAuth account privately in Google and run the existing operator-only
`calendar sync --all` from the production checkout; this uses only read-only
Google scopes and updates local SQLite. Keep a private SQLite backup and
redact any IDs/credentials before sharing results. A mismatched signed-in
Google account, unsynced calendar, provider error, or unrecognized account
needs owner-local evidence before a targeted connector fix.

Note: Google Calendar's UI also contains **Google Tasks**, which are not
synced by Calendar v3 `events.list`. Google Tasks API is a separate explicit
permission and provider. A conventional calendar event on November 3 is
also missing: that cannot be fixed by adding Google Tasks alone.

## Verification

```bash
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests -p test_calendar_planning.py -v
node --test apps/core/tests/test_inbox_status.cjs
bash scripts/validate-governance.sh
```

Acceptance is blocked until real owner-device inspection shows real provider
calendar events in the 7-day unified view. This PR removes a false free-time
claim; it is **not** proof that all events synced. Preserve mail/calendar
credentials and the production Core state. Only the owner may record the human
Solo Maintainer self-review and decide to merge/deploy after checks.
