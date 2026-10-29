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

All changes use `Task → Branch → Commit → Pull Request → Review → documented
Solo self-review or independent approval → Merge`. Direct pushes, force pushes,
and branch deletion on `main` are
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

The default profile is Solo Maintainer while `0PeterAdel` is the only eligible
human with repository write access. The same person may author, review and merge
their PR using the documented self-review below. A second reviewer is not a
prerequisite in that profile. Once a second eligible human has write access,
independent approval is required. Critical changes should receive two qualified
reviews when the team permits.

## Solo Maintainer mode

Okal is maintained by one eligible human. GitHub does not permit a Pull
Request author to approve their own work, so requiring one approval would make
the handbook workflow impossible without creating evidence that is not
independent.

While fewer than two eligible human maintainers have repository write access:

- every change still requires an Issue or Jira task, task branch, Pull Request,
  passing required checks, resolved conversations, and conflict resolution;
- required approval count is zero and CODEOWNERS approval is not a
  merge requirement;
- the author records a self-review as a non-approval Pull Request review or
  conversation comment, covering the reviewed head SHA, findings, evidence,
  risks, and merge decision;
- failed checks, unresolved findings, direct pushes, force pushes, and secret or
  authorization exceptions remain prohibited;
- major dependency, security-boundary, identity, permission, and destructive
  migration changes should seek external qualified review when practical.

This profile is owned by `0PeterAdel`. On 2026-10-30 the owner confirmed sole
write access and explicitly requested an ongoing solo workflow. That attestation
is not an independent access audit or approval of a particular PR. This profile
has no calendar expiry or periodic renewal requirement. It replaces the earlier
dated exception and proposed November renewal, without retroactively authorizing
past merges. Other workflow exceptions remain subject to the Exceptions section.

Use **Review changes → Comment**, or a PR conversation comment, not **Approve**.
Inspect the complete diff and actual check results first. State the reviewed head
SHA and the decision explicitly; a filled template or AI-generated comment is not
human review. After any new commit, refresh the review against the new head and
wait for its required checks. Only the owner records their human self-review;
automation must never impersonate it. See the practical checklist in
[Contributing](CONTRIBUTING.md#solo-self-review-checklist).

The profile ends when a second eligible human receives write access. Before the
next merge, switch to at least one independent approval, stale-approval dismissal
and CODEOWNERS review using the repository settings guide. Do not substitute bots
or the author's other accounts for independent review. Documentation does not
change GitHub protection settings; stricter enforced rules must still be met.

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
