# Dependency Selection and Licensing

Okal integrates strong open projects through explicit boundaries. It does not merge every repository into one process or assume that “public on GitHub” means freely redistributable.

## Selection policy

A candidate is evaluated for capability fit, maintenance, security history, deployment weight, API stability, observability, data handling, license, model/data terms, and ease of replacement. Every adopted component has an owner and exit strategy.

## Classification

| Class | Meaning |
|---|---|
| Adopt | selected for an initial production path |
| Evaluate | promising; requires benchmark, license, or security validation |
| Reference | learn patterns; do not make a runtime dependency |
| Optional isolated | supported only behind a process/network boundary |
| Defer | no MVP dependency |

## Initial matrix

Licenses below describe the upstream code repository as reviewed for this plan; model weights, datasets, plugins, and bundled components require separate verification at the pinned version.

| Project | Okal role | Initial decision | Code license / boundary note |
|---|---|---|---|
| OpenJarvis | local model/runtime patterns | Evaluate adapter | Apache-2.0; do not make it a second control plane |
| DeerFlow | long-horizon research worker | Evaluate adapter post-MVP | MIT; worker under kernel grants |
| OpenClaw | channels/gateway patterns | Reference or optional adapter | MIT; Okal remains authority |
| Hermes Agent | general agent runtime | Evaluate against alternatives | inspect pinned release and transitive licenses |
| OpenHands | coding runtime | Evaluate for showcase; keep a built-in fallback | inspect pinned release; isolate workspace execution |
| codebase-memory-mcp | code graph/context | Adopt for prototype, benchmark before lock-in | MIT; derived index remains rebuildable |
| Unlimited OCR | Arabic/document OCR | Evaluate GPU worker | verify repository and model-weight terms separately |
| Docling | document parsing | Adopt baseline candidate | MIT; use before OCR where sufficient |
| Voicebox | local STT/TTS studio | Evaluate voice worker | inspect pinned version and model terms; serialized GPU access |
| Pipecat | realtime voice orchestration | Evaluate | BSD-2-Clause; keep kernel state durable |
| openWakeWord | wake-word detection | Defer until push-to-talk is stable | Apache-2.0; model terms still apply |
| Mem0 | semantic/personal memory patterns | Evaluate adapter | Apache-2.0; Okal owns provenance/deletion |
| Graphiti | temporal knowledge graph | Evaluate for advanced memory | Apache-2.0; not required for MVP core |
| LiteLLM | model-provider gateway | Adopt behind Okal interface | MIT; pin and test provider behavior |
| Temporal | durable workflow engine | Evaluate when kernel durability needs it | MIT; avoid premature operational weight |
| Activepieces | automation connector runtime | Evaluate optional worker | Community Edition MIT; verify individual pieces |
| Node-RED | visual automation | Optional isolated | Apache-2.0; never bypass grants |
| n8n | automation ecosystem | Optional external integration | source-available Sustainable Use License; not core FOSS dependency |
| SkillSpector | skill security analysis | Adopt as one scanner | Apache-2.0; defense in depth, not sole approval |
| Anthropic Cybersecurity Skills | security workflows/corpus | Evaluate in quarantine | verify every skill and dependency individually |
| Matt Pocock skills | engineering skill patterns | Reference/evaluate individually | repository/item license must be confirmed |
| gstack | development workflow patterns | Reference/evaluate individually | verify pinned license and tool authority |
| Playwright MCP | structured browser control | Evaluate preferred browser adapter | Apache-2.0; accessibility/DOM before vision |
| Browser Use | browser-agent worker | Evaluate fallback | MIT; run with scoped profile and egress |
| Cua | computer-use infrastructure | Defer/optional isolated | MIT core; optional components have separate licenses |
| HyperFrames | media generation | Optional lab after MVP | Apache-2.0; isolated worker |
| OpenMontage | video editing | Optional isolated lab | AGPL-3.0; network/process boundary and compliance review |
| OPA | policy evaluation | Adopt adapter candidate | Apache-2.0; kernel owns identity/grant semantics |
| OpenTelemetry | observability contracts | Adopt | Apache-2.0 |
| Promptfoo | prompt/security evaluation | Evaluate in test toolchain | MIT; never receives production secrets |
| Inspect AI | agent evaluation | Evaluate in test toolchain | MIT; compare fit with internal runner |
| Langfuse | trace/evaluation backend | Optional | MIT core; self-host and redact content |
| Syft | SBOM generation | Adopt build tool | Apache-2.0 |
| Cosign | signing and provenance | Adopt release tool | Apache-2.0 |

## License boundaries

- Prefer MIT, Apache-2.0, BSD, or similarly permissive libraries in the distributed core.
- Copyleft and source-available systems require documented legal review and isolation; do not copy their code into the core.
- AGPL services may create network-use obligations; treat them as optional until compliance is accepted.
- A tool's connector or plugin may have different terms from its framework.
- Code license, model-weight license, dataset license, and service terms are four separate decisions.
- Preserve notices, attribution, source offers, and modification disclosures as required.

## Intake record

Before adoption, record the exact commit/tag and digest, license files, SBOM, known vulnerabilities, maintainer/release health, required privileges, network destinations, data classes, performance profile, conformance results, and replacement plan.

## Upgrade and removal

Automated update proposals run contract, security, evaluation, license, and resource gates. A dependency is removed when it violates policy, becomes unmaintained without a safe fork, causes repeated instability, or its value no longer justifies its attack/operations surface.
