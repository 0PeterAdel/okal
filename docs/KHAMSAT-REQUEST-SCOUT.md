# Khamsat request scout

This opt-in pilot checks the owner's chosen [Khamsat community requests](https://khamsat.com/community/requests) page once and keeps matching links in a private local queue. It does not sign in, reply, publish, or submit an offer. This community section is different from Mostaql's project bidding flow. Verify that a request is current, genuinely within your skills, and appropriate under Khamsat's community rules before writing a specific response yourself.

The account/browser profile was created on the owner's laptop by the separate freelance pilot. Do not copy that profile, cookies, or queue to Git. Close other uses of the freelance browser before scanning. If the site blocks access or changes its page structure, stop; do not automate CAPTCHA or repeatedly retry.

From the checkout containing this script, using the existing browser environment:

```bash
cd ~/Projects/okal
.venv-okal-freelance/bin/python scripts/khamsat-request-scout.py --init
${EDITOR:-nano} "$HOME/.config/okal/khamsat-watch.json"
.venv-okal-freelance/bin/python scripts/khamsat-request-scout.py --scan
```

The private settings contain keywords and excluded terms; adjust them to services you actually deliver. The queue is `~/.local/share/okal/khamsat/queue.json` with mode `0600`. The script reads at most 10 new candidate pages in one run (adjust `--limit` up to 20), keeps previous candidates, and reports links in the terminal. The browser window is visible. It shares the existing persistent browser profile and lock, but never reads or prints cookies or passwords.

This is a first live-page probe, **not** a round-the-clock agent. Page layout and account access must be confirmed on the owner's machine. A later PR can add a restrained scheduled check, source-backed draft, duplicate guard, and verified submission flow after the operator validates the page and Khamsat's current terms. A successful local queue is not evidence of a submitted comment or purchased service.
