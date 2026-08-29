# Repository Governance

The ShiftCore Team Handbook governs Okal's contribution workflow. This file
defines the repository-specific application of that handbook.

## Authority

- `main` is the production-ready source of truth.
- Issues or Jira work items define tasks and acceptance criteria.
- Accepted ADRs define durable architecture decisions.
- CODEOWNERS identifies required domain review.
- GitHub checks provide evidence; they do not replace human review.

## Change lifecycle

All changes use `Task → Branch → Commit → Pull Request → Review → Approval →
Merge`. Direct pushes, force pushes, and branch deletion on `main` are
prohibited. Emergency work uses the same PR path with a `security/` or `fix/`
branch and an expedited qualified review.

## Review ownership

| Change | Required expertise |
|---|---|
| Kernel state, events, receipts | architecture and reliability |
| Policy, identity, secrets, sandbox | security |
| Public API, schema, manifest | compatibility and SDK |
| Memory or personal data | privacy and data lifecycle |
| Models, prompts, routing | evaluation, privacy, and cost |
| Dependencies or skills | supply chain and licensing |
| UI, voice, accessibility | product and accessibility |
| CI, packaging, deployment | platform and operations |

At least one eligible reviewer approves every PR. Critical security or
architecture changes should receive two qualified reviews when the team permits.

## Maintainers

Maintainers triage tasks, assign reviewers, protect release quality, manage
repository settings, and coordinate incident response. Maintainer status does
not bypass required PRs, checks, or review.

## Merge and release

The PR author merges only after approval, resolved conversations, passing
checks, and conflict resolution. Prefer squash merge for a noisy branch; retain
logical commits when they provide useful review or rollback boundaries.

Releases require reviewed `main`, a changelog, test/evaluation evidence, SBOM
and license review when applicable, migration and rollback notes, and signed
artifacts when packaging begins.

## Exceptions

Workflow exceptions require a documented reason, owner, scope, expiry, and
follow-up task. No exception permits secret exposure, authorization bypass, or
unreviewed direct modification of `main`.

Required repository settings are documented in
[Repository Settings](docs/REPOSITORY-SETTINGS.md).
