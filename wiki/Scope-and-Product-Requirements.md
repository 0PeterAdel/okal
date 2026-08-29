# Scope and Product Requirements

## Product boundary

Okal is initially a **single-operator personal AI operating system**. The design
supports multiple devices and remote workers, but multi-tenant enterprise
administration is not an MVP requirement.

## In scope

- Text and voice interaction across desktop and selected messaging channels.
- Local and cloud model providers behind one gateway.
- Durable tasks that can pause, resume, retry, cancel, and recover.
- Typed tools, Agent Skills, MCP servers, A2A agents, workflows, and services.
- Layered personal, episodic, semantic, procedural, document, and code memory.
- Browser, desktop, shell, file, code, OCR, research, and media capabilities.
- Explicit approvals and scoped policy for consequential actions.
- Sandboxed execution and controlled network/file/secret access.
- Evidence receipts, audit trails, observability, and reproducible evaluation.
- Local hardware scheduling and optional remote execution.
- Candidate skill and routing improvement with offline promotion gates.

## Explicit non-goals for the MVP

- Building or training a new foundation model.
- Claiming AGI, sentience, or guaranteed correctness.
- Unrestricted autonomous access to the host, accounts, money, or identity.
- Installing thousands of unreviewed community skills.
- Supporting every chat platform or SaaS integration.
- A public skill marketplace.
- Multi-tenant billing, organization management, or enterprise compliance claims.
- Live self-modifying production code.
- Replacing deterministic automation with model-generated steps.
- Running every heavy model simultaneously on an 8 GB GPU.

## Functional requirements

| ID | Requirement | MVP priority |
|---|---|---|
| FR-001 | Accept text requests and maintain a durable conversation/task link | Must |
| FR-002 | Classify intent, risk, privacy, and resource requirements | Must |
| FR-003 | Produce a visible, editable execution plan for multi-step tasks | Must |
| FR-004 | Discover capabilities from a signed registry | Must |
| FR-005 | Enforce capability permissions before invocation | Must |
| FR-006 | Route model requests across local and allowed remote providers | Must |
| FR-007 | Execute tools in an isolated workspace | Must |
| FR-008 | Bind outputs and artifacts to evidence receipts | Must |
| FR-009 | Require approval for external writes and communications | Must |
| FR-010 | Store raw events and approved memory with provenance | Must |
| FR-011 | Resume long tasks after worker or process failure | Must |
| FR-012 | Expose task state, plan, approvals, evidence, cost, and resources | Must |
| FR-013 | Support GitHub, Jira, local files, and document ingestion | Must |
| FR-014 | Support push-to-talk streaming speech and speech output; wake word is gated | Showcase |
| FR-015 | Delegate research to a long-horizon agent adapter | Later |
| FR-016 | Delegate coding to a specialist coding agent | Showcase |
| FR-017 | Support browser actions with structured-first fallback | Showcase |
| FR-018 | Generate candidate skills from successful traces | Later |
| FR-019 | Support A2A remote agent federation | Later |
| FR-020 | Support temporal knowledge graph memory | Later |

## Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-001 | Security | Deny by default; no capability may self-grant authority |
| NFR-002 | Privacy | Local storage and local inference are the default policy |
| NFR-003 | Truth | No governed success without bound execution evidence |
| NFR-004 | Reliability | Durable state survives process restart and safe retry |
| NFR-005 | Portability | Linux is first-class; Windows and macOS are adapter targets |
| NFR-006 | Replaceability | Provider-specific code remains outside domain contracts |
| NFR-007 | Performance | Interactive text first token target under 2.5 s when local resources permit |
| NFR-008 | Voice | Perceived turn latency target under 1.2 s for the configured fast path |
| NFR-009 | Resource safety | GPU/RAM budgets enforced before dispatch, not after OOM |
| NFR-010 | Cost | Every remote model/tool call records estimated and actual cost |
| NFR-011 | Observability | End-to-end trace across planning, policy, tools, models, and verification |
| NFR-012 | Accessibility | Keyboard-first UI, captions, text alternative for voice, reduced motion |
| NFR-013 | Internationalization | UTF-8 end to end; Arabic and English are acceptance-test languages |
| NFR-014 | Reproducibility | Pinned dependencies, clean-environment verification, artifact hashes |

## Constraints

- Initial reference device: Linux laptop, 16 GB RAM, RTX 4060 Mobile 8 GB.
- A local deployment must remain usable without a permanent cloud dependency.
- Model, data, and code licenses are evaluated separately.
- External projects are integrated through adapters or isolated processes.
- The repository remains MIT; copyleft components cannot be copied into the core.

## Product-level acceptance

The MVP is accepted only when the showcase workflow completes from a fresh
installation and produces verifiable evidence for every external or code action,
with no secret exposure and no unapproved side effect. See [MVP Definition](MVP-Definition)
and [Testing and Quality Gates](Testing-and-Quality-Gates).
