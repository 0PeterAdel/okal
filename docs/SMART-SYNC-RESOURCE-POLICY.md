# Smart Sync policy — Gmail and Google Calendar on Omarchy

Purpose: save network, local CPU and Ollama/GPU cycles without faking an
event-driven Gmail feed or resetting the sync cursor on laptop restarts.

## Actual current Gmail behavior (unchanged in this PR)

- When private `mail/config.json` has `sync_enabled=true`, the mail worker
  wakes every **30 seconds** to check local due times (very cheap).
- The real Gmail **History API** sync is due every **300 seconds**, measured
  from the last attempt and kept in SQLite. On a backlog it may continue
  one bounded next chunk after 30 seconds; failed attempts have a cooldown.
  With `sync_enabled=false`, the worker does not do background Gmail sync.
- Gmail uses `history.list` with a persistent cursor and fetches messages
  changed since that cursor, not the whole inbox each time. Only genuinely
  new unprocessed **UNREAD** mail is summarized by local Ollama. A configured
  daily digest is **independent**; it is not a push notification.
- `ocal-mail` is not a separate service: one `okal-core` user service hosts
  the light worker. The core service normally starts with the login session
  and stops with it. It restarts on abnormal failures, not once per email.

**This is not instant arrival.** Google's official Gmail API direct push
notification mode requires Cloud Pub/Sub topic, watch renewal (at least
weekly) and either HTTPS webhook delivery or a pull subscription. A strictly
local app without Pub/Sub **cannot** receive a Gmail API notification
immediately on each arrival. Google officially recommends client polling on
user-owned devices.

References: [Gmail Push](https://developers.google.com/workspace/gmail/api/guides/push),
[Gmail incremental sync](https://developers.google.com/workspace/gmail/api/guides/sync).

We do NOT silently introduce Google Cloud billing, Pub/Sub or an always-on
external listener. We also avoid Gmail IMAP IDLE as a drop-in because Google's
IMAP XOAUTH2 requires broad `https://mail.google.com/` OAuth scope.
Future push is a separate opt-in feature with owner-approved cloud setup
and a slower periodic recovery/checkpoint reconciliation path.

## Updated Google Calendar behavior (this PR)

- Periodic read-only Calendar Google API sync **every 10800s (3h) per
  configured account**, instead of every 1800s (30m).
- After the service starts, it waits 20 seconds before any local due check.
  A recent attempt is recorded in a tiny SQLite table
  `calendar_google_poll_attempts`. It is committed **before** provider I/O.
  Therefore successive logins, service crashes and network failures do not
  produce additional Calendar requests inside that same 3h window.
- Every five minutes the idle worker checks **local SQLite only** to see
  whether any account is due, using `Event.wait()` rather than busy-looping.
  A valid calendar may therefore be refreshed within five minutes *after*
  the three-hour due time, not at an exact second.
- If a new account has never been checked, the background worker starts its
  first request after 20s. An explicit OAuth browser consent still triggers
  an immediate read and records the attempt so the startup worker does not
  repeat it. Manual CLI sync is always deliberate and remains available.
- A failed provider call records the safe existing per-calendar failure
  status, leaves historical sync token/cursors untouched and waits until
  the next 3h slot. The previously implemented bounded current-week
  fallback remains in place for historical validation errors.
- Read-only `calendar status` now also includes `background_poll`
  with `last_attempt`, `next_eligible`, `interval_seconds=10800`.
  These values never contain event titles, OAuth tokens or calendar IDs.
  The status GET never calls Google; users can query it freely.
- This changes only the periodic Calendar worker; it does not control
  explicit calendar OAuth, manual CLI, Google Tasks or Gmail.
- Since Calendar is now refreshed less often, some changes may take up to
  around 3h5m to show up. A full-source verification is still required
  before OKAL can promise reliable free slots.

## Owner acceptance checks

```bash
PYTHONPATH=apps/core/src python -m unittest discover \
  -s apps/core/tests -p test_calendar_poll_interval.py -v
PYTHONPATH=apps/core/src python -m unittest discover \
  -s apps/core/tests -p test_calendar_auto_sync.py -v
```

After approved merge and private SQLite backup, deploy updated main,
restart core and check **redacted** local status:

```bash
bash scripts/run-okal-core.sh mail sync status
bash scripts/run-okal-core.sh calendar status --account default
```

Do not publicly paste raw output if any account/calendar references are
present. Owner must reboot the service twice within 3h and verify that the
`background_poll.last_attempt` is unchanged and no Calendar API calls are
repeated; after 3h a due tick should update it. The user service stays
running for local dashboards/alerts but does not spin Ollama when idle.
Testing service or machine restarts on the real owner device is still
pending and is not proven by GitHub CI.
