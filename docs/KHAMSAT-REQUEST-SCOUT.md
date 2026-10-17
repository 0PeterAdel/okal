# Khamsat request scout

This opt-in pilot checks the owner's chosen [Khamsat community requests](https://khamsat.com/community/requests) page once and keeps matching links in a private local queue. It does not sign in, reply, publish, or submit an offer. This community section is different from Mostaql's project bidding flow. Verify that a request is current, genuinely within your skills, and appropriate under Khamsat's community rules before writing a specific response yourself.

The account/browser profile was created on the owner's laptop by the separate freelance pilot. Do not copy that profile, cookies, or queue to Git. Close other uses of the freelance browser before scanning. If the site blocks access or changes its page structure, stop; do not automate CAPTCHA or repeatedly retry.

From the checkout containing this script, using the existing browser environment:

```bash
cd ~/Projects/okal
.venv-okal-freelance/bin/python scripts/khamsat-request-scout.py --init
${EDITOR:-nano} "$HOME/.config/okal/khamsat-watch.json"
.venv-okal-freelance/bin/python scripts/khamsat-request-scout.py --scan
.venv-okal-freelance/bin/python scripts/khamsat-request-scout.py --list
```

The private settings contain keywords and excluded terms; adjust them to services you actually deliver. The queue is `~/.local/share/okal/khamsat/queue.json` with mode `0600`. In the expanded pilot, the browser clicks the site's visible **Load more** button twice, reads the request table, asks the configured local Ollama model to shortlist at most 10 candidates against your verified work facts, opens the selected pages for their descriptions and performs a second fit check. Optional recent public comments can provide context for drafts. Adjust the limit up to 20 and the comment options in the local control page described in [KHAMSAT-AUTOREPLY.md](KHAMSAT-AUTOREPLY.md). The browser window is visible. It shares the existing persistent browser profile and lock, but never reads or prints cookies or passwords. The scout command itself remains read-only.

The timed scan and the separate reply workflow live in the follow-up pilot. Page layout and account access must still be confirmed on the owner's machine. A successful local queue is not evidence of a submitted comment or purchased service.
