# Evidence Receipts and Observability

Okal must be able to explain what it attempted, what actually ran, what produced an output, and why that output was accepted. A green status without evidence is not a success signal.

## Outcome dimensions

Every step records these dimensions independently. They must never be collapsed into one `success` boolean.

| Dimension | Question |
|---|---|
| Invocation | Did Okal create and dispatch a valid request? |
| Reachability | Was the selected provider or worker reachable? |
| Execution | Did the intended capability actually run? |
| Output | Was an artifact or structured result produced? |
| Native output | Did the external system report its own result? |
| Model output | What did the model claim or infer? |
| Acceptance | Did deterministic validation and evaluation pass? |
| Policy | Was the action authorized under the active policy? |
| Governed success | May the system treat the step as complete? |

`governed_success` is derived only after all required dimensions are known. Unknown, unverified, and not-applicable are first-class states.

## Receipt envelope

```json
{
  "receipt_version": "okal.receipt.v1",
  "receipt_id": "rcpt_01J...",
  "task_id": "task_01J...",
  "step_id": "step_01J...",
  "attempt": 1,
  "capability": {
    "id": "github.issue.create",
    "version": "1.2.0",
    "manifest_digest": "sha256:..."
  },
  "principal": "user:peter",
  "policy_decision_id": "pdp_01J...",
  "grant_id": "grant_01J...",
  "request_digest": "sha256:...",
  "environment_digest": "sha256:...",
  "started_at": "2026-08-29T10:00:00Z",
  "completed_at": "2026-08-29T10:00:01Z",
  "dimensions": {
    "invocation": "passed",
    "reachability": "passed",
    "execution": "passed",
    "output": "passed",
    "native_output": "passed",
    "model_output": "not_applicable",
    "acceptance": "passed",
    "policy": "passed",
    "governed_success": "passed"
  },
  "artifacts": [{"uri": "artifact://...", "digest": "sha256:..."}],
  "redactions": ["authorization_header"],
  "previous_receipt_digest": "sha256:...",
  "receipt_digest": "sha256:..."
}
```

## Binding rules

A receipt binds together:

- the normalized request and user intent;
- the selected plan, step, and attempt;
- principal, consent, scoped grant, and policy decision;
- capability manifest and immutable version;
- model/provider identity and effective configuration;
- worker and execution-environment fingerprint;
- input and output artifact digests;
- validators, evaluation results, timestamps, and prior receipt digest.

Changing any bound field produces a different digest. Large or sensitive outputs remain in the artifact store; receipts contain references, hashes, media types, and redaction metadata.

## Lifecycle

1. The kernel creates an intent receipt before planning.
2. The policy engine records the allow, deny, or approval-required decision.
3. The executor records dispatch and environment evidence.
4. The adapter captures native output before interpretation.
5. Deterministic validators and evaluators record acceptance evidence.
6. The kernel derives governed success and appends the final receipt.
7. A verifier can independently recompute hashes and inspect the chain.

## Failure semantics

- Missing evidence is `unknown`, not `passed`.
- A timeout does not prove that an external side effect did not occur.
- Retrying a side-effecting call requires an idempotency key or reconciliation.
- Model narration cannot substitute for native-system confirmation.
- A policy denial is a valid execution outcome, not an infrastructure failure.
- Partial results stay visible and attributable.

## Observability model

Okal uses OpenTelemetry-compatible traces, metrics, and structured logs. IDs for task, step, attempt, approval, receipt, artifact, model call, and external operation propagate across all adapters.

Core signals include:

| Signal | Examples |
|---|---|
| Reliability | completion rate, retry rate, stuck tasks, queue age |
| Quality | validator pass rate, citation correctness, human overrides |
| Cost | tokens, provider spend, GPU time, storage growth |
| Latency | plan, model, tool, approval, and end-to-end latency |
| Security | denied actions, suspicious skills, sandbox violations |
| Resources | RAM, VRAM, CPU, model load/unload, thermal pressure |

Logs must never contain raw secrets. User content is redacted by policy and retained according to data class.

## Verification API

The kernel exposes read-only operations to retrieve a receipt, verify its digest chain, enumerate referenced artifacts, and explain why governed success was derived. Export supports JSON plus a compact human-readable report.

## Acceptance criteria

- Every executed step has at least one receipt, including failures and denials.
- A verifier detects changed requests, outputs, manifests, or receipt order.
- External side effects have native confirmation or remain unverified.
- A trace can be reconstructed from task to provider and artifact without exposing secrets.
- No product surface displays “completed” when governed success is unknown or failed.

