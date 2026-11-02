# OKAL local HTTPS — trusted private address

## Purpose

The **default owner URL** is now `https://okal/`. Firefox should show a
secure connection **after** the owner explicitly trusts OKAL's **public**
local root CA. The loopback backend is still
`http://127.0.0.1:8766/` for internal operation and Google Desktop OAuth.

The Caddy frontend listens only on `127.0.0.1:443` and performs a local
HTTP `127.0.0.1:80` → HTTPS 308 redirect. Both are non-LAN. It uses
`tls internal`: no public certificate authority, domain purchase, network
requests to ACME, or external cloud services are needed.

The CA private signing material is persisted across logins in Caddy's
restricted systemd `StateDirectory` (`/var/lib/okal-local-proxy`), **not**
the former temporary RuntimeDirectory. The installer exports **only the
public root CA certificate** into the owner's private files and does not
make its private signing keys accessible to Firefox or other processes.

## Owner-controlled upgrade on Omarchy

After normal GitHub-reviewed merge and private SQLite backup, update the
`okal-production` checkout to new `main`, restart `okal-core.service`,
then run:

```bash
cd "$HOME/Projects/okal-production"
bash scripts/upgrade-okal-local-https.sh
```

The script requires existing `caddy`, `ss`, `curl` and sudo; it validates
the new config and compares existing system configs against the known
previous, repo-managed HTTP configuration. Unknown/manual changes trigger
a **STOP**, not an overwrite. It creates protected backups under
`/etc/okal-https-backup-XXXXXXXX`, refuses an unrelated occupied port
and verifies TLS identity with `curl --cacert` (never `curl -k`).

If Caddy is not installed yet:

```bash
sudo pacman -S --needed caddy
bash scripts/install-okal-local-host.sh
```

The old installation script now delegates to the HTTPS installer.

## Remove Firefox's "Not Secure" warning

On the host machine, after installation, find the exported **public**
root CA:

```bash
echo "$HOME/.local/share/okal-certs/okal-local-ca.crt"
```

Firefox → Settings → Privacy & Security → Certificates → View Certificates
→ Authorities → Import → choose the exported `okal-local-ca.crt` →
allow this CA to identify websites. Restart Firefox or reopen the tab,
then visit **`https://okal/`**.

A local CA is trusted only on the device/browser where the owner imports
it. It is **not** a publicly trusted certificate and does not make the
machine available externally. Do not click "Accept risk" on an untrusted
certificate; verify you imported the correct local root. If the CA is
rotated, review and manually trust the new public certificate.

System trust via Arch's `trust anchor` is a possible alternative but may
not change Firefox's independent NSS store; Firefox import is explicit
and deterministic. The CA trust affects certificate trust for that root:
only import the CA you own, never arbitrary downloaded roots.

## Security contract

- Custom browser `Origin` is exclusively `https://okal`, even though
  the internal reverse-proxied request to FastAPI arrives via HTTP.
- Existing `http://127.0.0.1:8766` and `http://localhost:8766` origins
  remain valid for **local** use.
- All three Desktop Google OAuth flows continue redirecting to the
  official `http://127.0.0.1:8766` loopback callback. A browser may
  temporarily navigate there during consent.
- Read-key authenticated browser pairing sets `Secure; HttpOnly;
  SameSite=Strict` for cookies at `https://okal`.
- Custom Host still requires a loopback TCP client; no forwarded host
  is trusted, and cross-origin POSTs continue to fail closed.
- The plain HTTP site on port 80 only redirects and serves NO dashboard
  data. Do not publish or port-forward either port.

## Troubleshooting and rollback

```bash
sudo systemctl status okal-local-proxy.service --no-pager
ss -lnt '( sport = :80 or sport = :443 )'
curl --noproxy '*' --cacert "$HOME/.local/share/okal-certs/okal-local-ca.crt" \
  -fsS https://okal/api/v1/health
```

If Caddy fails or Firefox trust is not yet installed, the direct
`http://127.0.0.1:8766/` remains the local fallback. This is loopback-only,
not an excuse to forward that port to the internet. To stop the proxy,
`sudo systemctl disable --now okal-local-proxy.service`. System config
backups are printed by the upgrade script; restore only after reviewing
them. Never delete the CA signing keys unless intentionally resetting
all trusted local devices and certificates.

This issue covers **local HTTPS only**; a remote Cloudflare Tunnel is a
separate opt-in, authenticated feature and MUST NOT expose this
passwordless local origin as a public website.
