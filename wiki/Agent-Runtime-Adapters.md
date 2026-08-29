# Agent Runtime Adapters

## Adapter rule

Agent runtimes receive a bounded goal, workspace, context package, capability
grant, budget, and callback contract. They return progress and evidence. They do
not own the operator profile, global memory, policy, secrets, or governed result.

## Planned runtime roles

| Runtime | Intended role | Integration status |
|---|---|---|
| OpenJarvis | Default local-first conversational and on-device runtime | Priority evaluation |
| DeerFlow | Long-horizon research, planning, creation, and sub-agent work | Post-MVP priority evaluation |
| OpenHands | Specialist software-engineering worker | Priority adapter |
| OpenClaw | Optional channel/device gateway, not root orchestrator | Gateway evaluation |
| Hermes Agent | Learning-loop and personal-agent reference | Research reference; adapter deferred |

The list is not a promise to ship every runtime. Each must outperform a simpler
baseline on a defined task class before promotion.

## Delegation contract

An `AgentJobRequest` contains:

- job, parent task, and plan-step identifiers;
- goal and explicit non-goals;
- input artifact references and verified context package;
- allowed tools/capabilities and scoped grants;
- workspace mount map;
- time, token, cost, and resource budgets;
- expected output schema and acceptance checks;
- progress and heartbeat interval;
- cancellation endpoint;
- untrusted-content labels;
- memory read scope and prohibition on direct memory writes.

The response contains:

- agent runtime and exact version;
- execution identifier and environment digest;
- structured result or typed failure;
- native messages/tool trace references;
- artifact hashes;
- resource and cost usage;
- claimed completion state;
- verification suggestions.

Claimed completion remains untrusted until Okal verifies it.

## Context isolation

Each agent receives the minimum task context. Untrusted web, issue, email, and
document content remains marked as data. Worker instructions cannot override the
kernel goal, policy, or grants. Context packages are immutable and hashed.

## Memory boundary

Workers may:

- request scoped memory retrieval;
- return candidate observations or procedural lessons;
- reference existing memory IDs.

Workers may not:

- update the operator profile directly;
- silently store conversation content;
- delete or rewrite source events;
- share memory across scopes without kernel authorization.

## Nested agents

Nested agents are disabled by default. When allowed, child creation must be
visible to the kernel and inherit a reduced budget and permission set. Recursion,
fan-out, and total child count are hard-limited.

## Failure handling

The adapter maps provider behavior into canonical failures:

- `UNAVAILABLE` — runtime or required service cannot be reached;
- `REJECTED` — runtime refused valid work;
- `INVALID_OUTPUT` — response failed schema or semantic validation;
- `BUDGET_EXCEEDED` — time, token, cost, or resource limit reached;
- `POLICY_DENIED` — requested action exceeded its grant;
- `CANCELLED` — termination was acknowledged;
- `UNKNOWN_EXTERNAL_STATE` — a consequential action cannot be reconciled;
- `INTERNAL_ERROR` — runtime failure with sanitized diagnostics.

## Promotion gate

An agent adapter becomes active only after contract tests, task-class benchmarks,
adversarial injection tests, resource profiling, failure-recovery tests, and a
license/security review. A newer upstream version begins in quarantine.
