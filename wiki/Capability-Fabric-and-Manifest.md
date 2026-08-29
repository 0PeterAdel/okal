# Capability Fabric and Manifest

## Purpose

The Capability Fabric makes heterogeneous functionality discoverable without
giving it authority. It represents models, deterministic tools, MCP servers,
Agent Skills, workflows, services, and remote agents using one registry contract.

## Capability classes

| Class | Meaning | Typical protocol |
|---|---|---|
| `tool` | Bounded deterministic or API operation | Native, CLI, REST, MCP |
| `skill` | Procedural knowledge and resources | Agent Skills |
| `workflow` | Durable deterministic step graph | Native, Temporal, Activepieces |
| `model` | Text, vision, speech, embedding, or reranking inference | OpenAI-compatible/provider API |
| `agent` | Autonomous bounded worker for a delegated goal | Native job API, A2A |
| `service` | Supporting capability such as OCR or indexing | REST, gRPC, MCP |
| `channel` | User interaction transport | Gateway adapter |

## Canonical manifest

```yaml
apiVersion: okal.dev/v1alpha1
kind: Capability
metadata:
  id: org.example.code-review
  version: 1.2.0
  displayName: Example Code Review
spec:
  class: agent
  source:
    repository: https://github.com/example/review-agent
    commit: 0123456789abcdef
    license: MIT
    artifactDigest: sha256:...
  interface:
    protocol: a2a
    inputSchema: schemas/review-input.json
    outputSchema: schemas/review-output.json
  permissions:
    filesystem:
      read: ["workspace/repository/**"]
      write: ["workspace/artifacts/**"]
    network:
      allow: ["api.github.com:443"]
    secrets: ["github.read-token"]
    sideEffects: ["none"]
  resources:
    cpu: 4
    memoryMiB: 4096
    gpuMemoryMiB: 0
    timeoutSeconds: 1800
  trust:
    riskTier: R1
    requiredScans: [license, sbom, static, semantic]
    requiredEvalSuite: code-review-v1
    approvalMode: install-and-version-change
  runtime:
    sandboxProfile: network-readonly
    healthCheck: /health
```

## Registry records

The registry stores immutable capability versions plus mutable lifecycle state:

- `discovered` — metadata only, never executable;
- `quarantined` — available to the intake sandbox;
- `evaluated` — conformance and evaluation reports exist;
- `approved` — an operator approved the exact version and permissions;
- `active` — eligible for routing;
- `degraded` — temporarily penalized by health or success metrics;
- `revoked` — dispatch denied immediately;
- `retired` — retained for evidence history but not selectable.

## Discovery and selection

Discovery filters by required output, protocol, trust, permissions, platform,
language, resource fit, availability, and policy. Ranking then considers:

- verified success rate for the task class;
- acceptance-test coverage;
- latency and cost distribution;
- privacy locality;
- resource fit and queue impact;
- operator preference;
- recency and version stability;
- failure correlation with other plan steps.

Popularity and star count are metadata, not trust evidence.

## Versioning rules

- Every execution binds to an immutable version and artifact digest.
- A floating branch or `latest` tag is forbidden in governed execution.
- Permission growth creates a new approval requirement.
- Schema-breaking changes require a major capability version.
- Evaluation results are bound to manifest and artifact digests.
- Revoking a version does not erase historical receipts.

## Capability SDK

The planned SDK will provide:

- manifest validation;
- typed request and response envelopes;
- grant and secret access APIs;
- progress, cancellation, and heartbeat APIs;
- artifact and evidence emission;
- health and conformance checks;
- local fixture runner;
- packaging and signing helpers.

## Conformance minimum

An executable capability must pass schema validation, cancellation, timeout,
malformed input, empty output, error envelope, permission denial, secret
redaction, deterministic fixture, and evidence-binding tests before approval.

See [Skill Supply Chain](Skill-Supply-Chain) for intake and
[Evaluation and Benchmarking](Evaluation-and-Benchmarking) for ranking.
