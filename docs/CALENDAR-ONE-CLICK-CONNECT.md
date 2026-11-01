# Connect Google Calendar from OKAL (one click)

This feature uses the **existing Gmail Desktop OAuth Client**, not a second
Google Cloud client. The owner explicitly requested the familiar
"Connect → Google consent → return to app" experience (Issue #62).

## What the owner does

1. Review and merge Calendar Foundation PR #59, then Google read-sync PR #61,
   then this UI/OAuth PR, following the repository Solo Maintainer governance
   and fresh CI checks for each merge.
2. Open the normal OKAL Dashboard at
   `http://127.0.0.1:8766/#integrations` on the Omarchy desktop.
3. Click **ربط Google Calendar** and choose the intended Google account on
   Google's official consent page. Accept the two read-only Calendar scopes.
4. Google returns to a brief, **self-hosted** completion document, which
   navigates to the OKAL Dashboard from the local origin. The Integrations
   panel displays the authorization result and the separately verified
   sync status. No JSON error or callback codes appear on successful return.

**No new OAuth JSON file or token entry is requested.** Existing Gmail
authorization must have completed on the same OKAL private state directory
already, because the client ID and Desktop client secret are retrieved only
from `mail/token.json`. Gmail access and refresh tokens are never passed to
Google Calendar, any browser endpoint or the LLM. Calendar has a separate
token at `calendar/google/default.json`.

## Technical boundary

- Explicit JSON POST `/api/v1/calendar/oauth/start`, guarded by the same
  loopback, Origin, browser-session and Fetch Metadata checks as other
  privileged owner UI actions.
- Server builds Google official Desktop client info from the private Gmail
  token's `client_id`, `client_secret` and canonical token URI only.
- The server creates a unique, short-lived OAuth state and PKCE S256
  challenge and gives the browser **only** Google's official authorization
  URL. No OAuth state, tokens or client secrets are returned via the API.
- Native Desktop OAuth callback:
  `GET /api/v1/calendar/oauth/callback`. Cross-site navigation is
  permitted **only for this path**, and only the matching one-use state
  can complete. Wrong/expired/replayed state or invalid scopes fail closed,
  with a local error page and a return link rather than raw JSON.
- Successful callback responds with a local HTML document (not a 303
  chain). Its self-hosted JS navigates with `location.replace` so
  callback authorization codes are not kept in visible navigation history.
  A safe top-level GET document navigation to `/` is also permitted
  from cross-site context, but **no cross-site API access, subresource
  requests or writes are permitted**.
- Google API calls do not happen in the regular dashboard GET handlers.
  The existing read-only background worker syncs Calendar after consent.
- Both provider writes and automatic AI edits/deletes remain disabled.
- Google Desktop OAuth is valid on Linux using loopback redirect:
  [Google documentation](https://developers.google.com/identity/protocols/oauth2/resources/loopback-migration).

## Limitations

The redirect stays on the **same local port** on which the owner clicked
Connect: `8877` for an isolated test server, `8766` in the deployed
OKAL app. Test Calendar permissions and sync are isolated and will not
automatically appear in the production SQLite state.

This is a **single-user, single-local-core** UI consent. The state is
in-process and expires after five minutes or a Core service restart;
restart the consent with the button if expired. After consent OKAL queues a bounded, read-only full sync and keeps its
periodic worker for later changes. A failed provider fetch records only
a redacted error code; the UI must never claim connected until a successful
checkpoint.
The original Gmail consent should still be rechecked after the Calendar
consent, because both use the same Google OAuth client identity.
Testing-mode Google refresh-token expiration may require reconnect.

The current Calendar Foundation and Google provider PRs are still drafts.
This change is for **review, not production deployment**; no live account
consent was performed through GitHub CI.
