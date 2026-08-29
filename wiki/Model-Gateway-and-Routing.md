# Model Gateway and Routing

## Purpose

Okal treats models as interchangeable inference capabilities. The Model Gateway
normalizes provider APIs, but the Okal router—not LiteLLM or an agent runtime—owns
task-aware selection.

## Provider classes

- Local chat/reasoning through Ollama or llama.cpp.
- Local embeddings, rerankers, speech, vision, and OCR providers.
- Remote frontier models when policy permits.
- Remote self-hosted inference through vLLM when stronger hardware is available.
- Specialist providers exposed through an OpenAI-compatible or native adapter.

## Routing inputs

The router uses:

- task class and required modalities;
- minimum structured-output and tool-use support;
- context size and expected output size;
- sensitivity and data residency policy;
- measured success on the relevant evaluation slice;
- latency objective and current queue;
- input/output token cost and task budget;
- local CPU/RAM/GPU availability;
- provider reachability and rate limits;
- operator preference and explicit model selection.

## Routing modes

| Mode | Behavior |
|---|---|
| `local-only` | No request content leaves the trusted device boundary |
| `local-preferred` | Use local when it meets quality/latency; remote fallback is policy-bound |
| `balanced` | Optimize verified success, latency, resource pressure, and cost |
| `quality-first` | Use the best approved provider within privacy and cost constraints |
| `fixed` | Use an explicitly selected provider; fail rather than silently substitute |

## Fast and deep paths

Interactive classification, wake-word follow-up, and simple queries use the fast
path. Complex planning and verification may use a stronger model. A single task
can use different models for planning, execution assistance, and judging, but
each call is individually recorded.

## Fallback rules

- Fallback must preserve the requested privacy and capability constraints.
- A remote provider cannot silently replace a failed local-only route.
- Model substitution is recorded with reason and expected effect.
- Consequential actions are revalidated after a model switch.
- Provider-level success without valid content is rejected.
- Empty, malformed, error-bearing, or incomplete outputs are not model success.

## Cost and budget

Before dispatch, the gateway estimates token, monetary, latency, and resource
cost. During execution it enforces per-call, per-task, daily, and provider budgets.
The final receipt records estimated versus observed use.

## Local reference profile

The reference laptop has 8 GB VRAM and 16 GB RAM. The initial policy favors one
small quantized local text model, with exclusive scheduling for heavy OCR, TTS,
or vision workloads. Large local models may be used only when measured memory
headroom permits; swap is not treated as acceptable interactive capacity.

## Evaluation

Routing decisions are compared against fixed-provider baselines. The router must
demonstrate improved verified success per cost/resource unit without increasing
unsafe-action or privacy-policy violations. See [Evaluation and Benchmarking](Evaluation-and-Benchmarking).
