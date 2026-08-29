# Automation, Channels, and Integrations

## Deterministic automation first

Schedules, webhooks, retries, branching, and API transformations should be typed
workflows. An agent may design or repair a workflow, but recurring production
execution uses a pinned reviewed definition.

## Workflow roles

- Native Okal steps for task, policy, memory, and evidence semantics.
- A database-backed durable queue for the MVP.
- Temporal as the preferred long-term durable execution provider.
- Activepieces or Node-RED as optional visual automation surfaces.
- n8n is not a core dependency because its Sustainable Use License conflicts with
  the project's strict FOSS preference.

## Channel strategy

The web/desktop UI and CLI are first-party surfaces. OpenClaw may provide optional
messaging and device gateway adapters. Telegram is the first external chat target
after the local UI; additional channels require demand and security evaluation.

## Integration priorities

| Priority | Integration | Purpose |
|---|---|---|
| P0 | Local files and shell sandbox | Foundation execution |
| P0 | GitHub | Repositories, issues, PR context and drafts |
| P0 | Jira | Assigned work, review state, acceptance context |
| P0 | Web search/retrieval | Research with source provenance |
| P1 | Telegram | Mobile conversation and notifications |
| P1 | Calendar and tasks | Briefings, reminders, planning |
| P1 | Email read and draft | Context and controlled communication |
| P2 | Drive/document stores | Knowledge ingestion |
| P2 | Slack/Discord | Team interaction |
| P3 | Smart-home/device nodes | Physical-world actions with stronger policy |

## Credential boundary

Connectors receive scoped tokens through the secret broker. Read and write scopes
are separate. Okal records the effective identity and permission set without
logging credentials. Revocation is immediate for new dispatch and reconciled for
active work.

## Schedules

A schedule stores owner, purpose, cadence/trigger, timezone, bounded task
template, budgets, expiry, notification policy, and failure policy. It can be
listed, paused, resumed, edited, or removed. Every run receives a new task and
evidence chain.

## Webhooks

Webhook payloads are untrusted. Authenticity, replay window, delivery ID, and
schema are verified before creating a task. Duplicate deliveries are idempotent.

## Communication policy

Reading, drafting, sending, editing, reacting, and deleting are distinct
capabilities. The MVP supports read and draft for GitHub/Jira context; submission
requires exact operator approval. Bulk or ambiguous recipients are not silently
resolved.

## Integration conformance

Each connector must test authentication failure, scope denial, pagination,
rate limits, retries, duplicate delivery, stale state, partial write, revocation,
redaction, and provider-reported confirmation.
