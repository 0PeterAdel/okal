# Okal

**A verified, resource-aware personal AI operating system.**

Okal is a local-first control plane for personal AI. It gives one operator a
single identity, memory, policy boundary, evidence ledger, and capability
registry while delegating work to interchangeable models, tools, workflows,
and specialist agent runtimes.

Okal is not another monolithic chatbot and it does not merge upstream agent
projects into one codebase. It composes them through versioned adapters and
keeps authority in a small control kernel.

## Project status

The project is in **architecture and foundation planning**. No production or
security claims should be inferred until the corresponding quality gates in the
Wiki have passed.

## Start here

- [Project Wiki](https://github.com/0PeterAdel/okal/wiki)
- [Wiki source](wiki/Home.md)
- [MVP definition](wiki/MVP-Definition.md)
- [Roadmap](wiki/Roadmap-and-Release-Plan.md)
- [Initial backlog](wiki/Initial-Backlog.md)
- [Security model](wiki/Security-and-Threat-Model.md)
- [Architecture decisions](wiki/Architecture-Decision-Records.md)

## Core promises

- Local-first, cloud-optional execution.
- One authority boundary across every agent and tool.
- Least privilege and explicit approval for consequential actions.
- Source-grounded memory with provenance, correction, and deletion.
- Evidence-backed completion; no silent or unverifiable success.
- Interchangeable upstream components through stable contracts.
- Resource-aware routing across CPU, RAM, GPU, latency, privacy, and cost.
- Gated improvement through evaluation, promotion, and rollback.

## Documentation policy

The `wiki/` directory is the canonical source for the GitHub Wiki. Changes are
reviewed in the main repository and synchronized by
`.github/workflows/sync-wiki.yml`.

## License

Okal is licensed under the repository's MIT License. Upstream software, models,
datasets, skills, and media retain their own licenses. See
[Dependency Selection and Licensing](wiki/Dependency-Selection-and-Licensing.md).
