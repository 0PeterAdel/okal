# OKAL Mail Agent V1 — Owner-reviewed Gmail actions

A stacked **Draft PR #49** built over PR #48. Code is on GitHub; the owner's
actual Omarchy checkout is unchanged until they fetch/switch branches.

## Capabilities

1. Click any saved Gmail message to open its full native content in OKAL
   (HTML/text including embedded images), with separate saved AI summary.
2. Mark Read, Mark Unread and Archive operate through native Gmail API
   `users.messages.modify` using the owner's existing `gmail.modify` scope.
   Each action first opens a **read-only provider-native review** displaying
   subject and current labels, and then requires a **separate confirmation
   click**. A 120-second single-use digest-bound approval prevents changing
   a different selection or replaying a clicked button. Archive excludes
   the item from active OKAL triage (historical evidence is retained).
3. **Create Task** makes one idempotent local task for saved Gmail evidence,
   linked back to its original message. No external calendar writes.
4. **AI Reply Draft** runs the previously pinned, verified, local-only Ollama
   model on the native Gmail message. The recipient/thread metadata comes
   from Gmail, **never from AI**. Choose Egyptian Arabic or English, review
   the proposed reply in the UI, edit and save local revisions, or copy it.
   The original draft is preserved when an edited revision is saved.
5. **Send after explicit owner approval**: click Review & Send, verify the exact
   recipient, subject and complete saved draft body, then click Confirm Send.
   Gmail's existing `gmail.modify` scope also permits `messages.send`.
   The request requires one-time approval (120 seconds), and the existing
   reconciliation-aware `send_reviewed` path records its pending tombstone
   BEFORE making a single provider write. No automatic retry of an uncertain
   send. The persistent `send_enabled=false` setting remains unchanged;
   only this owner-approved API request is permitted to send.

## Before real-device testing

Back up private Core database. Check for uncommitted edits and do not reset
or clean. To fetch this stacked branch (do not switch during an active sync):

```bash
cd /home/okal/Projects/okal
git status --short --branch
backup_dir=$(mktemp -d "$HOME/okal-core-backup-XXXXXXXX")
bash scripts/run-okal-core.sh backup "$backup_dir/core.sqlite3"
git fetch origin feat/core-mail-agent-actions-v1
systemctl --user stop okal-core.service
git switch --track origin/feat/core-mail-agent-actions-v1
systemctl --user start okal-core.service
systemctl --user is-active okal-core.service
```

If the branch is already local, use `git switch feat/core-mail-agent-actions-v1`
and a **fast-forward-only** update when the working tree is clean. Do not
overwrite local files/other worktrees.

Open <http://127.0.0.1:8766> and hard-refresh Firefox (Ctrl+Shift+R). Choose
one noncritical email and test Mark Read, then Unread; next separately test
Archive with a recoverable message. Verify its actual Gmail labels. Test
Create Task twice and confirm only one task; test Ollama reply generation,
editing and copying, and verify no email was sent.

## Safety limits and outstanding work

- Gmail actions are *owner-click only*; no automated deletions, sends, or
  agent tool execution. Every external modification has preview + confirm.
- Gmail writes receive **no automatic retry**. The append-only local audit
  ledger records attempts before each provider call; ambiguous outcomes
  must be checked in Gmail, not resent.
- Current Gmail label projection for the UI can lag the background sync.
  Archived email is excluded from the active inbox on a confirmed OKAL
  action; external re-inbox of an archived message may need a future
  reconciliation improvement. Gmail remains authoritative.
- The local model must be available, cloud-disabled and have the expected
  digest; otherwise AI drafting fails closed with an explicit error. No
  auto-pull and no paid inference API.
- Sending is strictly opt-in per message and requires two explicit clicks:
  Review & Send, then Confirm Send in a separate preview. Always verify
  real recipient and facts; generated claims may be wrong.
- The manual CLI send configuration remains disabled with this Google grant.
  The in-app confirmed send uses the existing Google gmail.modify scope.
  Gmail sent receipts may be uncertain on a network interruption: inspect
  the Sent folder before considering a new draft or trying again.
- Tests are entirely synthetic; owner Firefox/Gmail acceptance is required
  before merging stacked Draft PRs into `main`.
