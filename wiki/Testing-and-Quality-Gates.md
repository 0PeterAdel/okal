# Testing and Quality Gates

Quality is enforced at boundaries: schemas, policy, side effects, evidence, persistence, and user-visible outcomes.

## Test portfolio

| Test type | What it protects |
|---|---|
| Unit | pure domain rules, validators, routing, and redaction |
| Property-based | state machines, idempotency, receipt chains, and parsers |
| Contract | adapters, MCP/A2A, OpenAPI, events, and model gateway |
| Integration | database, policy, artifacts, queues, and sandbox lifecycle |
| End-to-end | complete workflows with native-system verification |
| Adversarial | injection, poisoned content, permission bypass, exfiltration |
| Replay | deterministic inspection of recorded task trajectories |
| Resilience | crash, timeout, duplicate delivery, outage, and resume |
| Performance | latency, throughput, memory, VRAM, and long-running stability |
| Clean-room | installation from a fresh machine or container state |

## CI stages

1. **Fast checks:** formatting, linting, type checks, generated-code drift, secret scan.
2. **Unit and property tests:** deterministic and parallel.
3. **Contracts:** OpenAPI, events, manifests, provider fakes, compatibility.
4. **Integration:** ephemeral PostgreSQL, artifact store, policy, and sandbox.
5. **Security:** dependency, image, license, SBOM, skill, and adversarial scans.
6. **End-to-end:** showcase workflow with mocked external services on every PR.
7. **Hardware lane:** real GPU, voice, OCR, and resource-pressure tests before release.
8. **Evaluation lane:** private regression suite and promotion decision.

No untrusted pull request receives production secrets.

## Side-effect testing

External adapters implement a fake, a sandbox/test-account mode where available, and a reconciliation query. Tests assert the resulting native state, not only the adapter response. Destructive paths use disposable fixtures and require exact target resolution.

## Security gates

A release is blocked by:

- a critical or untriaged high-severity vulnerability in a reachable component;
- a capability that bypasses policy, grant validation, sandboxing, or receipts;
- secret material in source, logs, artifacts, or evaluation fixtures;
- an unapproved dependency license or unsigned promoted skill;
- a successful critical prompt-injection or confused-deputy scenario.

Exceptions are time-limited, documented, owned, and never allowed for known credential exposure or authorization bypass.

## Flaky tests

Flaky tests are defects. A quarantined test requires an issue, owner, expiry, and preserved signal. Retry counts are reported; retries cannot turn a failing safety gate green.

## Definition of done

A change is done when:

- behavior and non-goals are documented;
- threat and privacy impacts are assessed;
- tests cover normal, error, denial, retry, and resume paths;
- schemas and migrations are compatible and reversible;
- receipts and telemetry make the new behavior inspectable;
- resource and cost budgets are measured where relevant;
- user documentation and runbooks are updated;
- CI gates and required review pass.

## Release evidence

Each release publishes a versioned changelog, SBOM, dependency/license report, signed build provenance, migration/rollback notes, benchmark summary, known risks, and checksums or signatures for distributed artifacts.

## Acceptance criteria

- The showcase workflow passes from a clean install.
- Every side-effecting adapter has idempotency and reconciliation tests.
- Receipt tampering and missing-evidence tests fail closed.
- The constrained-hardware lane stays within declared budgets.
- Release artifacts can be traced to reviewed source and a passing evaluation run.

