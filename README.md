# Okal

**One local personal assistant for mail, planning, social content and freelance opportunities.**

Okal is being refocused around daily routines, not a general-purpose AI operating
system or a collection of coding/research agents. One small center will own task
state, summaries, schedules and approvals. Desktop, mobile and later voice will
use the same authenticated API.

## Status: repository transition

Existing voice, Studio and agent pilots remain experimental. The new center,
automatic startup and mobile connection are **planned, not implemented by this
reset**. Existing installation commands do not install the new architecture.
Do not enable competing schedulers.

Tracking: [issue #36](https://github.com/0PeterAdel/okal/issues/36).
The architecture proposal requires review before adoption.

## Start here

- [Personal assistant plan and delivery gates](wiki/Personal-Assistant-Plan.md)
- [Preserved branches and local safety checks](docs/REPOSITORY-RESET.md)
- [Proposed ADR-013](wiki/Architecture-Decision-Records.md#adr-013--daily-personal-assistant-reset)
- [Wiki navigation](wiki/Home.md)

## Product scope

| Area | Intended outcome | First delivery |
|---|---|---|
| Mail | Digest, reply drafts and controlled sending | Read-only Gmail digest |
| Planning | Tasks, availability and a realistic day plan | Read calendar, propose changes |
| Social | Approved topics and source-grounded content | One external publisher adapter |
| Freelance | Opportunities, proposals and follow-up | One reviewed Khamsat adapter |
| Mobile | Unified summaries and task status | Read-only paired client |
| Voice | Optional input to the same boundary | Deferred |

## Boundaries

- Local inference through Ollama; no paid or cloud model fallback.
- Online accounts still require internet access and provider permission.
- Reuse upstream libraries/services through adapters; no wholesale forks.
- Code-first modular Python center, not microservices or an agent swarm.
- One durable task store and scheduling authority.
- Scoped approvals, duplicate guards and native verification for external writes.
- No generic shell execution or coding agent in the current product scope.
- A powered-off laptop cannot run jobs; recovery must be explicit.

## Documentation and contribution

The canonical Wiki lives in `wiki/`. Older designs and pilot runbooks are retained
as historical reference, not a second active backlog. Governance/security rules
remain binding; proposed ADR-013 does not silently override accepted decisions.

All changes use task branches and reviewed PRs; never push directly to main.
Read [CONTRIBUTING.md](CONTRIBUTING.md), [GOVERNANCE.md](GOVERNANCE.md),
[AGENTS.md](AGENTS.md) and [SECURITY.md](SECURITY.md).

## License

Okal is MIT licensed. Dependencies, weights and platform services retain their
own terms. See [Dependency Selection](wiki/Dependency-Selection-and-Licensing.md).
