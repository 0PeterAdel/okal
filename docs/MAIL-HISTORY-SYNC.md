# OKAL Gmail History Sync — Security and Operations

Implementation branch: feat/gmail-unattended-history-sync (PR #42).
Based on feat/core-mail-backend at 0e7c6eb. Draft pending acceptance.

## Scope and correctness

This is an opt-in, read-only, five-minute Gmail worker inside the already-running
OKAL Core service. It uses Gmail users.history.list and persists an opaque
history cursor in the SAME private SQLite database as the Core inbox.

On the first scan, capture the mailbox history ID BEFORE a bounded 24-hour
backfill. On later scans read ALL history pages from the saved cursor. Collect
new message IDs, filter current SENT/DRAFT/SPAM/TRASH labels, deduplicate by
native Gmail ID, and classify/summarize with the explicitly pinned LOCAL Ollama
model. The checkpoint, seen-ID tombstones, summary and provenance are recorded
in one transaction. Errors and interrupted runs NEVER advance the cursor.

Example: a successful scan at noon, a system shutdown until 15:00, then service
restart. The worker picks up at the last saved cursor and reads newly-added
messages from the outage. It does not merely fetch messages received during
the last five minutes. The daily digest scheduler remains separate.

If a Gmail history cursor is expired (HTTP 404), the worker captures a fresh
cursor before scanning visible incoming messages from the last successful
checkpoint (with five-minute overlap), at most 31 days. The saved status/digest
warns that deleted historic mail cannot be reconstructed. A gap exceeding 31
days fails without moving the cursor. Likewise, query pagination, message,
runtime or model budget errors fail without claiming a complete sync.
Very large backlogs may need controlled manual recovery / higher bounded config.

Only messagesAdded are treated as new for AI summaries. Read/unread or label
changes, deleted messages and attachment contents are NOT a mailbox mirror or
guaranteed forensic record. History IDs are monotonic, not contiguous.

## Owner-only setup

Keep the existing private state and untracked directories. Never run git clean,
git reset --hard, or overwrite a live SQLite DB. Stop Core before changing
its code, and make a fresh out-of-tree SQLite backup; follow MAIL-BACKEND.md.

First ensure the existing Gmail configuration and OAuth approval are valid.
On the owner's machine (after reviewed code install):

~~~bash
bash scripts/run-okal-core.sh mail doctor
bash scripts/run-okal-core.sh mail sync now
bash scripts/run-okal-core.sh mail sync on
systemctl --user restart okal-core.service
bash scripts/run-okal-core.sh mail sync status
bash scripts/run-okal-core.sh mail status
~~~

For read-only suspension:
~~~bash
bash scripts/run-okal-core.sh mail sync off
~~~

No new daemon or paid API is needed. Gmail still requires internet. Core uses
local inference and existing optional mail hash-locked dependencies.
Enabling the schedule NEVER grants Gmail sending authorization.
No automatic send, archive, deletion, reply or mark-as-read is included.

## Persistent OAuth — no recurring token pastes

The access token is short-lived; Google's official OAuth credentials automatically
refresh it. OKAL stores the refresh token and rotated credentials in a private
owner-only mode 0600 JSON file, atomically fsyncing updates after renewal.
Never publish the OAuth client JSON, refresh token, cache, SQLite data or mail
content. The worker never opens a browser or refreshes with a Google password.

Reauthorization may still become necessary. Google can revoke/expire refresh
tokens. Critically, Google External OAuth apps in TESTING mode normally receive
Gmail-scope refresh tokens expiring after seven days. A properly configured,
eligible Production consent screen may be needed; this does not bypass Google
verification, security, account scope or revocation policies. After revocation
the local doctor/worker must report authorization_required rather than silently
pretend online access.

Official reference:
https://developers.google.com/identity/protocols/oauth2

## Persistent but revocable browser pairing

The locally issued OKAL inbox read key is NOT a Gmail OAuth token. Paste it
only on first pairing with this trusted desktop browser. The app exchanges it
for a random cookie via POST /api/v1/session. The server persists only a hash
of the random browser session, bound to the issuing device, which must remain
active and unexpired.

The cookie is HttpOnly, SameSite Strict, host-only and scoped to /api.
It is not written to localStorage, IndexedDB or client JavaScript.
After reload, the browser resumes reading its saved summaries without retyping
the key. Logout deletes/revokes the session, and a device-revoke also
invalidates it. The cookie lasts at most 30 days and never beyond the parent
device expiry. Pair again after expiration or explicit revocation.

This browser stays on loopback HTTP (127.0.0.1/localhost), and its cookie is
NOT Secure because the deployment is not HTTPS. NEVER expose it to a LAN or
phone via reverse proxy without independently reviewed TLS, authorization,
CSRF and device pairing. Cookies have read-only inbox scope; the outgoing email
CLI still requires Google send permission and exact-content confirmation.
Same-user malware/browser extensions/unlocked desktop are residual risks.

## Triage and digest presentation

Stored analysis is grouped in Arabic/English under Action required,
Information and Low priority. Each entry carries a native Gmail source link,
subject/sender, summary, suggestion, and unreviewed attachment warning.
The overall briefing records the period, counts and recovery caveats. All
email text and LLM outputs are treated as untrusted DATA, rendered as text
nodes instead of executable HTML. Follow email links and verify details
in Gmail before sending or committing to anything.

Raw incoming body text is NOT saved in the SQLite database, but metadata,
body digests, snippets and classifications can still be sensitive.
Use the existing private SQLite backup guide. Retain seen-message tombstones
to prevent replay. Explicit mail prune controls old summary retention;
backups still contain anything present at the time of backup.

## Verification and limitations

Synthetic no-network tests cover initial fetch, incremental pages, restart,
failure atomicity, deduplication, expired-history recovery, failed-window
safety, browser pairing, expiry, revocation and origin enforcement. CI runs
the full Python 3.12 and 3.14 test matrix, JavaScript syntax and process
restart. Passing CI cannot prove Gmail account linkage, real three-hour
downtime behavior, model quality or send delivery. Keep PR #42 draft until
owner-only local acceptance and upstream PR #41/#39 dependency review.

References:
- https://developers.google.com/workspace/gmail/api/guides/sync
- https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list
- https://github.com/googleworkspace/cli/tree/main/skills
- https://github.com/taylorwilsdon/google_workspace_mcp
- https://github.com/elie222/inbox-zero
