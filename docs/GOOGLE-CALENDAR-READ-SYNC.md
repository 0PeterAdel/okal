# Google Calendar in OKAL — first live read-only connector

This PR is **stacked on Calendar Foundation PR #59**, which must undergo
the owner's documented Solo Maintainer review and merge before this PR
is retargeted onto `main`. Neither change may bypass Governance.

## What this connector does

- Separate local Desktop OAuth for Google Calendar, using only
  `calendar.events.readonly` and `calendar.calendarlist.readonly`.
  The Gmail credentials and permissions are unchanged.
- Owner-driven commands to authorize, discover calendars, manually sync
  one or all calendars and inspect redacted status.
- Background read-only sync every ~30 minutes **after consent**, started
  by Core's own service. It does not connect if no accounts are configured.
  Failing network requests must not stop OKAL's local functionality.
- Google Calendar REST `events.list` with `singleEvents=true`,
  `showDeleted=true`, paginated `nextPageToken`, per-calendar
  `nextSyncToken` and 410 Gone full resync recovery. Event
  normalization preserves timezone-aware times, all-day dates,
  recurring instance identity and cancellation tombstones.
- Persist calendar events to the existing SQLite projection. HTTP
  `/api/v1/calendar/agenda`, `/availability`, and `/status` read
  **only the local cache**; no provider traffic happens on a GET.
- OAuth tokens are not printed to console, returned by the API,
  passed to Ollama or committed to GitHub.
- All external calendar create/update/delete APIs remain **disabled**.
  AI autonomy and explicit grants are a subsequent reviewed change.

## Local setup (Omarchy)

1. In [Google Cloud Console](https://console.cloud.google.com/),
   enable **Google Calendar API** in your existing project if desired.
   Configure OAuth Audience to allow your personal Google account.
   Create an **OAuth Client ID → Desktop app**, and download the JSON.
   You may use the same Google Cloud project as Gmail, but **do not
   reuse the Gmail token file**. Google may require refreshing consent
   in Testing mode after seven days.
2. Put the downloaded JSON in a private folder outside the repo,
   e.g. `~/.config/okal/calendar/google-desktop-client.json`,
   and ensure owner-only permissions:

   ```bash
   mkdir -p -m 700 ~/.config/okal/calendar
   mv ~/Downloads/client_secret_*.json ~/.config/okal/calendar/google-desktop-client.json
   chmod 600 ~/.config/okal/calendar/google-desktop-client.json
   ```

   The wildcard only works when exactly one download matches; choose
   the exact path otherwise. **Never send this file or a token in chat.**
3. Once #59 and this PR have been reviewed and deployed locally:

   ```bash
   cd /home/okal/Projects/okal
   bash scripts/run-okal-core.sh calendar authorize \
      --account default \
      --client-secrets "$HOME/.config/okal/calendar/google-desktop-client.json"
   bash scripts/run-okal-core.sh calendar calendars --account default
   bash scripts/run-okal-core.sh calendar sync --account default
   bash scripts/run-okal-core.sh calendar status --account default
   ```

   `calendar sync --all` explicitly syncs up to 20 calendars. A
   single-calendar sync uses `--calendar <actual-id>` from the listing.
   The default `primary` calendar must be visible in that list.
4. Core's read-only HTTP endpoints:

   ```bash
   curl -fsS http://127.0.0.1:8766/api/v1/calendar/status
   curl -fsS http://127.0.0.1:8766/api/v1/calendar/agenda
   ```

   The API reports cached state, **not guaranteed live completeness**.
   Individual events can include private schedule details; never
   forward HTTP JSON or screenshots containing sensitive data.

## Known limits and future hardening

- Strict full-sync budget: maximum 32 pages × 250 events; if
  exceeded the sync fails closed, retaining the old cursor rather
  than claiming completeness. This first connector does not yet
  filter old events or enable incremental sync by date window because
  Google's `syncToken` forbids `timeMin`/`timeMax` on follow-ups.
- If a batch persists and cursor persistence fails, the old cursor
  remains; the next run replays the same changes idempotently. A
  full-sync 410 refresh reconciles cached deleted events.
- The unattended worker polls without a push/webhook subscription.
  Access tokens may expire; refresh token errors require the owner
  to reauthorize. The status endpoint exposes no secrets and no
  Google account email.
- Backups of the local Core state remain private. Do not expose
  `127.0.0.1:8766` publicly and do not put OAuth credentials into
  any mobile app.
- Recurrence-series editing, attendee invitations, writes, account
  deletion/disconnection, conflict-aware model proposals, UI views and
  phone notifications require separate reviewed PRs.

## CI acceptance

Mock all provider calls: no CI needs network or real Google OAuth.
Test first sync, delta, duplicate/stale protection, pagination,
provider failure, 410 recovery, cancelled events, all-day timezone
handling, recurrence identities, token redaction and local API
read boundaries. Run Governance, Python 3.12/3.14 and Markdown.
Owner records Solo Maintainer human review at current SHA before merge.

Sources:

- [Google synchronization](https://developers.google.com/workspace/calendar/api/guides/sync)
- [Google Calendar scopes](https://developers.google.com/workspace/calendar/api/auth)
- [Google events list](https://developers.google.com/workspace/calendar/api/v3/reference/events/list)
