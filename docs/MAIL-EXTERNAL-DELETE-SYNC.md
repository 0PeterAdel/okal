# Gmail deletion outside OKAL — automatic Inbox reconciliation

## What changed

OKAL must not continue displaying saved messages in Smart Inbox after the
owner moves those messages to Gmail Trash directly in the Gmail website/app.

Google's History API uses:
- `labelsAdded` with `TRASH` when a message is moved into Trash;
- `messagesDeleted` when a message is permanently deleted (not merely
  Trashed);
- `labelsRemoved` with `TRASH` when a message is restored.

The original history implementation only subscribed to messageAdded and
messageDeleted; therefore moving a message into Trash did not invalidate an
old local insight. OKAL now processes all four history event types.

On successful Gmail History sync, changes are atomically recorded in the
local `mail_sync_visibility` table with the checkpoint. Current Smart Inbox,
Inbox Actions, manual-review queue and Morning Briefing exclude messages
marked `trashed` or `deleted`. An explicit restore can make an existing
saved message appear again without repeating AI inference.

The table **does not remove old evidence, run summaries or original local
audit records**. Existing immutable historical reports are retained so
tracking and auditing remain possible, but the deleted message is not part of
the *current inbox* or future morning highlights.

### Prior deletions and reconnects

A history cursor can have already moved past deletions before installing
this fix. Each successful sync now checks up to 50 native Gmail message
metadata records that lack visibility verification or are over a day old.
Previously unchecked messages are ordered newest first, then older
messages are reconciled over subsequent syncs. Gmail 404 means a message
was deleted; Gmail `TRASH` label means trashed; other labels are present.
This only performs Gmail **read** operations.

No API scope change, Gmail write, irreversible delete or model call is
introduced. Google readonly and modify grants both permit this check.
If Gmail is unavailable or OAuth fails, the checkpoint is not silently
advanced and current records are not incorrectly discarded.

### Timing

Background History Polling runs on its configured interval (default about
5 minutes), not immediately in response to a change on gmail.com. The
Dashboard re-reads the local snapshot about every 90 seconds while idle and
when its browser tab regains focus. A fresh manual review or open message
dialog is not interrupted.

The dashboard refresh button only reloads locally cached state; it does
not initiate Gmail sync. To request a provider check on the owner's device:

```bash
cd /home/okal/Projects/okal
bash scripts/run-okal-core.sh mail sync now
```

If the background Gmail worker currently holds the operation lock,
`mail_operation_already_running` means another sync is in progress.
Do not stop the service just to resend a check; it should reconcile at
the next normal cycle. No owner-generated test email is required.

## Acceptance (mocked in CI; live owner test pending)

- Gmail Trash label event hides saved mail with no need for an OKAL delete.
- Permanent delete hides it; Gmail Restore makes an existing saved item
  visible again.
- Previously trashed messages reconcile even if their history events have
  already been checkpointed.
- Manual-review and Morning Briefing reflect the same native visibility.
- Native Gmail read errors do not destroy old evidence or advance cursor.
- UI refreshes in the background only when the owner isn't selecting or
  reviewing messages.

CI: `apps/core/tests/test_mail_external_visibility.py`.
