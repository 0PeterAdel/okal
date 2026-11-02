# OKAL Calendar Engine — local-first multi-provider plan

## Architecture decision

Keep OKAL's existing owner-only SQLite `Store`, Python Core API,
TaskPlanner and Ollama. Build a calendar domain, not a second standalone
Next.js/Convex/Redis/cloud app. Existing confirmed TaskPlanner deadlines
remain independent from remote calendar events to prevent duplication.

### Current milestone (Issue #58)

Implemented provider-neutral local event projection in
`apps/core/src/okal_core/calendar_core.py`. The events preserve
provider/account/calendar identity, recurring instance ID, all-day/busy
flags, explicit IANA timezone, UTC instants, and provider revision.
Bounded incremental batches are transactional and idempotent; stale
updates cannot replace fresh records; cancellation tombstones are
preserved. The first private loopback read APIs are:

- `GET /api/v1/calendar/agenda` — next 14 local calendar days from
  owner-only SQLite; never fetches a provider.
- `GET /api/v1/calendar/availability` — merged **known** busy blocks
  from cached events. An empty result does **not** prove availability
  until each provider has finished a complete sync.
- `assess_ai_action` — a pure rule evaluator; does not execute
  external actions or grant authorization.

**Not connected yet:** Google, Microsoft, iCloud, any public ICS,
live OAuth, provider sync, calendar event writes, AI inference,
reminder delivery, or mobile application. The API explicitly reports
`not_connected_in_foundation`; do not describe it as live.

## Providers and staged implementation

| Order | Provider | Authentication | Read/sync | Write |
| --- | --- | --- | --- | --- |
| P1 | Google Calendar | user OAuth Desktop + PKCE, separated from Gmail tokens | initial full event sync, paginated `nextSyncToken`; invalidate 410 and backfill | requested Calendar event scopes, conditional updates |
| P2 | Microsoft Outlook / Microsoft 365 | Microsoft Identity delegated OAuth | Graph calendarView + event delta per bounded date range | delegated `Calendars.ReadWrite` |
| P3 | Apple iCloud Calendar | CalDAV + app-specific password or supported Apple authorization | REPORT / URI / ETag reconciliation | CalDAV conditional PUT/DELETE |
| P4 | Other CalDAV | explicitly configured HTTPS server, TLS validation and safe discovery | RFC 4791 | capabilities dependent |
| P5 | ICS web subscription | bounded HTTPS pull | read-only | unsupported |

Apple **Calendar.app** can aggregate Google and Microsoft accounts. Connect
the underlying real provider exactly once, not both the Apple front end and
Google service, to avoid duplicate events. Don't store the main Apple ID
password; app-specific passwords require 2FA and must live in an
owner-only credential store with revoke instructions.

Each provider adapter must persist its own secret auth/cursor state
under 0700 directories and 0600 files, never exposing tokens to
the browser or LLM. Treat URLs and calendar text as untrusted:
block SSRF, redirects to non-allowlisted hosts, unsafe HTML,
accidental attendee invitations and destructive recurrence edits.

## AI calendar operations

1. **Automatic by default:** search and summarize *locally saved*
   events, detect known conflicts, suggest free slots, and produce a
   daily/weekly briefing. Never misrepresent stale/incomplete data.
2. **Default owner confirmation:** each external create/update/delete
   needs a typed preview containing provider, calendar, timezone,
   attendee impact, exact event ID, before/after diff and a one-use
   signed approval token. Provider writes never trigger on GET.
3. **Optional owner-configured auto mode:** explicit per-account,
   per-calendar and per-action grants. The model can then autonomously
   create and move *its own* private blocks within the approved
   horizon, and delete only its own attendee-free single-instance
   events. Shared events, invitations, external events, recurring
   series and expensive/irreversible changes require separate review.
4. **Execution ledger:** key by provider/account/calendar/event and
   content/revision for deduplication. Record action proposal, policy
   decision, approval/grant version, external outcome, and a
   compensating undo when the provider supports it. Never blindly
   retry an uncertain write; re-read provider state first.
5. **Source of truth:** provider's calendar remains authoritative;
   OKAL is a working local projection. Gmail-to-Calendar suggestions
   must not create calendar events just because an email mentioned a
   date; show a draft for confirmation or use an explicit scoped grant.

## Product and mobile

Desktop UI will offer Agenda / Day / Week / Month, account filters,
Gmail-linked proposals, busy overlays with existing local tasks, and
notification preferences. Do not visually equate local tasks with
provider calendar events or create duplicate reminders.

The future Android/iOS companion should consume a **versioned**, limited
snapshot from a securely paired sync service, schedule local reminders,
and allow safe action requests. `127.0.0.1:8766` must never be
exposed directly on the internet. Cross-device delivery while a PC is
offline would require separately reviewed secure relay/push or direct
authorized provider sync on the phone; local-only desktop storage
cannot magically send mobile push when offline.

## Technical review sources

- [Google Calendar MCP (MIT)](https://github.com/nspady/google-calendar-mcp):
  multi-account provider API and recurring-event semantics.
- [Replanme (MIT)](https://github.com/avervill/replanme):
  plan → safety → owner approval → audited execution.
- [Zero Calendar (MIT)](https://github.com/x1xhlol/zero-calendar):
  calendar UX inspiration, **not** its Convex/OpenRouter/Resend stack.
- [Google incremental sync](https://developers.google.com/workspace/calendar/api/guides/sync).
- [Google Calendar OAuth scopes](https://developers.google.com/workspace/calendar/api/auth).
- [Microsoft Graph event delta](https://learn.microsoft.com/en-us/graph/api/event-delta?view=graph-rest-1.0).
- [Apple app-specific passwords](https://support.apple.com/en-us/102654).
- [CalDAV RFC 4791](https://www.rfc-editor.org/rfc/rfc4791).

## Next focused PRs (ShiftCore)

1. Google Calendar read-only OAuth and live incremental sync, separate
   private credentials from Gmail and owner-device authentication.
2. Calendar timeline UI with provider status, stale-data indicator
   and protected read semantics; tests for RTL, keyboard and mobile.
3. AI natural-language planning as structured proposals with policy
   checks, explicit preview/confirm and scoped autopilot grants.
4. Provider mutation ledger, conditional writes and audited cancel/undo.
5. Microsoft Graph adapter, then Apple CalDAV adapter.
6. Integrated desktop notifications and secure mobile projection.

Every step requires an issue, dedicated branch, conventional commits,
PR, exact-head CI and owner Solo Maintainer review before merge.
No production credentials, tokens or secrets in GitHub.
