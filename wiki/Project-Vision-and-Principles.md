# Project Vision and Principles

## Vision

Okal will be a personal intelligence control plane that can safely perceive,
reason, remember, act, verify, and improve across the operator's digital life.
It will be local-first and model-agnostic, but able to use remote compute when
the operator's policy allows it.

Okal's value is not a new foundation model. Its value is trustworthy composition:
the correct capability, with the minimum authority, running on the appropriate
resource, producing a verifiable result, and updating memory only when allowed.

## Product thesis

The personal-agent ecosystem already contains strong projects for local agents,
long-horizon research, coding, voice, document understanding, browser control,
workflow automation, and memory. Their individual strength does not automatically
produce a coherent assistant. A personal AI operating system must own the
cross-cutting concerns those projects cannot safely own together:

- operator identity and intent;
- policy and approval;
- durable task state;
- capability discovery and versioning;
- memory provenance and lifecycle;
- resource and cost arbitration;
- evidence and truth semantics;
- evaluation, promotion, rollback, and incident response.

## Governing principles

### 1. One authority, many workers

Only the Okal Control Kernel can authorize actions, commit durable memory, mark a
task governed-successful, or grant capability permissions. External agents are
workers, never co-owners of authority.

### 2. Local first, not local only

Sensitive state and control remain local by default. Cloud models and services
are optional execution providers selected by explicit policy. The operator can
inspect why data was routed remotely.

### 3. Evidence before confidence

A natural-language claim is not execution evidence. Completion requires a typed
receipt bound to the request, execution, capability version, policy decision,
output bytes or artifacts, and verification result.

### 4. Least privilege by construction

Capabilities receive narrow, temporary grants to specific paths, hosts, secrets,
devices, and actions. A prompt cannot widen those grants.

### 5. Raw truth is separate from derived memory

Source events and artifacts are immutable records. Profiles, summaries, facts,
embeddings, and graphs are derived views that may be corrected, invalidated, or
deleted without rewriting history.

### 6. Deterministic where possible, agentic where valuable

Known workflows use typed code and durable workflow steps. Models are used for
interpretation, planning, generation, and uncertain decisions—not for operations
that can be made deterministic.

### 7. Replaceability is a feature

Models, stores, agent runtimes, and tools are behind contracts. Forking or
modifying an upstream project is a last resort and must be justified by an ADR.

### 8. Improvement is gated

Okal may propose new skills, prompts, routing policies, and code. Candidates are
evaluated offline, compared against a baseline, approved, promoted, monitored,
and reversible. Production never edits itself without a release gate.

### 9. Resource use is part of correctness

A task that succeeds by exhausting memory, blocking real-time voice, leaking
data, or spending unbounded money is not a successful task.

### 10. Honest boundaries

Okal does not claim consciousness, AGI, infallibility, or unrestricted autonomy.
The project describes demonstrated capabilities and explicit unavailable states.

## Long-term outcome

A mature Okal installation should feel continuous across desktop, mobile, voice,
chat, repositories, documents, and scheduled work while remaining inspectable
and under operator control. It should be possible to remove any upstream worker
without losing identity, memory ownership, policy, or evidence history.
