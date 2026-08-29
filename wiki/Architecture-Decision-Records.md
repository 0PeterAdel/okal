# Architecture Decision Records

This page is the initial ADR index. Status values are `Proposed`, `Accepted`, `Superseded`, or `Rejected`. A future ADR may supersede a decision but must preserve its history.

## ADR-001 — One thin authoritative kernel

**Status:** Accepted

**Decision:** The Okal kernel exclusively owns identity, policy, task state, approvals, resource leases, receipts, and final outcome status. Agent frameworks run as untrusted or semi-trusted workers.

**Why:** Combining multiple autonomous frameworks as peers creates conflicting authority and irreconcilable state.

**Consequences:** Integrations require adapters and may expose fewer framework-specific features, but runtimes remain replaceable and governable.

## ADR-002 — Modular monolith before distributed services

**Status:** Accepted

**Decision:** Build the kernel as a modular Python service with clear internal boundaries. Split a module only for isolation, scaling, licensing, language/runtime, or failure-containment reasons.

**Why:** A small team needs transactional consistency and low operational overhead while contracts mature.

**Consequences:** Module boundaries and events must be disciplined so later extraction is possible.

## ADR-003 — Local-first, policy-controlled hybrid execution

**Status:** Accepted

**Decision:** Keep task state, policy, approvals, core memory, and receipts local by default. Route model or compute work remotely only when allowed by data class, budget, capability, and user policy.

**Why:** Privacy and offline resilience matter, but consumer hardware cannot efficiently run every workload.

**Consequences:** Every adapter declares data handling; the product must explain routing decisions and support degraded local operation.

## ADR-004 — Evidence is multidimensional and fail-closed

**Status:** Accepted

**Decision:** Store invocation, reachability, execution, output, native output, model output, acceptance, policy, and governed success separately. Missing required evidence cannot become success.

**Why:** Agent narration and transport success do not prove that an intended side effect occurred correctly.

**Consequences:** Adapters need reconciliation and native-state checks; receipts are a core domain object.

## ADR-005 — Layered, provenance-bound memory

**Status:** Accepted

**Decision:** Separate working, episodic, semantic, preference, document, code, and procedural memory. Durable items include provenance, time, scope, confidence, and deletion lineage.

**Why:** A single vector store conflates temporary context, facts, preferences, and source evidence.

**Consequences:** Retrieval and retention are more complex, but stale or sensitive memories can be explained and removed.

## ADR-006 — MCP for tools, A2A for remote agents

**Status:** Accepted

**Decision:** Prefer MCP at tool/data boundaries and A2A where a remote component has agent/task semantics. Both pass through Okal capability manifests and grants.

**Why:** The protocols solve different interoperability problems and neither supplies Okal's authorization model.

**Consequences:** Protocol adapters must translate identity, schemas, errors, and evidence into kernel contracts.

## ADR-007 — Durable orchestration is explicit

**Status:** Accepted

**Decision:** Task and step state is persisted before side effects; events use a transactional outbox; retries are idempotent; uncertain outcomes enter reconciliation.

**Why:** Long-running assistants must survive crashes, provider outages, and human approval delays.

**Consequences:** Execution is more structured than an in-memory agent loop. Temporal may be adopted later if its operational value exceeds cost.

## ADR-008 — Structured-first computer interaction

**Status:** Accepted

**Decision:** Prefer native APIs, then MCP, then DOM/accessibility automation, and use visual coordinate interaction only as a bounded fallback.

**Why:** Structured actions are easier to authorize, test, replay, and verify.

**Consequences:** Some applications remain unsupported until a reliable adapter exists; visual actions require stronger preview and evidence.

## ADR-009 — Resource broker controls heavy workloads

**Status:** Accepted

**Decision:** Heavy model, OCR, voice, and media workers obtain RAM/VRAM leases. On the reference machine, only one GPU-heavy workload executes at a time and interactive voice has priority.

**Why:** Uncoordinated workers cause OOM, latency spikes, and an unusable workstation.

**Consequences:** Jobs may queue, unload models, degrade, or route remotely, and must declare resource profiles.

## ADR-010 — Gated self-improvement only

**Status:** Accepted

**Decision:** Production may collect redacted failures and propose candidates, but cannot silently rewrite or promote its own prompts, policies, tools, skills, or code. Promotion requires offline evaluation, review, signing, canary, and rollback.

**Why:** Uncontrolled adaptation can optimize for misleading metrics or weaken safety.

**Consequences:** Improvement is slower but attributable, reversible, and testable.

## ADR-011 — Dependency and license isolation

**Status:** Accepted

**Decision:** Keep the core permissively licensed where possible. Components with incompatible, copyleft, source-available, weight, or dataset terms remain optional and isolated unless compliance is explicitly accepted.

**Why:** Technical composition can unintentionally constrain distribution or create obligations.

**Consequences:** Some integrations use external service/process boundaries and are not bundled.

## ADR-012 — Canonical documentation lives in the repository

**Status:** Accepted

**Decision:** Markdown under `/wiki` is the canonical source and is synchronized to GitHub Wiki by automation.

**Why:** Documentation changes need review, history, CI validation, and reproducible publication.

**Consequences:** Direct Wiki edits are overwritten; contributors edit `/wiki` through pull requests.

## ADR template

```markdown
## ADR-NNN — Title

**Status:** Proposed
**Date:** YYYY-MM-DD
**Decision owners:** roles or maintainers

### Context
What constraint or problem requires a durable decision?

### Decision
What exactly will Okal do?

### Alternatives considered
What credible options were rejected and why?

### Consequences
What becomes easier, harder, required, or prohibited?

### Validation
Which tests, metrics, or review will prove the decision still works?
```

