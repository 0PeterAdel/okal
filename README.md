# OKAL — Your Private, Local-First AI Assistant

**A chat-first personal workspace for your computer, memory, email, calendar
and everyday tasks — with real tools under your control.**

**أوكال** مساعد شخصي محلي يركز على الخصوصية: محادثة، ذاكرة للمشاريع،
تنظيم المهام، وأدوات للجهاز والويب بصلاحيات واضحة.

OKAL is an **actively developed, open-source Linux project**, not a finished
multi-platform assistant or a cloud SaaS. A local Core and user interface
work without sharing anyone else's account. More advanced features need
your **own** model, services, permissions and configuration.

## Interface preview

![OKAL chat-first personal assistant desktop interface](docs/assets/okal-chat-interface.webp)

*Actual OKAL desktop screenshot (November 2026). It illustrates the
Liquid Glass interface, not a promise that all integrations or Voice are
active on a fresh installation.*

## What can OKAL do?

| Capability | Current availability |
| --- | --- |
| **Chat-first workspace** | Bilingual Arabic/English conversation, persistent history, conversation resume |
| **Cognitive Memory V2** | Project context, saved knowledge, source-linked recall, correction and forgetting; release acceptance still ongoing |
| **Local AI via Ollama** | Explicitly configured local pinned model; no paid/cloud AI fallback. First-time model onboarding still needs work |
| **Computer Actions** | Owner-granted file/document operations, Linux storage status, desktop commands with typed plans, approvals and verified receipts |
| **Web search and reading** | Optional public HTTPS browsing via isolated Chromium; permissions and live network required |
| **Terminal** | Exact user-requested, approval-bound commands inside an isolated sandbox; **not** an unrestricted shell |
| **Daily workspace** | Local Tasks, Calendar, reminders and a brief based on available evidence |
| **Google integrations** | Optional Gmail and Google Calendar/Tasks workflows; your own OAuth setup and actual sync verification required |
| **Remote access** | Optional guarded local HTTPS and Cloudflare Access/Tunnel setup, never enabled by default |
| **Voice** | **Under development** — separate research/STT/TTS lab, **not yet integrated into the full Chat assistant** |

See the complete [feature matrix and roadmap](docs/FEATURE-STATUS.md)
for what's implemented, experimental, planned or limited.

## Quick start — Linux

Current main development target: **Arch Linux / Omarchy** with Python
**3.12**. Other Linux distributions need extra verification. The Core
uses a Python environment separate from the experimental Voice package.

```bash
git clone https://github.com/0PeterAdel/okal.git
cd okal

python3.12 -m venv .venv-okal-core
.venv-okal-core/bin/python -m pip install --require-hashes \
  -r apps/core/requirements-actions.lock

bash scripts/run-okal-core.sh init
bash scripts/run-okal-core.sh serve
```

Open **<http://127.0.0.1:8766>** on the same computer. Press
**Ctrl+C** in the terminal to stop the foreground service.

This is a **safe local Core trial**, not full AI onboarding: the interface
and local tools can work with no provider account, but model-powered Chat
needs an owner-configured pinned Ollama model. Today that model pin is
stored in the private Gmail-module configuration. A standalone,
mail-independent first-run model wizard is **not implemented yet**.
OKAL neither pulls models nor connects Google accounts automatically.

**Before configuring an account, model, system service or remote
endpoint, read the [full installation and first-run guide](docs/GETTING-STARTED.md).**

## Run at login — optional

After a successful foreground trial, Linux users can install a portable
user-systemd unit:

```bash
bash scripts/install-okal-user-service.sh
systemctl --user daemon-reload
systemctl --user enable --now okal-core.service
```

The installer chooses your checkout path, **does not start or enable**
anything by itself, and refuses to overwrite an existing customized
unit. To stop and disable the login service:

```bash
systemctl --user disable --now okal-core.service
```

This stops **OKAL**, not a separately running Ollama server/proxy.
No model is automatically loaded by Core installation.

## Privacy and permissions

- Local Core binds to `127.0.0.1`. **Do not forward the HTTP port**
  to the internet or a LAN. [Remote access](docs/OKAL-REMOTE-CLOUDFLARE.md)
  requires an explicit, independently secured configuration.
- Private SQLite, tokens, email data, model configuration and backups
  live outside Git. Nothing personal is packaged in the public repository.
- Computer, browser and terminal tools start with **no grants**.
  You choose precise scopes in the Actions panel; consequential
  operations require exact owner approval. A model cannot approve itself.
- Live searches and Google OAuth send information to their respective
  external providers **only after your explicit setup/actions**.
  Core's local LLM does not automatically switch to a paid cloud service.
- Persistent memory is versioned and owner-controlled, but safe operation
  depends on correct local state, backups and model/provenance validation.

More detail: [Security policy](SECURITY.md),
[Computer Actions](docs/COMPUTER-ACTIONS.md), and
[Cognitive Memory](docs/COGNITIVE-MEMORY.md).

## Voice: under development

Our goal is natural Egyptian Arabic + English voice conversation with
local transcription, high-quality speech output, context retention and
the **same controlled permissions** as typed chat.

The repository contains a **separate experimental Voice lab**, but
**the current Core Chat does not ship a complete microphone-to-assistant
experience**. Voice is off by default; no normal Core setup starts
recording or downloads a voice model.

Read the [Voice development status](docs/VOICE-STATUS.md) and optional
[Voice lab notes](docs/LOCAL-VOICE.md). The top-level `pyproject.toml`
packages **this experimental Voice lab**, not the Core.

## Project status, help and contributing

- [Getting started](docs/GETTING-STARTED.md) — dependencies,
  installation, foreground/background operation and troubleshooting.
- [Feature status & roadmap](docs/FEATURE-STATUS.md) — available features
  and what is still being developed.
- [Development guidelines](CONTRIBUTING.md),
  [governance](GOVERNANCE.md), [third-party notices](THIRD_PARTY_NOTICES.md),
  [license](LICENSE).
- [Issues](https://github.com/0PeterAdel/okal/issues) — bug reports and
  feature requests; never include credentials or private conversations.

**Known work in progress:** improving model onboarding for new users,
bilingual intelligence and source-grounded answers
([#143](https://github.com/0PeterAdel/okal/issues/143)), provider freshness,
Voice integration and acceptance on more Linux systems.
The [Cognitive Memory V2 production release checklist](https://github.com/0PeterAdel/okal/issues/128)
is specific to a rollout; it is not a preinstalled feature or a reason
to migrate a new user's SQLite database by hand.

OKAL is licensed under the [MIT License](LICENSE). Third-party models,
Python libraries and online providers retain their own licenses and terms.
