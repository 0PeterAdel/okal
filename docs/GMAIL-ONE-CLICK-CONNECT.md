# One-click Gmail connection in OKAL

The owner explicitly asked Gmail to use the same one-click Google consent
flow as Calendar. This is an addition to existing, working Gmail sync and
operator controls, **not** a new mail integration or automatic Gmail write.

## Owner experience

1. Open OKAL's **Integrations** view on the usual local port
   (`8766` in the deployed app; `8877` only in an isolated test).
2. Select **ربط Gmail** / **إعادة ربط Gmail**, then choose the existing
   configured Google account and approve the **existing** permission set.
3. Google returns to a self-hosted completion page. OKAL navigates internally
   back to Integrations and shows the local authorization status, separately
   from the last successful Gmail sync.

No pasted token, downloaded Desktop client JSON, or CLI reauthorization is
required for an **existing installed OKAL configuration**. The app reads only
client identity metadata already saved in the private Gmail OAuth token,
falling back to the already-authorized Calendar client identity when needed.
It **never copies or exchanges Calendar tokens as Gmail tokens**, nor does it
deliver any client secret, refresh token or access token to the UI.

**First-install boundary:** Google Client ID and Desktop OAuth client identity
still must be enrolled at least once, and the local Gmail configuration
must identify the owner's exact email account. If these are missing, the
Connect button explains why it is disabled rather than inventing credentials
or silently creating a model/workflow configuration.

## Scope and safety

- The existing Gmail token's scope set is reused **exactly**:
  `gmail.readonly`, `gmail.readonly + gmail.send`, or `gmail.modify`.
  When no old Gmail token exists, default to Gmail read-only. Gmail send and
  Trash write options are not enabled by the Connect button.
- Google OAuth starts from an explicit same-origin JSON POST and uses a
  short-lived, single-use server-side state and PKCE verifier. Callback issuer
  is checked. Cross-site GET is allowed only for this exact callback path;
  all other APIs and external-write endpoints remain restricted.
- After Google exchanges the code, OKAL validates the new scopes and uses
  the Gmail API to verify the returned email equals the local configured
  account. If the account is wrong, or the flow fails, the previously saved
  Gmail authorization is left **untouched**.
- Gmail's operation lock is acquired during final verification/token
  replacement, preventing concurrent Gmail background token refresh writes.
  Existing `sync_enabled`, `send_enabled`, `trash_enabled` and schedule
  configuration are not mutated by OAuth.
- The result page uses a same-origin JavaScript navigation and strips callback
  data from visible navigation history. Status endpoints are local-only,
  token-free and reflect *saved* sync evidence instead of claiming live access.
- Calendar remains independent. This change never enables writing to
  Calendar, sending mail, or deleting/trashing messages by itself.

## Testing and deployment

Branch is stacked on #63, which depends on #61 and #59. Follow ShiftCore:
owner reviews upstream PRs and merges them in order, then reviews this diff
and reruns exact-head CI and manual Firefox/Google consent. Draft until then.

When testing from a separate state directory, Gmail configuration is also
needed in that directory; copying Google Desktop client metadata alone (as
was used for Calendar tests) does **not** configure the Gmail account. Never
copy Gmail access/refresh tokens into the test state.

The test UI will return to the **same local port** that initiated consent.
Nothing in a test worktree automatically deploys to the main OKAL service.
