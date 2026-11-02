# Optional private Gmail desktop notices (local-only)

Issue #91. Notification requires **owner opt-in**. It does not implement
Gmail Pub/Sub push, does not add Google API polling, and does not wake
Ollama solely to show a notification.

## Delivery rules

After the existing Gmail History worker has successfully completed and
committed a chunk of *new, unread, previously unseen* messages, OKAL sends
**one generic desktop notification** containing only the count (1–100).
The notification contains NO sender, account address, subject, message ID,
body, AI summary, or quoted data. Titles never reach the desktop notifier.

Never notify for initial/backfill runs (which may replay mail after
login), zero new items, failed provider/model sync, an unrecognized
result, or manual actions. The worker calls `notify-send` via a local
subprocess with no shell and a strict 3-second timeout. If desktop
notifications are unavailable, Gmail history still commits normally.

A private SQLite `mail_desktop_alert_claims` table records each
successfully committed Gmail history run **before** attempting to display
it, preventing duplicate alerts across service restarts. Notice
delivery is best-effort: a dropped OS notification is *not retried*,
so no storm is triggered on login. Claims older than 90 days are pruned.
No additional daemon, service, public webhook, Cloud resource or timer.

## Owner controls

Default is **off**, including all existing private configurations:

```bash
cd "$HOME/Projects/okal-production"
bash scripts/run-okal-core.sh mail notifications status
bash scripts/run-okal-core.sh mail notifications on
bash scripts/run-okal-core.sh mail notifications off
```

These commands only update the existing private mail `config.json` via the
private file helper; they do not change OAuth scopes or sending settings.
The running Gmail worker rereads the config on each tick, so a service
restart is normally unnecessary. If background Gmail sync is disabled,
no automatic Gmail notices occur.

**Important:** Notifications can only appear after the existing **up to
five-minute** Gmail incremental History polling plus local processing.
They are not immediate Gmail Push. Achieving near-real-time requires
separately authorized Google Cloud Pub/Sub work; Issue #89 was deferred
per owner and no Cloud resources were created.

## Acceptance

```bash
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests \
  -p test_mail_desktop_alerts.py -v
```

After PR review, merged CI and SQLite backup, test with real user-systemd
and a non-sensitive **new unread** Gmail test message. Check a single
notification without sender/subject, ensure no repeat after service
restart, and verify turning the setting off silences it. Also test
`notify-send` failure (or no graphical session): Gmail cursor and
Smart Inbox must still progress. Synthetic CI tests cannot prove
notification delivery under the actual Omarchy Hyprland/DBus session.
