# Personas and End-to-End Use Cases

## Primary persona: the operator

The first user is a technical single operator who works across Linux, source
repositories, project tracking, documents, web research, communication, and
local AI. The operator values power, privacy, inspectability, and the ability to
replace components without losing accumulated context.

The operator is not expected to understand every upstream framework or manually
choose an agent for each request. Okal explains important routing and approval
decisions without exposing unnecessary internal noise.

## Secondary personas

### Contributor

Builds kernel features, adapters, skills, evaluations, UI, or documentation.
Needs stable contracts, local development, test fixtures, and clear ownership.

### Capability maintainer

Publishes a tool, skill, model adapter, or agent adapter. Needs a versioned
manifest, conformance suite, security scan, evaluation report, and promotion path.

### Research evaluator

Runs repeatable experiments on routing, memory, safety, resource efficiency, or
task success. Needs frozen datasets, configurations, traces, and result manifests.

## Priority use cases

### UC-01 — Software delivery review

1. The operator asks Okal to review a pull request.
2. Okal resolves the repository, branch, task context, and requested depth.
3. The router obtains architecture context from code memory.
4. A coding worker reviews code and runs tests in an isolated checkout.
5. Okal verifies commands, repository state, and produced artifacts.
6. It relates findings to Jira and the requirements document.
7. It prepares, but does not submit, review communication without approval.
8. It stores only the approved decision and evidence references.

### UC-02 — Source-grounded research

1. The operator asks a multi-part research question.
2. Okal establishes freshness and source requirements.
3. A long-horizon worker gathers sources and drafts findings.
4. The kernel verifies source reachability, citation binding, and contradictions.
5. The final report distinguishes sourced fact, inference, and uncertainty.

### UC-03 — Arabic document intelligence

1. The operator adds a PDF or image.
2. Okal records the original artifact hash and sensitivity class.
3. Docling handles structural parsing; OCR is invoked only for required pages.
4. Extracted blocks retain page/region provenance.
5. Answers link back to source spans and report extraction confidence.

### UC-04 — Voice command with consequential action

1. The wake-word detector activates locally.
2. Streaming speech is transcribed and shown to the operator.
3. Okal repeats or requests clarification when the action is ambiguous.
4. A draft action is generated.
5. The operator approves the exact recipient, payload, and destination.
6. Okal executes and verifies the remote result.

### UC-05 — Scheduled monitoring

1. The operator defines a condition and cadence.
2. Okal stores a durable schedule and a bounded action policy.
3. Each run records sources, changes, cost, and outcome.
4. No notification is sent when the condition is not met.
5. The schedule can be inspected, paused, edited, or removed.

### UC-06 — Personal continuity

1. The operator states a preference or makes a decision.
2. Okal proposes a memory entry with scope and source.
3. The memory gate checks duplication, sensitivity, contradiction, and retention.
4. Future tasks retrieve the entry only when relevant and permitted.
5. The operator can inspect, correct, expire, export, or delete it.

### UC-07 — Capability installation

1. The operator provides a repository or registry reference.
2. Okal resolves and pins a commit or immutable artifact.
3. License, SBOM, signature, and security scans run before execution.
4. Conformance and adversarial tests run in a denied-by-default sandbox.
5. Okal presents required permissions and evaluation evidence.
6. The operator approves or rejects promotion.

### UC-08 — Resource-aware local execution

1. An OCR request arrives while a local model is loaded.
2. The Resource Broker calculates VRAM and latency impact.
3. Interactive voice remains prioritized.
4. The model is unloaded, remote-routed, or the OCR job is queued according to policy.
5. Resource use and the routing reason appear in the task evidence.

## Experience rules

- The operator sees what Okal plans before high-impact work.
- Approvals describe the exact action, destination, and data.
- Failed, partial, unavailable, and blocked states remain distinct.
- A worker's natural-language statement never substitutes for verification.
- The operator can stop a running task and revoke active grants.
- Memory use is visible when it materially affects a decision.
