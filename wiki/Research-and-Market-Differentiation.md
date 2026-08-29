# Research and Market Differentiation

Okal is not differentiated by having more tools. Its research claim is that a personal assistant becomes more capable when heterogeneous runtimes are coordinated by a verified, resource-aware control plane with explicit authority and provenance.

## Product gap

Existing projects usually optimize one layer: local models, deep research, channels, coding, memory, voice, automation, or media. Combining them directly creates conflicting state, permission, and success semantics. Okal focuses on the missing coordination layer.

## Differentiators

1. **Verified outcomes:** native-system evidence is separated from model claims.
2. **One authority:** external agents are workers; the kernel owns policy and lifecycle.
3. **Resource awareness:** routing accounts for RAM, VRAM, latency, privacy, and cost.
4. **Provenance-first memory:** every durable claim retains source, time, scope, and deletion path.
5. **Governed extensibility:** skills pass a supply-chain pipeline before receiving authority.
6. **Local-first hybrid operation:** private work stays local when possible, without pretending every workload fits local hardware.
7. **Arabic-first-class evaluation:** Arabic documents and voice are release gates, not translations added later.

## Research hypotheses

| ID | Hypothesis | Experiment | Success signal |
|---|---|---|---|
| H1 | Constraint-aware routing beats a fixed “best” model | compare fixed/local/cloud/router across task and resource suites | higher governed success within cost/privacy budgets |
| H2 | Multidimensional receipts reduce false completion | inject timeouts, model misreports, and partial side effects | lower false-success and faster reconciliation |
| H3 | Provenance-temporal memory improves personalization safely | compare no memory/vector-only/layered memory | better grounded recall with lower stale/leak rate |
| H4 | Skill quarantine prevents practical capability compromise | submit benign, vulnerable, and adversarial skill corpus | high malicious recall with acceptable false positives |
| H5 | A thin kernel reduces integration churn | replace runtimes/providers under contract tests | fewer core changes and stable task behavior |
| H6 | Resource brokering improves experience on consumer GPUs | concurrent voice/OCR/model workloads | lower OOM and voice p95 latency |
| H7 | Structured-first computer use is more reliable | compare API/DOM/accessibility/vision paths | fewer unintended actions and better replayability |

## Experimental method

- Pre-register task suites, thresholds, and primary metrics.
- Compare against simple baselines, not only previous Okal versions.
- Separate quality, safety, cost, latency, and resource results.
- Publish configuration, dataset provenance, seeds, traces, and failure taxonomy where privacy permits.
- Use deterministic native-state checks for external actions.
- Repeat on the reference constrained workstation and a larger lab machine.

## Potential public outputs

- the Okal Capability Manifest and conformance kit;
- a receipt schema and verifier for agentic execution;
- an Arabic document-and-coding assistant benchmark;
- a consumer-GPU resource-aware agent benchmark;
- anonymized failure taxonomies for prompt injection and uncertain side effects;
- reproducible technical reports describing negative as well as positive results.

## What Okal will not claim

Okal is not AGI, consciousness, or a guarantee of correctness. It does not make an unsafe model safe merely by logging it. Claims must be tied to a versioned benchmark, deployment boundary, and evidence report.

## Decision rule

A research feature enters the product only if it improves a named user outcome, passes safety and resource gates, and remains understandable and removable. Interesting complexity without demonstrated value stays in the lab.

