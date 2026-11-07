# Getting started with OKAL

This guide is for a **new Linux user** who wants to try the local Core
without importing anybody else's database, tokens, settings or models.
The current development/test target is **Arch Linux / Omarchy with systemd**.
Other Linux distributions may work with compatible dependencies, but are not
yet accepted as supported installs. Windows, macOS and Android/iOS apps are
not released. This is an actively developed project, **not a one-click app**.

## 1. Prerequisites

- Linux desktop, Git, Python **3.12** with `venv` and `pip`, and a browser.
  Python 3.14 is exercised in Core CI; Python 3.12 is the simpler shared
  starting point. The separate Voice package supports Python 3.12/3.13.
- An internet connection is needed **once** to download Python packages.
  Gmail, Google Calendar, live web search, optional models and Chromium
  installation need additional network access/explicit consent.
- `systemd --user` is needed only for the **optional** login-start service.
  Foreground Core operation does not require enabling systemd.
- Optional: locally installed Ollama for model-powered conversation,
  `bubblewrap` for sandboxed computer commands, `pdftotext` for PDF text,
  and Playwright-managed Chromium for governed web tools.
- Hardware needs depend on the local Ollama model. No GPU is required merely
  to serve the basic web UI; capable CPU/RAM/GPU are required for reasonable
  model performance. Nothing in the installer downloads model weights.

## 2. Fresh clone and Core environment

Use a **new empty checkout**, not someone else's Production state:

```bash
git clone https://github.com/0PeterAdel/okal.git
cd okal
python3.12 -m venv .venv-okal-core
.venv-okal-core/bin/python -m pip install --require-hashes \
  -r apps/core/requirements-actions.lock
bash scripts/run-okal-core.sh init
```

The Actions lock includes the Core and optional computer-browser Python
adapter dependencies. Runtime setup still requires external native binaries
for some tools. Do not run the repository-root `pip install .` expecting
it to install Core: the root `pyproject.toml` packages the **separate
experimental Voice lab**, not the Core.

A fresh installation creates a private local state directory at
`$XDG_STATE_HOME/okal-core` or `~/.local/state/okal-core`. It
does **not** copy the developer's conversations, initialize Gmail, pull an
Ollama model, grant desktop/browser tools, install a service or start a
Cloudflare Tunnel.

## 3. Start in the foreground

```bash
bash scripts/run-okal-core.sh serve
```

Open **<http://127.0.0.1:8766>** in a browser on the **same machine**.
To stop OKAL, press **Ctrl+C** in the foreground terminal. Its data stays
in the private SQLite state directory.

If port 8766 is already used, choose another loopback port:

```bash
bash scripts/run-okal-core.sh serve --port 8876
```

The current Core uses the same-owner local browser boundary on loopback;
it is **not safe to expose this local HTTP port on the LAN or internet**.
To enforce browser read-key login locally when needed, set
`OKAL_REQUIRE_READ_KEY=1` **before starting**, then issue a private device
token with `bash scripts/run-okal-core.sh device-add desktop`. Do not
paste a token into tickets or shared logs. See the
[Core security model](CORE-INBOX.md) and
[remote-access guide](OKAL-REMOTE-CLOUDFLARE.md) before considering remote access.

## 4. Getting actual AI replies

A fresh clone may show the UI and local-data workflows **without useful
model-generated answers**. Current model-powered Chat uses an **existing
private Gmail-module model configuration** containing an Ollama model name,
verified model SHA-256 digest and a local-only confirmation. The present
Core does **not** have a separate first-run, mail-independent model
onboarding wizard. This is a known public-onboarding limitation; see
[feature status](FEATURE-STATUS.md). Do not invent an email account or
paste other people's Gmail configuration just to bypass it.

For now, model configuration is intended for experienced operators who
review [Gmail backend and local model configuration](MAIL-BACKEND.md)
and [AI architecture](INTELLIGENCE-CORE.md). Ollama must be installed,
running locally and have the exact model/digest explicitly approved.
OKAL **never automatically downloads a model** and cannot use a paid
cloud LLM fallback. Failure to configure inference should yield a
labelled local fallback, not a claim of a successful model conversation.

```bash
ollama list
ollama ps
```

