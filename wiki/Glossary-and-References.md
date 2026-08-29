# Glossary and References

## Glossary

| Term | Meaning in Okal |
|---|---|
| Adapter | Boundary translating an external system into Okal contracts |
| Agent runtime | Worker that can plan or execute a delegated task but does not own authority |
| Artifact | Content-addressed input or output with media type, digest, and provenance |
| Attempt | One execution of a step, including retries |
| Capability | Versioned, policy-governed action contract |
| Capability manifest | Machine-readable declaration of schemas, permissions, risks, resources, and provenance |
| Control kernel | Authoritative core for state, policy, approvals, scheduling, and receipts |
| Governed success | Derived completion state after required policy and evidence dimensions pass |
| Grant | Scoped, expiring authority for a specific principal and action |
| Memory | Durable knowledge with provenance, scope, time, confidence, and lifecycle |
| Native output | Result or state reported by the external system itself |
| Plan | Versioned graph of proposed steps and constraints |
| Principal | Identified human, service, worker, or agent acting in the system |
| Receipt | Tamper-evident evidence envelope for intent, decision, execution, or outcome |
| Reconciliation | Inspection of native state after an uncertain side effect |
| Resource lease | Temporary reservation of CPU, RAM, VRAM, or concurrency capacity |
| Skill | Packaged instructions, code, and metadata that proposes one or more capabilities |
| Step | One authorized capability invocation or deterministic operation in a plan |
| Worker | Replaceable execution component controlled through kernel contracts |

## Protocol and foundation references

- [Model Context Protocol](https://github.com/modelcontextprotocol/modelcontextprotocol) — tool and context interoperability.
- [Agent2Agent Protocol](https://github.com/a2aproject/A2A) — remote agent interoperability.
- [OpenTelemetry](https://github.com/open-telemetry/opentelemetry-specification) — traces, metrics, and logs.
- [Open Policy Agent](https://github.com/open-policy-agent/opa) — policy evaluation candidate.
- [LiteLLM](https://github.com/BerriAI/litellm) — model gateway candidate.
- [Temporal](https://github.com/temporalio/temporal) — durable workflow engine candidate.

## Agent and channel projects

- [OpenJarvis](https://github.com/open-jarvis/OpenJarvis)
- [DeerFlow](https://github.com/bytedance/deer-flow)
- [OpenClaw](https://github.com/openclaw/openclaw)
- [Hermes Agent](https://github.com/NousResearch/hermes-agent)
- [OpenHands](https://github.com/All-Hands-AI/OpenHands)

## Knowledge, memory, and document projects

- [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp)
- [Mem0](https://github.com/mem0ai/mem0)
- [Graphiti](https://github.com/getzep/graphiti)
- [Docling](https://github.com/docling-project/docling)
- [Unlimited OCR](https://github.com/baidu/Unlimited-OCR)

## Voice, browser, automation, and media projects

- [Voicebox](https://github.com/jamiepine/voicebox)
- [Pipecat](https://github.com/pipecat-ai/pipecat)
- [openWakeWord](https://github.com/dscripka/openWakeWord)
- [Playwright MCP](https://github.com/microsoft/playwright-mcp)
- [Browser Use](https://github.com/browser-use/browser-use)
- [Cua](https://github.com/trycua/cua)
- [Activepieces](https://github.com/activepieces/activepieces)
- [Node-RED](https://github.com/node-red/node-red)
- [n8n](https://github.com/n8n-io/n8n)
- [HyperFrames](https://github.com/heygen-com/hyperframes)
- [OpenMontage](https://github.com/calesthio/OpenMontage)

## Security, evaluation, and supply-chain projects

- [SkillSpector](https://github.com/NVIDIA/skillspector)
- [Anthropic Cybersecurity Skills](https://github.com/mukul975/Anthropic-Cybersecurity-Skills)
- [Matt Pocock Skills](https://github.com/mattpocock/skills)
- [gstack](https://github.com/garrytan/gstack)
- [Promptfoo](https://github.com/promptfoo/promptfoo)
- [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai)
- [Langfuse](https://github.com/langfuse/langfuse)
- [Syft](https://github.com/anchore/syft)
- [Cosign](https://github.com/sigstore/cosign)

## Reading order

New contributors should read [Project Vision and Principles](Project-Vision-and-Principles), [System Architecture](System-Architecture), [Control Kernel and Task Lifecycle](Control-Kernel-and-Task-Lifecycle), [Security and Threat Model](Security-and-Threat-Model), [MVP Definition](MVP-Definition), and [Initial Backlog](Initial-Backlog) before selecting implementation work.

Project-specific decisions in this Wiki take precedence over patterns observed in upstream projects. Always verify the pinned version's license and documentation before adoption.

