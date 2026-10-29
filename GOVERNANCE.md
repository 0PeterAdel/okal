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

At least one eligible reviewer approves every PR when an independent eligible
reviewer exists. The temporary Solo Maintainer mode below is the only approval
exception. Critical security or architecture changes should receive two
qualified reviews when the team permits.

## Solo Maintainer mode

Okal begins with one eligible human maintainer. GitHub does not permit a Pull
Request author to approve their own work, so requiring one approval would make
the handbook workflow impossible without creating evidence that is not
independent.

While fewer than two eligible human maintainers have repository write access:

- every change still requires an Issue or Jira task, task branch, Pull Request,
  passing required checks, resolved conversations, and conflict resolution;
- required approval count is temporarily zero and CODEOWNERS approval is not a
  merge requirement;
- the author records a self-review as a non-approval Pull Request review or
  conversation comment, covering findings, evidence, risks, and merge decision;
- failed checks, unresolved findings, direct pushes, force pushes, and secret or
  authorization exceptions remain prohibited;
- major dependency, security-boundary, identity, permission, and destructive
  migration changes should seek external qualified review when practical.

This exception is owned by `0PeterAdel`. The owner confirmed on 2026-10-30 that
they remain the only person with repository write access. This is an owner
attestation, not an independent access audit or an approval of a particular PR.

The renewal proposed in [PR #37](https://github.com/0PeterAdel/okal/pull/37)
requires the owner's explicit non-approval self-review accepting the renewal
before merge. It does not retroactively authorize merges during the period after
the previous review deadline of 2026-09-30. Automated comments do not substitute
for this human record. Repository protection settings are not changed by this
document; any stricter enforced requirements still apply.

After that review and adoption, the exception expires at the earlier of:

- a second eligible human maintainer receiving repository write access; or
- 2026-11-30 at 23:59 in `Africa/Cairo`.

Review or replace this exception before that deadline. Track the follow-up in
[issue #36](https://github.com/0PeterAdel/okal/issues/36). Renewal requires another
explicit owner record and reviewed policy change; it is never automatic. At
expiry, stop using the zero-approval exception and require at least one eligible
independent approval, stale-approval dismissal, and CODEOWNERS review before
merge. This renewal changes only the time-bounded approval exception, not the
mandatory checks, self-review, conversation resolution or security boundaries.

## Trusted automation Pull Requests

Automation may use generated metadata only through an explicit, authenticated
exception. The current exception applies only when GitHub reports the PR author
as `dependabot[bot]` and the branch is inside the `dependabot/` namespace.
Branch naming alone never establishes trust.

The exception covers generated branch names, dependency-scoped titles, and the
generated PR description. It does not bypass commit validation, sensitive-file
and credential checks, conflict checks, Markdown and shell validation, required
status checks, human dependency review, or the merge rules. Major updates are
never auto-merged.

## Maintainers

Maintainers triage tasks, assign reviewers, protect release quality, manage
repository settings, and coordinate incident response. Maintainer status does
not bypass required PRs, checks, or review.

## Merge and release

The PR author merges only after independent approval or the active documented
Solo Maintainer self-review, resolved conversations, passing checks, and
conflict resolution. Prefer squash merge for a noisy branch; retain logical
commits when they provide useful review or rollback boundaries.

Releases require reviewed `main`, a changelog, test/evaluation evidence, SBOM
and license review when applicable, migration and rollback notes, and signed
artifacts when packaging begins.

## Exceptions

Workflow exceptions require a documented reason, owner, scope, expiry, and
follow-up task. No exception permits secret exposure, authorization bypass, or
unreviewed direct modification of `main`.

Required repository settings are documented in
[Repository Settings](docs/REPOSITORY-SETTINGS.md).
