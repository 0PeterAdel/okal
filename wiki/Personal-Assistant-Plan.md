# Personal Assistant Plan

**Date:** 2026-10-29. **Status:** proposed, tracked in
[issue #36](https://github.com/0PeterAdel/okal/issues/36).
No new runtime, startup service, connector or mobile application is implemented
by this documentation reset.

Implementation checkpoint (2026-10-30): R0 merged via PR #37. The bounded R1a
trial in [issue #38](https://github.com/0PeterAdel/okal/issues/38) adds a local-only
inbox, read tokens and responsive shell; see [Core Inbox](../docs/CORE-INBOX.md).
R1a is not full R1 acceptance: phone TLS/pairing and owner boot/lifecycle tests
remain pending. The endpoint and dependency proposals below describe the full
target; the runbook identifies the narrower implemented contract.

## Scope and authority

One owner, one laptop, one center. Four workflows: mail, planning, social and
freelance. Mobile/desktop are clients, not independent agents. Voice is deferred.

Out of scope: coding agents, research swarms, model training, generic shell tools,
self-modifying workflows, enterprise tenancy, marketplaces and vector/graph memory.

The center owns requests, schedules, runs, summaries, device permissions, approvals,
duplicate guards and a global pause for external writes. Feature modules call
bounded provider adapters. Neither adapters nor model outputs authorize actions.

## Code-first foundation

Propose a Python modular monolith using FastAPI/Pydantic, local SQLite and an
APScheduler scheduling adapter. Ollama supplies local inference. These are
candidates, not newly installed or pinned dependencies in this PR.

| Proposed location | Responsibility |
|---|---|
| `apps/core/` | API, state, bounded workflow runner and scheduler |
| `apps/core/modules/` | Mail, planning, social and freelance workflows |
| `apps/core/adapters/` | Gmail, calendar, publisher, Khamsat and Ollama clients |
| `apps/mobile/` | Thin summary/status client; no provider credentials |
| `contracts/` | Versioned API contracts and fixtures |
| `deploy/` | Reviewed service lifecycle and migration tools |
| `tests/` | Authorization, recovery and connector tests |

These directories describe the next implementation, not an existing runtime.
Do not rename the installed voice package or move its files without migration.

## Reuse and alternatives

| Component | Decision | Reason |
|---|---|---|
| [FastAPI](https://github.com/fastapi/fastapi) | Evaluate API foundation | Python baseline, typed contracts, MIT |
| [APScheduler](https://github.com/agronholm/apscheduler) | Evaluate scheduling library | Reuse time calculations; not an external-write reliability solution |
| [n8n](https://github.com/n8n-io/n8n) | Optional later | Good connectors; avoid a second state/scheduling authority |
| [Activepieces](https://github.com/activepieces/activepieces) | Alternative | MIT core, separate runtime not yet justified |
| [Prefect](https://github.com/PrefectHQ/prefect) | Defer | Useful Python orchestration; unnecessary separate layer for first slice |
| [Shoutrrr](https://github.com/coollabsio/shoutrrr) | Evaluate publisher | REST API and calendar; inspected at v1.5.8, not deployed |
| [Google API Python client](https://github.com/googleapis/google-api-python-client) | Evaluate account client | Reuse official API/auth components |
| Existing Khamsat scripts | Salvage after review | Real discovery and duplicate/pending guards already explored |

n8n is not technically incompatible with mobile. The code-first choice is about
keeping the custom inbox, device permissions and durable run state in one tested
Python boundary. It costs more initial work than a Gmail-only n8n flow. Limit the
center to the first delivery slice; reconsider if it becomes a general framework.

Before adoption record exact versions/digests, direct/transitive licenses, security
review, destinations, resource measurements and replacement plan. No benchmark is
implied here. No whole upstream repository is copied into Okal.

## Persistent state and recovery

Start with devices, account references, schedules, runs, steps, summaries and
approvals. Keep OAuth secrets outside normal payloads/logs. Store instants in UTC,
and schedules with IANA zones; owner default is Africa/Cairo.

Only one scheduler process may claim work. Enforce a database uniqueness key for
workflow, account and scheduled occurrence. Use library triggers, not custom cron
parsing. Scheduler state alone never proves that an external action happened.

Persist a step and its action digest before an external write. Run states include
queued, running, awaiting_approval, succeeded, failed, cancelled and
needs_reconciliation. Use provider idempotency where available. Otherwise an
ambiguous result blocks resubmission until native-state reconciliation.
Do not claim exactly-once delivery from a scheduler.

After restart, retry read-only work with bounds. Coalesce missed digests into one
interval since the last successful checkpoint. Never catch up expired posts,
proposals or approvals by silently sending them. Interrupted writes need native
message/post/comment IDs checked before a retry.

If Shoutrrr owns a post's schedule, Okal records the external post ID and observes
its status. Okal does not schedule a second publication directly to the provider.

## Shared mobile and voice boundary

The first mobile release is a responsive web app/PWA showing summaries, task
status, last successful sync and connection state. Native Android is optional
later. Offline cached data shows its age; background push is not promised until
a transport has been selected and tested.

Proposed versioned API (not implemented):

| Endpoint | Purpose | Access |
|---|---|---|
| `GET /api/v1/health` | Liveness only, no account details | Minimal loopback response |
| `GET /api/v1/summaries` | Cursor-paginated unified inbox | Paired read-only device |
| `GET /api/v1/runs/{id}` | Redacted status and result | Paired read-only device |
| `GET /api/v1/capabilities` | Allowed operations and readiness | Authenticated |
| `POST /api/v1/requests` | Typed allowlisted workflow | Separate execute permission, later |
| `POST /api/v1/approvals/{id}/decision` | One-use exact-action approval | Separate approve permission, later |

Requests carry schema version, request ID, idempotency key, allowed operation,
validated arguments and expiry. Device identity comes from authentication, not
the request body. Voice/text source is metadata, never permission. No arbitrary
shell command, tool name or URL is accepted as an operation.

Pairing uses a short-lived one-use code displayed locally. Device tokens are
scoped, revocable, rate-limited at pairing and not logged or placed in URLs.
Store token verifiers server-side. Approvals bind exact account, destination,
payload digest and expiry; any draft edit invalidates the previous approval.

The phone never receives provider tokens or browser cookies. Require TLS before
non-loopback exposure, host/origin restrictions and application authentication.
Start with a reviewed LAN connection; VPN access is optional and separately
onboarded. Do not expose the raw API through router port forwarding.
A VPN is not a replacement for application authentication.

## Automatic startup

Target one unprivileged user unit, `okal-core.service`. Login startup and boot
startup are different tests. Boot-before-login requires explicit user lingering
and owner-device verification. Encrypted home availability can prevent early boot
startup. Browser adapters may need a graphical login/unlocked profile and must
report waiting_for_session instead of blocking the whole center.

Use restart-on-failure with bounded backoff, private state, explicit working
directory, graceful shutdown and least privilege. Start the core even when the
network/model is unavailable, marking affected workflows blocked/retrying.
Serialize heavy inference; never fall back silently to cloud AI.

No unit is enabled by this PR. The installation PR must test cold boot, login,
logout, crash, suspend/resume, offline operation, backup/restore and uninstall.
The laptop cannot work while powered off. Recovery is not uninterrupted uptime.
Disable only exact replaced legacy schedules after their replacement passes.

## Privacy and controlled writes

- Incoming mail/listings are untrusted data, never policy instructions.
- The model cannot approve itself, change permissions or invent owner credentials.
- Begin read-only, then reviewed writes. Unattended authority is explicit per
  workflow/account with content/destination rules, limits, expiry and pause.
- Keep secrets outside Git, mobile responses, model prompts and ordinary logs.
- Define source/report retention and deletion per module.
- X API cost remains a blocker under the zero-paid-services requirement.
- Freelance submission needs platform permission and native outcome verification.
- Local inference does not make external email/social/calendar services offline.
- The calendar provider is an onboarding choice, not an implicit upload of local data.

## Delivery order

One active implementation PR at a time. Later rows are backlog, not parallel work.

| Stage | Deliverable | Exit evidence |
|---|---|---|
| R0 | Repository reset and ADR | Reviewed docs, preserved branch inventory |
| R1 | Core, durable inbox, read-only mobile shell, startup | Auth denial, pagination, recovery and owner boot tests |
| R2 | Real Gmail digest | Correct account, complete chosen interval, source links, local inference, no duplicates |
| R3 | Reviewed send and planning | Exact-recipient preview, native receipt, availability and no duplicate event |
| R4 | Social publisher adapter | Approved text, account/time readback, post URL and confirmed provider cost |
| R5 | Khamsat opportunities/proposals/follow-up | Real listings, verified facts, review, no duplicate submissions; notification coverage declared |
| Later | Mostaql, voice and native mobile extras | Earlier workflows accepted in daily use |

R1 is a small foundation, not months of generic kernel work. Label its fixtures
as fixtures, never real mail. R2 is the first useful real-data slice. Retain #33's
tests but explicitly decide whether archived incoming messages are included;
the old inbox-only filter must not masquerade as complete mailbox coverage.

## Evidence limits

Source review only: no laptop install, account authorization, sending, model
benchmark or mobile connection was performed. The owner's checkout
`/home/okal/Projects/okal` is not mounted in this session.
Read the [reset runbook](../docs/REPOSITORY-RESET.md) before local cleanup.
