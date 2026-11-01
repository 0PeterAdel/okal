# OKAL Gmail — Viewed / Unread state + hosted images

Originated as stacked PR #54, now included in the single consolidated OKAL integration release. Deploy the reviewed integration commit from `main` after its merge.

## New active-inbox semantics

- Gmail History `labelsRemoved(UNREAD)` means the message became **Read**, and the message disappears from current Smart Inbox and suggested actions on the next successful sync. The inverse `labelsAdded(UNREAD)` can reveal an unread item again when it was not locally viewed.
- Opening original Gmail content **successfully** inside OKAL records `mail_local_seen` through a same-origin POST and immediately removes the card from current Smart Inbox. This is **only a local Viewed status**; it deliberately does NOT modify Gmail itself.
- The original AI analysis, message provenance, Gmail URL and history remain in SQLite; the saved `mail_sync_seen` list prevents repeated local inference on old Gmail IDs.
- Mark Read/Unread from OKAL requires the existing explicit Gmail confirmation. Confirmed Mark Unread also clears the local Viewed marker.
- Current Gmail state is reconciled from history and the existing bounded native metadata checks (up to 50 older messages in a sync cycle). Read messages not yet analyzed are skipped instead of consuming Ollama work.
- The private database gains `mail_local_seen` and `mail_gmail_unread` tables. No destructive migrations.

## Displaying remote images — owner-requested always-on behavior

- **Current default:** opening an original Gmail message in OKAL automatically allows remote HTTP(S) images. There is no longer a Load Images button or remember-permission checkbox. The reader does not fetch images for unopened inbox rows.
- **Privacy:** image hosts and trackers may learn that the message was opened. This is an explicit owner-requested behavior, not a privacy-preserving default. The existing private SQLite image setting is ignored by the reader; it is retained for backwards database compatibility, not exposed in UI.
- The original sender HTML stays inside a script-disabled, opaque-origin sandbox; scripts, forms, automatic navigation, fonts and network APIs are still blocked by CSP. Safe deferred `data-src`, `data-original` and `data-srcset` image URLs are activated for the opened message.
- CID / Content-Location images still render from Gmail MIME locally where possible. Third-party hosts, expired URLs, Firefox tracking protection or browser extensions can still prevent an image from appearing. `فتح في Gmail` remains the fallback. No server-side image proxy or third-party URL fetch was added.

## Native reader Trash after Viewed

- Opening a saved message marks it locally Viewed and hides it from Smart Inbox. The reader's Trash button now uses the verified *native Gmail message labels*, not the removed list row, to decide whether to offer a delete preview.
- Starred, Important, Sent, Draft, Spam, Trash or non-Inbox messages are not offered for Trash. The server independently checks its saved source, current Gmail metadata, protective labels and the action permission.
- Clicking reader Trash opens the **same read-only native preview and explicit confirmation dialog** as batch Trash. Only the confirmation triggers a Gmail move to recoverable Trash; no permanent delete and no automatic retry on uncertain outcome.

## Owner rollout

```bash
cd /home/okal/Projects/okal
git status --short --branch

backup_dir=$(mktemp -d "$HOME/okal-core-backup-XXXXXXXX")
bash scripts/run-okal-core.sh backup "$backup_dir/core.sqlite3"
git fetch origin main

systemctl --user stop okal-core.service
git switch main
git merge --ff-only origin/main
systemctl --user start okal-core.service
systemctl --user is-active okal-core.service
```

Open Firefox at <http://127.0.0.1:8766> and hard refresh Ctrl+Shift+R.
Try one noncritical email; opening it should hide it in Smart Inbox but leave
it unchanged in Gmail. Mark another message as Read **inside Gmail**, run
`bash scripts/run-okal-core.sh mail sync now`, and check that the saved item
disappears from Smart Inbox without a new AI summary. Then test the hosted
images loading automatically on opening the native Gmail reader.

## Acceptance limits

Synthetic offline CI is not proof that all live Gmail newsletter pictures
will load. User browser privacy add-ons or third-party image host policies
can block graphics even when consent is enabled. The user's actual
Omarchy browser, Gmail account and service restart must still be tested.
