# OKAL Core · Friendly Morning Brief + Recoverable Gmail Trash

This experimental feature is **stacked on PR #43**, itself based on Gmail
PR #42. It is not active on the owner's Omarchy laptop until reviewed and
installed. Do not merge out of dependency order.

## Morning briefing

Open `http://127.0.0.1:8766` after boot/login. Above the inbox, OKAL displays
a friendly Egyptian Arabic **voice-ready** briefing constructed locally from:

- Today’s and overdue **owner-confirmed** local tasks with timezones.
- Saved incoming Gmail action and FYI insights received in the past 24 hours.
- Actual last Gmail sync time; a stale checkpoint is marked as incomplete.

You can access the same content offline without opening Gmail or running a
model by executing:

```bash
bash scripts/run-okal-core.sh morning
```

The JSON field `spoken_text` is available for a future voice/TTS overlay.
The briefing is **rendered whenever you open the dashboard**. An optional
user systemd service can show the same text as a desktop notification at
graphical login, once per Cairo calendar day. No synthetic speech is
generated, and there is no Google Calendar API connection.

The notification command works only with a running graphical desktop and
`notify-send` installed. It never reads Gmail online or executes email
instructions. A successful delivery date is remembered in SQLite, so
restarting the service or logging in again that day doesn't show duplicate
notifications:

```bash
# One local notification now, if a desktop notification daemon is active:
bash scripts/run-okal-core.sh morning --notify

# Optional: install this unit ONLY after reviewing its exact paths.
install -Dm644 deploy/okal-morning.service \
  ~/.config/systemd/user/okal-morning.service
systemctl --user daemon-reload
systemctl --user enable okal-morning.service
# Start in the active graphical user session (optional for first test):
systemctl --user start okal-morning.service
```

This opt-in unit is wanted by `graphical-session.target`. Whether your Omarchy
session actually activates that target must be verified locally; if it doesn't,
the unit will not automatically display a login notification. Keep this
separate from the already-enabled `okal-core.service`. No `sudo` or
global machine changes are required.

Summarization guidance for future incoming emails has also been sharpened to
emphasize actual takeaways, clear action, exact dates/names, and natural
Egyptian Arabic. **Old stored summaries are not retroactively changed.**

## Recoverable bulk Gmail Trash (not permanent delete)

The read-only, automatically opened dashboard can **select up to 20 messages**
under **للاطلاع · Information**. Click **تجهيز طلب نقل المحدد إلى Trash**
to display/copy a **preview-only** command for the owner's local Terminal.

No write API is added to the passwordless web dashboard. A browser or an
untrusted message cannot submit the deletion itself.

Example (replace `aa`, `bb` with genuine selected native Gmail IDs):

```bash
# Inspect exact subjects and senders, no mutation.
bash scripts/run-okal-core.sh mail trash --ids aa bb

# Only after reviewing, opt in to a recoverable Trash move:
bash scripts/run-okal-core.sh mail trash --ids aa bb --apply
```

`--apply` requires **both** an interactive owner terminal and typing
`TRASH ` followed by the full approval digest printed by the current preview.
The system verifies the same account, locally saved native message IDs,
`Information` category, native Gmail subject, and protected Gmail labels
before an attempt. New incoming messages, drafts, starred, important, sent,
and already-trashed messages cannot be silently swept into this batch.
Each Gmail Trash operation is written **once**, no automatic retries after an
ambiguous API result. A private per-message ledger records attempts and
provider-confirmed Trash writes. If any request fails midway, **stop and
inspect Gmail manually**, because some earlier messages may have moved.
Confirmed trash moves are removed from the local Inbox triage view.

### Optional scope authorization — one-time explicit owner action

Gmail's `users.messages.trash` API needs the OAuth
`https://www.googleapis.com/auth/gmail.modify` scope. Google's scope is
**broader than trash alone**. The current read-only token cannot move
anything. Google does **not** offer a Trash-only scope.

When you decide to enable this feature on the laptop and have reviewed the
permission, run:

```bash
bash scripts/run-okal-core.sh mail authorize \
  --client /absolute/private/google-desktop.json --enable-trash
```

This replaces the stored read-only OAuth grant with a `gmail.modify` grant.
It **does not enable OKAL mail sending** (the local send gate remains false),
does not auto-delete, and does not authorize any action from the web page.
Re-authorization may require Google's consent again, and the account must
match the configured Gmail account. Never paste OAuth config or tokens into
chat/GitHub.

**To return to read-only permission**, reauthorize with the original
`mail authorize --client /absolute/private/google-desktop.json` (without
`--enable-trash`). This resets local trash/send gates. If you need sending
and trash later, that combination needs a separate security review.

Google Trash is **recoverable only while Gmail retains it**. Gmail may
automatically empty Trash after its retention window; this implementation
never calls the permanent delete or batchDelete APIs.

## Security boundary

- Core dashboard stays same-origin loopback, including passwordless read-only
  mode. No /api endpoint for Gmail writes or task approvals.
- Explicit owner CLI + fresh human-readable preview + digest confirmation.
- Gmail modify scope used only on explicit opt-in; no new paid API.
- Source provenance is not model-owned; native Gmail subject and labels
  checked before any write.
- Same-user malware can still invoke owner CLI with its permissions; running
  user sessions on shared/untrusted desktops is outside this boundary.
- No autonomous inbox cleanup, no bulk-delete rules, no model-executed tools.

## Follow-up checks

After reviewed feature deploy, open the dashboard and confirm the first
friendly briefing includes only *real saved* email and local task data.
Then choose a non-important Information email to preview the Trash command.
Do not authorize `gmail.modify` or use `--apply` until happy with the
selected preview. For unrelated Gmail permissions/credentials, preserve the
current setup.
