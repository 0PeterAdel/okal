# OKAL local dashboard — automatic unlock

For this single-user Omarchy deployment, the dashboard now opens directly
without asking for a read key on every visit.

Open: http://127.0.0.1:8766

The server MUST remain bound to 127.0.0.1 through the reviewed
`okal_core serve` launcher. No remote/LAN/phone support is provided.
The Gmail agent, offline model, historical sync cursor and private SQLite
data are unchanged.

## Default: local auto-unlock

- `OKAL_REQUIRE_READ_KEY=0` (the default, even when unset).
- GET requests for only the known read-only endpoints (`capabilities`,
  `summaries`, `runs/{id}`, `mail/triage`, `mail/assistant` and `health`)
  are allowed from loopback without a browser token.
- Sensitive mail state and provider operations are still **CLI only**. No
  auto-sending, Gmail modification, model execution or account-changing
  HTTP endpoint is created.
- Strict Host, loopback client, Origin and Fetch Metadata checks apply.
  Non-matching browser origins, other ports and remote clients get 403.
  Responses carry no-store, same-origin resource policy, CSP and anti-frame
  headers. No cross-origin CORS access is enabled.
- Old `/api/v1/session` POST/DELETE endpoints are disabled in this mode;
  a legacy read key neither unlocks a new privilege nor exposes writes.
- The dashboard's **إخفاء العرض** action only hides private text on screen.
  It is **not an authentication lock**; refreshing opens the dashboard again.

**Privacy trade-off:** with no read key, **any locally running program that
can connect to 127.0.0.1 can read saved dashboard mail summaries**, including
private email subjects and AI suggestions. Same-user malware, desktop users,
and privileged software are not isolated by localhost. Don't bind to
`0.0.0.0`, create tunnels, port-forward, or expose the service to the LAN.
Use the optional protected mode for shared machines.

## Optional: restore read-key protection

Set `OKAL_REQUIRE_READ_KEY=1` in the **user service environment**. For a
persistent per-unit override, run `systemctl --user edit okal-core.service`
and add:

```ini
[Service]
Environment=OKAL_REQUIRE_READ_KEY=1
```

Save, then:

```bash
systemctl --user daemon-reload
systemctl --user restart okal-core.service
```

In protected mode, all private API endpoints again require a valid read token
or revocable browser cookie. The dashboard automatically reveals its pairing
form only on HTTP 401. Existing issued devices/sessions are kept in private
SQLite; the Core never creates new tokens automatically. The old CLI commands
`device-add`, `devices` and `device-revoke` still apply.

For the original no-key local mode, remove this override (or set the
environment value to `0`), reload systemd and restart the service.
Unrecognized environment values fail startup closed; only `0` and `1`
are accepted.

## Owner verification

After updating the reviewed GitHub branch:

```bash
cd /home/okal/Projects/okal
systemctl --user restart okal-core.service
systemctl --user is-active okal-core.service
curl --noproxy '*' -fsS http://127.0.0.1:8766/api/v1/health
```

In the local browser, navigate to `http://127.0.0.1:8766`. Mail triage,
Inbox Actions and saved summaries should render without a read key. It does
not fetch Gmail merely because the page was opened. The existing background
worker continues its 300-second polling cycle independently.

To inspect current mode **without printing private data**, use:

```bash
curl --noproxy '*' -fsS http://127.0.0.1:8766/api/v1/capabilities \
  | .venv-okal-core/bin/python -c 'import json,sys; x=json.load(sys.stdin); print({k:x.get(k) for k in ("local_auto_unlock","read_key_required","external_writes")})'
```

Expected default: `local_auto_unlock=True`, `read_key_required=False`,
`external_writes=False`. Protected mode returns 401 until paired.

## Scope

This change applies only to the localhost **read** dashboard. Provider token
storage, Gmail OAuth consent, CLI send confirmation, email-to-task review
proposals, and local model inference remain separate. Do not generalize
passwordless access to any future API that performs operations or writes.
