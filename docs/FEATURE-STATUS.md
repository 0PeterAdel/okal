# Feature status and public roadmap

Last reviewed: **November 2026**. This page describes code currently merged
into the GitHub repository, **not** a guarantee that every feature has been
accepted on every laptop, configured for every account or enabled by default.

**Legend:** Implemented = code and isolated tests exist; Optional = extra
configuration/permission; Experimental = limited, not fully validated on
other devices; Planned = not delivered as an integrated user feature.

## Current capabilities

| Area | Status | What works | What you still need to know |
| --- | --- | --- | --- |
| Chat-first UI | Implemented | Desktop responsive dark glass interface, Arabic/English chat, conversation history and resume | Reasoning accuracy is limited by the local configured model |
| Local Core | Implemented | Python/FastAPI, SQLite private state, health checks, local CLI and opt-in service | Linux/Omarchy is the main tested target; no one-click multi-OS installer |
| Cognitive Memory V2 | Implemented; rollout acceptance pending | Source-linked personal/project memory, recall, correction/forget, versioning and optional local memory adapters | See [#128](https://github.com/0PeterAdel/okal/issues/128) for release acceptance; do not assume all index/backfill checks passed |
| Ollama inference | Optional; onboarding limitation | Local pinned model use with no paid-cloud fallback | Model identity/digest requires private configuration currently associated with the Gmail module; no independent first-run wizard |
| Computer/storage | Implemented; opt-in | Files/documents, disk inventory, desktop tools, durable plans, previews, approvals and receipts | Grants default deny; desktop features require compatible Linux native tools |
| Public web reading | Implemented; opt-in | Isolated Chromium search/HTTPS page reading with source excerpts | CAPTCHAs, consent prompts and site changes can prevent live results |
| Owner terminal | Implemented; opt-in | Exact approved command `argv` executed inside a no-network sandbox | Not unlimited shell/root access; Bubblewrap and explicit user approval required |
| Local tasks/calendar | Implemented | Local tasks, reminders and scheduling | Some date/time handling remains Cairo-focused; multi-timezone UX needs verification |
| Gmail | Optional; integration | OAuth, saved inbox, read/sync, draft/review paths and guarded outgoing operations | Requires user's own Google project/consent; authorization, freshness and sending tested separately |
| Google Calendar/Tasks | Optional; mostly read integrations | Cached events and tasks, read-only sync, scheduling context | Provider setup/permissions and sync freshness depend on account |
| Morning brief | Implemented with caveats | Local saved-data summary, optional AI refresh and notifications | Stale providers and model errors must be disclosed; voice delivery not integrated |
| Secure local/remote | Optional, advanced | Loopback core, supported local HTTPS proxy and guarded named Cloudflare Tunnel workflows | Do not expose the bare HTTP service; remote setup requires an owner-managed domain and Access policy |
| Social/freelance agents | Experimental | Scripted drafts and application/research helpers | No reliable end-to-end unattended sending/posting or financial automation |
| Voice assistant | **Under development** | Separate Omarchy voice/STT/TTS lab and candidate local voices | **Not** an integrated push-to-talk/always-listening assistant in current Chat |

## Under development: Voice

The desired experience is natural Egyptian Arabic + English speaking and
listening, with local speech recognition, natural TTS and the **same**
memory, permission and Actions safeguards as Chat. Today there is a
separate experimental Voice pipeline and benchmarking scripts, **not a
production microphone control for the full assistant**. See
[Voice development status](VOICE-STATUS.md) for scope, limitations and
planned acceptance; [historical Voice lab](LOCAL-VOICE.md) contains opt-in
experiments and may require substantial downloads. Neither Core startup
nor the public service installer enables voice.

## Engineering milestones (not guaranteed release dates)

1. **Public onboarding:** portable Core startup docs, path-safe optional
   systemd installer, truthful dependency/feature matrix and user-facing
   troubleshooting.
2. **Independent local model configuration:** owner-neutral profile,
   model/digest selection and local inference health, **without** needing
   Gmail account configuration.
3. **Intelligence V3:** measurable bilingual intent handling, entity fidelity
   and grounded tool-result synthesis with citations and non-hallucinated
   current facts. Tracked by
   [#143](https://github.com/0PeterAdel/okal/issues/143).
4. **Daily workflows:** stabilize real OAuth/sync/reporting, optional
   multi-account handling and timezone/locale configuration without using
   developer defaults.
5. **Voice integration:** bounded local microphone/STT/TTS, explicit wake
   action, conversation/memory handoff, voice consent and audited execution.
6. **Cross-platform/user testing:** fresh install on multiple Linux desktops,
   security hardening and later mobile/pairing workflows.

## What OKAL is not

OKAL does not ship an open cloud AI account, a default root shell, Google
OAuth credentials, a trusted Caddy certificate, a private model, a publicly
accessible server, a production voice agent, a mobile application, or an
autonomous business/freelance bot that can act without permissions. You must
review and opt into any external service/account access.

Product behaviors should be validated against actual action receipts,
sync timestamps and observed source links. An isolated green CI run is
not proof that a model, Google account, GPU or browser works on your machine.

For installation: [Getting started](GETTING-STARTED.md). For coding:
[Contributing](../CONTRIBUTING.md).
