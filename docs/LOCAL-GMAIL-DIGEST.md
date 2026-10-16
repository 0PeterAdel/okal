# Local Gmail daily digest

This runs entirely on the owner's machine. The Gmail API grant is **read-only**; Okal writes no message, label, or reply. Inbox message IDs are paginated and fetched in full since the last successful digest. Text is summarized by the local Ollama model. Private Markdown reports live in `~/.local/share/okal/gmail-digest/`.

1. In Google Cloud, enable Gmail API, configure OAuth consent for your account, and create a **Desktop app** OAuth client. Download its JSON and place it at `~/.config/okal/gmail-client.json` with mode 0600. If the consent screen is in Testing mode, check whether its refresh token expires and switch to the appropriate authorized configuration before relying on daily unattended runs.
2. Create `~/.config/okal/gmail-digest.json` with mode 0600, e.g. `{"expected_email":"you@example.com","ollama_model":"okal-qwen3.5-4b-64k"}`. Check the address; Okal refuses a different account.
3. In the checkout, set up and authorize once in your own browser:

```sh
python3 -m venv .venv-okal-gmail
.venv-okal-gmail/bin/python -m pip install google-api-python-client google-auth-oauthlib
chmod 600 ~/.config/okal/gmail-client.json ~/.config/okal/gmail-digest.json
.venv-okal-gmail/bin/python scripts/okal-gmail-digest.py --authorize
.venv-okal-gmail/bin/python scripts/okal-gmail-digest.py --digest
```

Inspect the path printed by `--digest`, its full message index and summary. The first run covers the preceding 24 hours; later runs cover the period since the previous **successful** report, including downtime. Mail body excerpts are limited to 2500 characters per message sent to local Ollama, while every message gets an index entry. Attachments are not interpreted. HTML-only mail is converted to text locally. Do not expose report or OAuth token to Git, cloud agents or journal logs.

After checking one report, install the local user timer for 20:00 Africa/Cairo:

```sh
install -Dm644 systemd/user/okal-gmail-digest.service ~/.config/systemd/user/okal-gmail-digest.service
install -Dm644 systemd/user/okal-gmail-digest.timer ~/.config/systemd/user/okal-gmail-digest.timer
systemctl --user daemon-reload
systemctl --user enable --now okal-gmail-digest.timer
systemctl --user list-timers okal-gmail-digest.timer
```

The unit assumes `~/Projects/okal` and a running local Ollama. A laptop that is off at the scheduled time runs after the next login; it cannot monitor messages while powered off. `systemctl --user disable --now okal-gmail-digest.timer` stops it.
