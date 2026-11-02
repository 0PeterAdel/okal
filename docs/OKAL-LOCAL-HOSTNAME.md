# OKAL private hostname — `http://okal`

Owner-only localhost alias for OKAL on Omarchy (Arch Linux). This is
**not a website or LAN service**. Backend remains on
`http://127.0.0.1:8766`; a separate, low-overhead Caddy service on
**127.0.0.1:80 only** forwards requests without altering the browser's
Host or Origin headers. `/etc/hosts` maps `okal` to `127.0.0.1`.
No DNS/ACME, no public certificate, no Cloud or paid API.

## Installation after merge/deployment

1. First deploy the current OKAL `main` to the existing
   `~/Projects/okal-production` checkout with its normal **private SQLite
   backup**, fast-forward and `okal-core.service` restart. Verify
   `curl http://127.0.0.1:8766/api/v1/health` succeeds.
2. Install the open-source reverse-proxy binary once (explicit
   administrator operation):

   ```bash
   sudo pacman -S --needed caddy
   ```

3. Install from Production:

   ```bash
   cd "$HOME/Projects/okal-production"
   bash scripts/install-okal-local-host.sh
   ```

   The installer checks `Host: okal` on the existing loopback backend,
   validates Caddy config, refuses an existing port-80 listener, rejects
   conflicting hosts aliases and **does not overwrite existing changed
   system config**. It backs up `/etc/hosts` before appending a single
   `127.0.0.1 okal` line. It installs a dedicated systemd service
   `okal-local-proxy.service` with `DynamicUser`,
   `CAP_NET_BIND_SERVICE`, localhost-only IP access and an explicit
   `http://okal` virtual host. The existing Caddy service and
   `/etc/caddy/Caddyfile` are left unchanged.
4. Check:

   ```bash
   curl --noproxy "*" -fsS http://okal/api/v1/health
   sudo systemctl is-active okal-local-proxy.service
   ss -lnt '( sport = :80 )'
   ```

   The port 80 listener must be `127.0.0.1:80`, NOT `0.0.0.0:80` or a
   LAN address. Open exactly **`http://okal/`** in Firefox; no port required.
   If the browser tries a search, type the full URL including `http://`.

## Browser security + Google OAuth

OKAL's FastAPI Host allowlist now includes exactly `okal` **only from
a loopback client**. It still rejects spoofed/remote clients, unknown
hosts, cross-site Origin and unsafe Sec-Fetch-Site, and requires
explicit owner gesture for privileged actions. Caddy **does not rewrite
Origin or Host**, so the backend checks the user's genuine
`http://okal` browser origin. Strict session cookies remain host-bound:
a read-key session paired on `127.0.0.1` does not carry over to
`okal`; pair the new hostname separately if read-key mode is enabled.

Google Desktop OAuth intentionally keeps **127.0.0.1:8766** redirect URIs
when consent starts from `http://okal`, because Google accepts localhost
or loopback for Desktop app redirects, **not arbitrary `http://okal`
URIs**. After Google authorization, a one-time return may show the
`127.0.0.1:8766` address. Navigate back to `http://okal/` for daily use.
No wider OAuth scopes, callback-state bypass, token copying or Google
writes were added.

Because `okal` is not `localhost`, some browser APIs requiring a
secure context might not be available over plain HTTP. The dashboard's
existing features are designed to work over HTTP; keep direct loopback
as a fallback for any browser or OAuth issue.

## Existing owner-reported issues fixed / caveats

**FullCalendar:** previous `npm pack` output clearly included
`package/index.global.min.js`, but `tar -tzf | grep -Fxq` could produce
`SIGPIPE` under `pipefail` when `grep -q` exited early. The corrected
script lists archive members to a temporary manifest, then runs grep
independently. Once this PR is deployed:

```bash
cd "$HOME/Projects/okal-production"
bash scripts/install-fullcalendar-standard.sh
```

No additional npm package is automatically installed at browser runtime.

**Gmail `mail_operation_already_running`:** this is the deliberately
non-blocking single-owner file lock while the background Gmail worker is
processing a sync. **Do not remove the lock file or kill Ollama**. For
`mail notifications on`, either retry when the worker is idle or
explicitly stop `okal-core.service` briefly, change the local config,
then restart the service. No Gmail OAuth writes or new notifications
occur until the owner opts in.

## Review and tests

```bash
PYTHONPATH=apps/core/src python -m unittest discover \
  -s apps/core/tests -p test_local_hostname.py -v
bash -n scripts/install-okal-local-host.sh
bash -n scripts/install-fullcalendar-standard.sh
```

GitHub CI checks Python 3.12/3.14, JS, Markdown and governance.
Actual port-80 binding, Fedora/Omarchy firewall, Firefox navigation,
DBus and Google OAuth browser return require owner machine acceptance.
Do not claim `http://okal` is deployed merely because CI passes.

To disable the alias without stopping OKAL:

```bash
sudo systemctl disable --now okal-local-proxy.service
```

For persistent removal, remove only the exact appended `127.0.0.1 okal`
record from `/etc/hosts` using `sudoedit /etc/hosts`. The old
`http://127.0.0.1:8766/` remains available.
