# Optional on-demand Cloudflare Tunnel for OKAL (secure remote mode)

Issue #97. **Off by default.** Nothing in this feature creates a public
DNS record, Cloudflare Access policy, tunnel or billed Cloudflare resource.
The owner must configure their **own domain on Cloudflare** and opt in.
Do NOT expose the passwordless `https://okal/` site through a generic
Quick Tunnel. This application contains sensitive Gmail and Calendar data.

## Expected addresses

| Access mode | Example URL | Protection |
| --- | --- | --- |
| Local / offline | `https://okal/` | Loopback-only Caddy TLS with trusted owner CA |
| Remote / optional | `https://assistant.example.com/` | Cloudflare TLS + Access login + signed JWT + local owner read-key |

The external hostname is only an example. Choose a real subdomain
(e.g. `okal.your-owned-domain.tld` or `assistant.your-owned-domain.tld`)
and configure it on a domain you control in Cloudflare. The URL slug is
customizable with **Named Tunnels + your domain**. An ephemeral
`trycloudflare.com` Quick Tunnel chooses a random address and is NOT
supported as a remote OKAL security configuration.

## Cloudflare setup — owner action, not automated

1. Have an active Cloudflare domain and create a **Named, remotely-managed
   Tunnel**, e.g. `okal-private`, under Networking → Tunnels.
2. Create a **Self-hosted Cloudflare Access application** for your exact
   public hostname. Add **Allow** for only your own verified email
   (or tightly scoped own IdP). Do not add Everyone, Bypass or Service Auth
   policies. Set an appropriate short Access session lifetime. Capture
   your Cloudflare One team subdomain and the app's **Audience (AUD) Tag**.
3. In that Tunnel, publish the SAME hostname to service
   `http://127.0.0.1:8766` on this machine. Keep the public
   `Host` header intact (do NOT rewrite it to `okal`).
   Enable **Protect with Access** in Tunnel settings as defense in depth,
   select the application created in step 2, and match its AUD.
   Never route Cloudflare directly to a LAN port, never forward port 8766,
   and never disable Access JWT verification.
4. Install `cloudflared` (official package for Omarchy/Arch, version
   **2025.4.0 or newer** for the supported `--token-file` mode).
   Keep its Tunnel token private: anyone with a valid token can run that
   tunnel. Do not paste the token in ChatGPT, GitHub, shell history, or PRs.

Official references:
[Cloudflare named Tunnel setup](https://developers.cloudflare.com/tunnel/get-started/),
[Cloudflare Access apps](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/),
[Access JWT validation](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/),
[Cloudflared token-file](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/).

## Local setup after safe deployment of merged main

Do this only AFTER the public Access policy and named Tunnel are set up:

```bash
cd "$HOME/Projects/okal-production"
python3 scripts/okal-remote.py configure \
  --hostname assistant.YOUR-OWN-DOMAIN.TLD \
  --team YOUR-CLOUDFLARE-TEAM \
  --aud YOUR-ACCESS-APPLICATION-AUD \
  --email YOUR-ONLY-ALLOWED-EMAIL

# Enter the remotely-managed tunnel token at a private masked prompt.
python3 scripts/okal-remote.py token

# Owner must inspect and explicitly acknowledge Access policy first.
python3 scripts/okal-remote.py on --confirm-access-policy

python3 scripts/okal-remote.py status

# Close remote access; also restores local auto-unlock configuration.
python3 scripts/okal-remote.py off
```

Replace all uppercase placeholders. The `configure` step saves only
non-secret host, team, audience and owner email to a private 0600
`~/.config/okal/remote.env` file and installs a disabled user-systemd
`okal-remote.service`. It **does not start** any remote Tunnel.

The token action accepts it through hidden interactive TTY input and
writes `~/.config/okal/remote.token` (0600), never a command-line token.
Remote `on` creates an owner-private override for the OKAL Core user
service to enforce `OKAL_REQUIRE_READ_KEY=1` and inject the verified
Access configuration. It restarts core, tests that an unauthenticated
remote hostname yields HTTP 403 and local private API yields HTTP 401,
then starts the Tunnel. If the check fails, the override is rolled back
and the Tunnel is **not started**.

**Remote is not configured to auto-start at login.** The command
`off` stops cloudflared first, removes only OKAL's own verified drop-in,
then restarts core to restore the original local-only UI mode.
Settings/token remain private and reusable. The command `status` prints
the configured external URL and local service state, but does **not**
pretend to verify public reachability or Cloudflare authorization.

## Login when using remote OKAL

Remote requires **two independent checks**:

- Signed Cloudflare Access application JWT in the
  `Cf-Access-Jwt-Assertion` request header: verifies RS256 signature
  with pinned Cloudflare One team certificate endpoint over HTTPS, exact
  account issuer, application audience, expiration, human session subject
  and your exact owner email. Unknown/malformed/expired/not-yet-valid
  tokens, certificate fetch failure and signing key issues fail closed.
- Existing OKAL browser read-key session. Issue a browser token
  **privately on the device**, e.g.:

  ```bash
  bash scripts/run-okal-core.sh device-add remote-browser --days 7
  ```

  Pair only through your Access-protected browser at the trusted external
  hostname. Never paste the generated token into chat or share it.
  Browser session is HttpOnly, Secure and SameSite=Strict on the remote
  HTTPS hostname.

**Why a second read-key?** Even if a future Cloudflare routing error
accidentally rewrites the remote HTTP Host to the local `okal` alias,
the Core cannot expose private read APIs in passwordless mode while the
Tunnel is ON.

All Gmail, Calendar and Google Tasks OAuth connection flows still need
to run **on your laptop** at `https://okal`, with Google's own Desktop
callback to `127.0.0.1:8766`. Do not try to re-authorize Google from
a remote phone: the remote OAuth-start endpoint deliberately returns 409.

## Other cautions

- This is not end-to-end opaque encryption: Cloudflare terminates HTTPS
  at its edge, then uses its encrypted Tunnel to cloudflared on your machine,
  with only loopback HTTP from cloudflared to your FastAPI backend.
  Cloudflare operates the edge and can process HTTPS application traffic.
- Ensure you accept Cloudflare account, Access, DNS and tunnel service
  policies, quotas, limits and any possible costs. Nothing is automatically
  purchased or enabled in the Cloudflare account.
- Some OAuth-dependent or privileged features remain deliberately
  restricted to the local desktop.
- Public DNS hostname must match the exact configured hostname and
  browser HTTPS Origin; do not set `httpHostHeader=okal`.
- Do NOT enable a domain-wide Access Bypass or publicly forward local
  port 80/443/8766. If the laptop sleeps, the remote link is unreachable.

## Test expectations

```bash
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests \
  -p test_cloudflare_remote.py -v
```

Security CI mocks Cloudflare signing keys with a local RSA test key and
verifies forged, expired, wrong-audience/issuer/email, remote Host and
cross-origin rejection. Real owner Access setup, phone login and
cloudflared tunnel connection remain explicit device acceptance; no
claim of Cloudflare account integration until owner verifies.
