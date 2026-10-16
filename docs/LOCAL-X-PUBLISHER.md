# Local X publishing

This task runs on the owner's machine. It sends a real post with the official `POST /2/tweets` API and X user-context OAuth 1.0a credentials. X prohibits scripting its website to automate posts. A developer app with write permission and API access is required and may incur X API costs. No browser profile or ChatGPT automation is used.

1. In X's developer console, create/configure an app with **Read and write** user permissions, then obtain its API key/secret and **user** access token/secret. The application-only bearer token cannot publish for your account.
2. Create `~/.config/okal/x-user-keys.json` with `consumer_key`, `consumer_secret`, `access_token`, `access_token_secret`; run `chmod 600` on it. Keep it out of Git and terminal output.
3. Create `~/.config/okal/x-publisher.json` as below and `chmod 600` it. Each fact must be verified by the owner and safe to publish. The model must reproduce it literally; other content remains your responsibility.

```json
{
  "enabled": true,
  "ollama_model": "okal-qwen3.5-4b-64k",
  "facts": [{"text": "أعمل على مشاريع Python وتحليل البيانات."}]
}
```

Run `python3 scripts/okal-x-publish.py --dry-run` to inspect the day's generated post. Run without that flag to publish once immediately; `--status` prints the local receipt. After a successful real post, install the timer:

```sh
install -Dm644 systemd/user/okal-x-publish.service ~/.config/systemd/user/okal-x-publish.service
install -Dm644 systemd/user/okal-x-publish.timer ~/.config/systemd/user/okal-x-publish.timer
systemctl --user daemon-reload
systemctl --user enable --now okal-x-publish.timer
```

The unit assumes the checkout is `~/Projects/okal`; edit `ExecStart` for another path. The timer fires at 10:00 Africa/Cairo if the laptop is running, or after the next login if missed. A failed or ambiguous API call leaves a `pending` receipt and prevents another automatic attempt that day; inspect your X profile and private receipt before manually resetting it. Credentials and receipts remain local (mode 0600); timer logs do not contain post text or keys. Disable with `systemctl --user disable --now okal-x-publish.timer`.
