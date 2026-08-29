# Initial Backlog

This backlog converts the architecture into executable epics. IDs are stable planning references; implementation issues should link back to them.

## E0 — Repository and engineering foundation

| ID | Work item | Depends on | Done when |
|---|---|---|---|
| E0.1 | Establish monorepo layout and developer commands | — | clean clone builds and tests |
| E0.2 | Add lint, typing, test, secret, dependency, and license CI | E0.1 | required checks run on PRs |
| E0.3 | Define configuration schema and local profiles | E0.1 | invalid config fails safely |
| E0.4 | Add versioning, changelog, SBOM, and signed-build skeleton | E0.2 | dry-run release emits artifacts |
| E0.5 | Publish threat model and initial ADRs | — | maintainer review accepted |

## E1 — Durable control kernel

| ID | Work item | Depends on | Done when |
|---|---|---|---|
| E1.1 | Implement Task, Plan, Step, Attempt state machines | E0.3 | property tests cover transitions |
| E1.2 | Add transactional outbox and event envelope | E1.1 | duplicate delivery is harmless |
| E1.3 | Add cancellation, pause, resume, timeout, retry | E1.1 | crash-resume suite passes |
| E1.4 | Implement approval lifecycle and scoped grants | E1.1 | expired/replayed grants fail |
| E1.5 | Expose OpenAPI and event stream | E1.2 | generated client passes contract tests |

## E2 — Evidence and observability

| ID | Work item | Depends on | Done when |
|---|---|---|---|
| E2.1 | Define receipt schemas and governed-success rules | E1.1 | no ambiguous success state |
| E2.2 | Add content-addressed artifact service | E0.3 | digest verification and GC tests pass |
| E2.3 | Bind receipts to requests, manifests, environment, and outputs | E2.1,E2.2 | tampering is detected |
| E2.4 | Add OpenTelemetry correlation and redaction | E1.2 | full trace reconstructs safely |
| E2.5 | Build receipt viewer and verifier | E2.3 | independent verify report works |

## E3 — Capability fabric and isolation

| ID | Work item | Depends on | Done when |
|---|---|---|---|
| E3.1 | Publish manifest schema and capability SDK | E1.5,E2.1 | sample adapter validates |
| E3.2 | Implement policy decision point and risk classes | E1.4 | allow/deny/approve suite passes |
| E3.3 | Build MCP gateway with identity and schema mediation | E3.1,E3.2 | MCP cannot bypass grants |
| E3.4 | Build rootless execution sandbox | E3.2 | escape and egress tests pass |
| E3.5 | Add conformance kit and three reference capabilities | E3.1–E3.4 | filesystem, shell, GitHub pass |

## E4 — Model and runtime routing

| ID | Work item | Depends on | Done when |
|---|---|---|---|
| E4.1 | Implement provider-neutral model gateway | E1.5 | local and remote providers work |
| E4.2 | Add privacy, quality, cost, latency routing policy | E4.1,E3.2 | decision is explainable/replayable |
| E4.3 | Define agent-runtime adapter contract | E3.1 | mock runtime passes conformance |
| E4.4 | Integrate first general runtime worker | E4.3 | worker has no direct authority |
| E4.5 | Add fallback, circuit breaker, and budget enforcement | E4.1 | outage/cost tests pass |

## E5 — Resource broker

| ID | Work item | Depends on | Done when |
|---|---|---|---|
| E5.1 | Collect CPU/RAM/VRAM worker telemetry | E2.4 | leases use current measurements |
| E5.2 | Implement resource leases and GPU-heavy queue | E1.2 | one heavy GPU job runs at once |
| E5.3 | Add priority, preemption points, unload, and cooldown | E5.2 | voice remains responsive |
| E5.4 | Add remote-route recommendation and budget guard | E4.2,E5.2 | oversized work degrades safely |

## E6 — Knowledge, documents, and memory

| ID | Work item | Depends on | Done when |
|---|---|---|---|
| E6.1 | Implement document ingestion and provenance graph | E2.2 | every chunk maps to source region |
| E6.2 | Integrate Arabic PDF parsing and OCR fallback | E6.1,E5.2 | fixture extraction threshold passes |
| E6.3 | Add codebase index adapter | E3.3,E6.1 | symbols and relations are cited |
| E6.4 | Implement working, episodic, semantic, and preference memory | E6.1 | memory eval suite passes |
| E6.5 | Add temporal updates, contradiction, export, and deletion | E6.4 | deletion verification passes |

## E7 — User experience and voice

| ID | Work item | Depends on | Done when |
|---|---|---|---|
| E7.1 | Build task-focused web shell and event streaming | E1.5 | state survives refresh |
| E7.2 | Build plan, permission, and approval preview | E1.4,E3.2 | exact action is understandable |
| E7.3 | Build artifacts, citations, receipts, and diff views | E2.5,E6.1 | evidence is navigable |
| E7.4 | Add CLI for tasks, approvals, and verification | E1.5,E2.5 | headless showcase works |
| E7.5 | Integrate push-to-talk Arabic/English STT/TTS | E4.1,E5.3 | interruption/latency suite passes |

## E8 — GitHub coding showcase

| ID | Work item | Depends on | Done when |
|---|---|---|---|
| E8.1 | Add read-only GitHub and Jira context adapters | E3.5 | fixture data retrieved safely |
| E8.2 | Add isolated clone, map, patch, and test workflow | E3.4,E6.3 | deterministic fixture passes |
| E8.3 | Add code review and change explanation | E8.2 | diff rubric threshold passes |
| E8.4 | Add approve-before-PR write and idempotency | E1.4,E8.1 | no write without valid grant |
| E8.5 | Add native PR reconciliation and receipts | E2.3,E8.4 | duplicates/uncertainty handled |

## E9 — Evaluation, security, and supply chain

| ID | Work item | Depends on | Done when |
|---|---|---|---|
| E9.1 | Build evaluation runner and versioned datasets | E1.2 | reproducible report generated |
| E9.2 | Add routing, memory, OCR, voice, and showcase suites | E4–E8 | baselines and thresholds recorded |
| E9.3 | Build skill intake quarantine and scan pipeline | E3.1 | unsigned skill cannot promote |
| E9.4 | Add adversarial injection and exfiltration suite | E3.2–E3.4 | critical scenarios fail closed |
| E9.5 | Add model/skill canary and rollback controller | E9.1,E9.3 | bad candidate auto-rolls back |

## E10 — Packaging and beta readiness

| ID | Work item | Depends on | Done when |
|---|---|---|---|
| E10.1 | Create production Compose/native package | E0–E9 | clean install passes |
| E10.2 | Add backup, restore, upgrade, and rollback automation | E10.1 | recovery exercise passes |
| E10.3 | Harden loopback/network defaults and remote-worker auth | E10.1 | exposure audit passes |
| E10.4 | Complete docs, runbooks, accessibility, and onboarding | E7,E10.1 | new-user walkthrough succeeds |
| E10.5 | Produce signed beta with SBOM and evaluation report | E10.2–E10.4 | M7 gates pass |

## First sprint recommendation

Begin with E0.1–E0.5, E1.1, E2.1, and contract spikes for E3.1/E4.3. The first demonstrable slice should create a task, request approval, run one mocked capability, emit a receipt, and render the result in a minimal UI.
