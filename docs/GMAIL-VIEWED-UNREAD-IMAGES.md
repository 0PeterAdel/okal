# OKAL Gmail — Viewed / Unread state + hosted images

**Stacked Draft PR #54**, on top of PR #53. Changes exist on GitHub, not on the owner's Omarchy PC until deployed.

## New active-inbox semantics

- Gmail History `labelsRemoved(UNREAD)` means the message became **Read**, and the message disappears from current Smart Inbox and suggested actions on the next successful sync. The inverse `labelsAdded(UNREAD)` can reveal an unread item again when it was not locally viewed.
- Opening original Gmail content **successfully** inside OKAL records `mail_local_seen` through a same-origin POST and immediately removes the card from current Smart Inbox. This is **only a local Viewed status**; it deliberately does NOT modify Gmail itself.
- The original AI analysis, message provenance, Gmail URL and history remain in SQLite; the saved `mail_sync_seen` list prevents repeated local inference on old Gmail IDs.
- Mark Read/Unread from OKAL requires the existing explicit Gmail confirmation. Confirmed Mark Unread also clears the local Viewed marker.
- Current Gmail state is reconciled from history and the existing bounded native metadata checks (up to 50 older messages in a sync cycle). Read messages not yet analyzed are skipped instead of consuming Ollama work.
- The private database gains `mail_local_seen` and `mail_gmail_unread` tables. No destructive migrations.

## Displaying remote images

- Previously the screenshot showed the hosted image checkbox **unchecked**: OKAL was blocking remote images by design. The native Gmail read endpoint cannot guarantee third-party pictures without making requests to those external hosts.
- Click **عرض صور الرسالة** for an explicit per-message opt-in. If you want the app to remember it, tick **تذكّر سماحي بتحميل الصور الخارجية**. This stores **a boolean in private SQLite**, never auth tokens or mail data in browser storage.
- The preference persists on the single user's Core service and auto-loads remote images in later emails, unless you revoke it. Third-party hosts can learn that an image URL was requested, and Firefox blockers or expired URLs may still prevent display.
- Internal CID/Content-Location images render locally from the authenticated Gmail MIME payload if available. The official **فتح في Gmail** link is a faithful fallback where embedded assets cannot be recovered.
- No server-side proxy or raw email URL fetch is performed. No new OAuth, Gmail writes or paid inference API.

## Owner rollout

```bash
cd /home/okal/Projects/okal
git status --short --branch

backup_dir=$(mktemp -d "$HOME/okal-core-backup-XXXXXXXX")
bash scripts/run-okal-core.sh backup "$backup_dir/core.sqlite3"
git fetch origin fix/mail-read-state-and-image-preferences

systemctl --user stop okal-core.service
if git show-ref --verify --quiet refs/heads/fix/mail-read-state-and-image-preferences; then
  git switch fix/mail-read-state-and-image-preferences &&
  git merge --ff-only origin/fix/mail-read-state-and-image-preferences
else
  git switch --track origin/fix/mail-read-state-and-image-preferences
fi
systemctl --user start okal-core.service
systemctl --user is-active okal-core.service
```

Open Firefox at http://127.0.0.1:8766 and hard refresh Ctrl+Shift+R.
Try one noncritical email; opening it should hide it in Smart Inbox but leave
it unchanged in Gmail. Mark another message as Read **inside Gmail**, run
`bash scripts/run-okal-core.sh mail sync now`, and check that the saved item
disappears from Smart Inbox without a new AI summary. Then test the hosted
images using the explicit button and optional remembered permission.

## Acceptance limits

Synthetic offline CI is not proof that all live Gmail newsletter pictures
will load. User browser privacy add-ons or third-party image host policies
can block graphics even when consent is enabled. The user's actual
Omarchy browser, Gmail account and service restart must still be tested.
