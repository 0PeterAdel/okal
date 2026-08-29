# Risk Register

Risks are reviewed at every milestone and release. Likelihood and impact use `Low`, `Medium`, `High`, and `Critical`; owners are roles until named maintainers are assigned.

| ID | Risk | Likelihood | Impact | Trigger / early signal | Mitigation | Owner |
|---|---|---:|---:|---|---|---|
| R01 | Integration sprawl overwhelms the core | High | High | adapters alter kernel semantics | freeze contracts; ship only showcase adapters | Architecture |
| R02 | Multiple runtimes compete for authority | Medium | Critical | worker performs direct side effects | thin kernel; all actions through grants/receipts | Architecture |
| R03 | Prompt injection causes data/action abuse | High | Critical | content requests secrets or tool escalation | taint tracking; policy; isolation; adversarial tests | Security |
| R04 | Malicious or compromised skill | Medium | Critical | unexpected network/filesystem behavior | quarantine, scan, conformance, signing, revocation | Supply chain |
| R05 | Dependency/license conflict blocks distribution | Medium | High | copyleft/source-available code enters core | license gate; process isolation; clean-room adapter | Legal/Release |
| R06 | Model weights or datasets have incompatible terms | Medium | High | unclear redistribution/commercial rights | separate review and manifest; no implicit bundling | Release |
| R07 | False success hides failed side effects | Medium | Critical | model says done but native state differs | multidimensional receipts and reconciliation | Reliability |
| R08 | Retry duplicates an external action | Medium | Critical | timeout after provider accepted request | idempotency keys; native lookup; uncertain state | Reliability |
| R09 | Personal memory leaks or becomes stale | Medium | Critical | irrelevant sensitive recall or contradictions | provenance, scope, temporal updates, user controls | Privacy |
| R10 | Deletion does not remove derived data | Medium | High | deleted item still appears in index/cache | deletion graph; rebuildable indexes; verify report | Privacy |
| R11 | Local hardware cannot sustain the stack | High | High | OOM, swap, voice latency, thermal throttling | resource broker; profiles; quantization; remote option | Platform |
| R12 | Voice creates accidental or covert actions | Medium | High | false wake/turn or unclear recording | push-to-talk first; visible state; confirmation | Product/Security |
| R13 | Browser/desktop control is brittle | High | High | selectors drift or visual misclick | structured-first; screenshots/evidence; bounded fallback | Automation |
| R14 | Upstream project becomes unmaintained | Medium | Medium | security backlog or release inactivity | adapter boundary; pinned fork option; exit tests | Architecture |
| R15 | Cloud outage or pricing change | Medium | High | provider errors or budget spike | multi-provider routing; local degraded mode; caps | Platform |
| R16 | Evaluation overfits visible benchmarks | Medium | High | gains vanish on private cases | sealed holdout; rotating adversarial cases; human audit | Evaluation |
| R17 | Model judge bias approves poor output | Medium | High | disagreement with deterministic/human labels | calibrate judges; never sole critical verifier | Evaluation |
| R18 | Self-improvement regresses safety | Medium | Critical | candidate bypasses or games evaluation | offline proposals; gated promotion; canary/rollback | Security/Evaluation |
| R19 | Supply-chain compromise in builds | Medium | Critical | unsigned/untraceable artifact | pinned deps; SBOM; provenance; signed releases | Release |
| R20 | Observability leaks secrets or content | Medium | Critical | raw prompt/token appears in logs | structured redaction; content classes; access control | Security |
| R21 | Single-user scope silently becomes multi-tenant | Medium | High | shared accounts or cross-user data | explicit non-goal; workspace boundary; new ADR first | Product |
| R22 | Project attempts too much before proving value | High | High | many demos, no complete workflow | MVP acceptance gates; milestone funding by evidence | Product |

## Risk treatment rules

- Critical risks require preventive controls and tested detection before exposure.
- High residual risks require a named acceptance decision and review date.
- A mitigation is not complete until it has a test, metric, or operational check.
- Closed risks remain in history with the evidence that justified closure.
- New capabilities update the threat model, resource budget, and license inventory.

## Stop conditions

Pause release or autonomous execution if receipt integrity fails, an authorization bypass is found, secrets are exposed, an external side effect cannot be reconciled, or a critical dependency/skill lacks trustworthy provenance.