These two diagnostic commands inspect Ollama only; they do not configure
OKAL or authorize it to use a model.

## 5. Optional capabilities

Open **Chat → Tool permissions / Actions**. No computer or website tool
is authorized by default. Grant only the minimum exact capabilities
you intend to use and review each receipt. For example, `system.status`
can read disk/device sizes, while public web search needs both
`browser.search` permission and working isolated Chromium. A
`system.terminal` invocation is an explicit owner command, confined
to a no-network sandbox with **separate exact approval**, not a root shell.
See the [Actions capability guide](COMPUTER-ACTIONS.md),
[storage](CHAT-SYSTEM-DIAGNOSTICS.md),
[web](CHAT-PUBLIC-WEB.md) and
[terminal](CHAT-OWNER-TERMINAL.md).

Google accounts are **optional** and are not configured during Core setup.
For Gmail/Calendar, follow the specific
[Gmail connection](GMAIL-ONE-CLICK-CONNECT.md) and
[Google Calendar](CALENDAR-ONE-CLICK-CONNECT.md) guides, create your own
Google Desktop OAuth client and keep its JSON/private tokens **outside Git**.
The UI may display saved/cached provider data; verify sync freshness before
assuming it is current. Real sends and destructive actions require their
specific policy and review. No OAuth secrets or user data are bundled.

## 6. Optional launch at login (systemd)

Only after the **foreground launch succeeds**, on a system with systemd
user services:

```bash
bash scripts/install-okal-user-service.sh
systemctl --user daemon-reload
systemctl --user enable --now okal-core.service
systemctl --user status okal-core.service --no-pager
```

The installer **does not enable or start OKAL by itself**. It uses the
current checkout path rather than assuming a developer directory. It refuses
to overwrite a different existing unit, and reports unsupported paths.
If you already operate a customized OKAL service, **do not replace it**:
inspect its drop-ins and running processes first.

To stop the background service and disable login startup:

```bash
systemctl --user disable --now okal-core.service
systemctl --user is-active okal-core.service
systemctl --user is-enabled okal-core.service
```

You should see `inactive` and `disabled`. This does **not** stop a
separately installed `ollama serve`, Ollama proxy, Cloudflare Tunnel or
other unrelated processes. `ollama ps` reports whether models are loaded.
Never disable Ollama globally without checking whether another app uses it.

## 7. Data, backup and upgrades

The private SQLite database and account configuration live **outside
this Git repository**. A `git pull` never backs up your personal data.
Never commit `~/.local/state/okal-core`, tokens, private model config,
OAuth JSON or conversation exports.

Use the reviewed online-backup and release procedures in
[Cognitive Memory V2 rollout](COGNITIVE-MEMORY-ROLLOUT.md) before
changing an existing installation. Do **not** copy a donor's database
or replay a schema migration: schema 2 may already be live. Never
overwrite a running SQLite database with an old backup. Existing
custom services and units are not automatically changed by cloning Git.

## 8. Troubleshooting

| Symptom | Safe first check |
| --- | --- |
| `Core environment missing` | Verify `.venv-okal-core/bin/python` exists and the lock installation succeeded |
| Port unavailable | Use `ss -lnt '( sport = :8766 )'` and a different loopback port |
| Chat answers look generic | Check your own model pin/config and Ollama with `ollama list`; no automatic model download |
| Actions denied | Review the exact permission in **Chat → Actions**, never disable the policy wholesale |
| Web search fails | Check Chromium installation, DNS/network, and consent/CAPTCHA in the isolated profile |
| Gmail/Calendar looks stale | Revisit that provider's OAuth/sync status; cached data is not proof of a fresh sync |
| Voice doesn't appear in Chat | Correct: integrated Voice is **under development**, see [Voice status](VOICE-STATUS.md) |
| systemd installer refuses | Existing unit differs or path contains unsupported characters; do not force overwrite |
| No service process | Foreground Core exits on Ctrl+C; systemd service is optional and opt-in |

For reproducible bugs, include your distro, Python version, **redacted**
error message, and the feature/steps affected. Do not post SQLite, emails,
logs containing tokens, OAuth files, personal conversations or model secrets.
Use [GitHub Issues](https://github.com/0PeterAdel/okal/issues) and the
[security policy](../SECURITY.md) when appropriate.
