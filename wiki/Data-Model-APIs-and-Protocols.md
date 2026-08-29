# Data Model, APIs, and Protocols

Okal uses stable domain contracts so that models, tools, workers, storage engines, and user interfaces remain replaceable.

## Core entities

| Entity | Responsibility |
|---|---|
| Principal | human, service, agent, or worker identity |
| Workspace | security and data boundary for a user's work |
| Conversation | ordered interaction context |
| Task | durable intent with constraints and desired outcome |
| Plan | versioned graph of proposed steps |
| Step | one capability invocation or deterministic operation |
| Attempt | one execution of a step |
| Capability | versioned action contract and risk metadata |
| Grant | scoped, expiring authority to perform an action |
| Approval | explicit decision for a proposed action |
| Artifact | content-addressed input or output object |
| Memory | provenance-bound durable knowledge item |
| Receipt | evidence for an intent, decision, execution, or outcome |
| Evaluation | assertions and metrics over a result or trajectory |
| Resource lease | reserved CPU, RAM, VRAM, or concurrency capacity |

All durable entities use sortable opaque IDs, UTC timestamps, schema versions, and explicit lifecycle states. User-facing names are never used as security identifiers.

## State machines

A task moves through `created → planning → awaiting_approval → queued → running → verifying → completed`. Any active state may move to `paused`, `cancelled`, or `failed`; resumability is explicit.

A step moves through `proposed → authorized → dispatched → observed → validated → accepted`. A denied step never enters dispatched. An uncertain external outcome enters `reconciliation_required`.

## API surface

The kernel initially exposes versioned HTTP APIs and server-sent events:

```text
POST   /api/v1/tasks
GET    /api/v1/tasks/{task_id}
POST   /api/v1/tasks/{task_id}/cancel
GET    /api/v1/tasks/{task_id}/events
POST   /api/v1/approvals/{approval_id}/decisions
GET    /api/v1/receipts/{receipt_id}
POST   /api/v1/receipts/{receipt_id}/verify
GET    /api/v1/artifacts/{artifact_id}
GET    /api/v1/capabilities
POST   /api/v1/memory/search
DELETE /api/v1/memory/{memory_id}
GET    /api/v1/health
```

OpenAPI is the source of truth for public kernel APIs. Generated clients are checked for drift in CI. WebSocket or WebRTC channels may be added for realtime voice, while durable state continues through the kernel contracts.

## Event envelope

```json
{
  "schema": "okal.event.v1",
  "event_id": "evt_01J...",
  "event_type": "step.accepted",
  "occurred_at": "2026-08-29T10:00:00Z",
  "task_id": "task_01J...",
  "step_id": "step_01J...",
  "causation_id": "evt_01J...",
  "correlation_id": "task_01J...",
  "producer": "kernel",
  "payload": {},
  "payload_digest": "sha256:..."
}
```

Consumers must be idempotent. The outbox pattern publishes state changes only after the database transaction commits.

## Error contract

Errors include a stable code, safe message, retryability, correlation ID, details safe for the caller, and a receipt reference when execution began. Internal traces, prompts, credentials, and provider payloads are not returned by default.

## Protocol strategy

| Boundary | Protocol |
|---|---|
| Model providers | LiteLLM-compatible adapter plus provider-native extensions |
| Tools and data sources | Model Context Protocol (MCP) behind the capability gateway |
| Remote agents | Agent2Agent (A2A) adapter when agent semantics are needed |
| Traces and metrics | OpenTelemetry |
| Browser automation | structured accessibility/DOM actions before visual fallback |
| Local workers | authenticated HTTP/gRPC-style contracts over a private transport |

MCP and A2A are interoperability boundaries, not authorization boundaries. Every inbound capability is re-described in an Okal manifest and governed by kernel policy.

## Compatibility and evolution

- Additive fields are preferred within a major schema version.
- Removed or reinterpreted fields require a new major version.
- Adapters declare the versions and optional features they support.
- Stored events retain their original schema and migrate through deterministic upcasters.
- Capability signatures include input/output schema digests.
- Deprecations have telemetry, an owner, and a removal release.

## Data integrity

PostgreSQL is the shared durable store; SQLite supports constrained local development. Artifacts are content-addressed. Vector indexes are derived and rebuildable. Secrets reside outside domain tables. Foreign keys and uniqueness constraints enforce task, attempt, idempotency, and receipt relationships.

## Acceptance criteria

- A worker can be replaced without changing the task API.
- Duplicate events and retries do not duplicate side effects.
- Every externally visible error carries a correlation identifier.
- Protocol schemas and generated clients pass compatibility tests.
- MCP/A2A callers cannot bypass capability grants or receipt generation.

