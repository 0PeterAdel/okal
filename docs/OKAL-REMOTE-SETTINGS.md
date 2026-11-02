# OKAL Remote Settings: owner-only UI controls (draft)

The existing command-line Cloudflare remote mode remains the authority.
**Remote is OFF by default.** Nothing in this feature provisions Cloudflare
DNS, domains, Access apps, or a named tunnel. Never expose the unsecured local
dashboard using an unauthenticated Quick Tunnel.

## Before the ON button can work

1. Deploy the trusted local HTTPS release and verify `https://okal/`
   after importing the public Caddy root CA into Firefox Authorities.
2. Follow [Cloudflare setup](OKAL-REMOTE-CLOUDFLARE.md): configure owner-only
   Access, named Tunnel, explicit hostname, AUD and private token using CLI.
3. Open a **private terminal on the laptop**, not the public remote browser:
   `cd ~/Projects/okal-production && python3 scripts/okal-remote.py ui-key`
   This displays a **one-day separate UI control key** once. It is hashed
   on disk, never added to the repo or sent to Cloudflare. Do not save it in
   browser storage or paste it in a shared chat.
4. From local `https://okal/#settings-section` enter that control key,
   confirm verified owner-only Cloudflare Access policy, and press
   **تشغيل الوصول الخارجي**.
5. Recheck status and independently verify protected public login from another
   network. The UI's "accepted" is not evidence of public reachability.
6. Use **إيقاف الوصول الخارجي** to stop it; a fresh key is required if the
   previous key expired. Emergency terminal fallback always exists:
   `python3 scripts/okal-remote.py off`.

## Security constraints

- The toggle route is **POST + same-origin JSON + local host okal only**.
  Even paired remote Cloudflare Access users cannot invoke it.
- In addition to usual local browser security, the toggle validates a
  **distinct 256-bit owner control key** against a local owner-only hashed file
  with a 24-hour expiry. Ordinary dashboard read keys cannot toggle remote.
- This is a single-user device control. It does not protect against a process
  already running malicious code as the same Linux owner.
- The only executable command is an exact, fixed `systemd-run --user` request
  to the repository's `scripts/okal-remote.py on/off`, **no shell** and no
  browser-supplied CLI arguments. That command runs in its own user service
  so restarting `okal-core.service` does not kill itself.
- Original CLI checks still enforce token-file permissions, Access JWT gate,
  OKAL read-key when enabled, and fail-closed rollback.
- No auto-start at boot. New UI returns the configured HTTPS URL but **does
  not** claim it is reachable or authenticated until live owner validation.
- Caddy stays loopback-only and no router ports are opened.

## Validation

```bash
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests \
  -p test_remote_ui.py -v
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests \
  -p test_cloudflare_remote.py -v
```

Before merge: all GitHub required checks, Solo owner self-review on current
head SHA, manual rollback test, and Firefox UI/Tunnel tests on Omarchy. No
live Cloudflare account changes are performed from CI.
