# Contributing to Okal

Okal follows the [ShiftCore Team Handbook](https://platform.shiftcore.workers.dev/docs/handbook).
Every change, including documentation and CI changes, follows this lifecycle:

```text
Task → Branch → Commit → Push → Pull Request → Review → Fix comments
→ Approval or documented Solo review → Merge → Documentation update
```

## Before starting

- Select or create one task with a clear outcome and acceptance criteria.
- Pull the latest `main`.
- Confirm that the task is small enough to review.
- Identify security, privacy, compatibility, data, and resource impacts.

## Branches

Never work on or push directly to `main`.

Create one branch per task:

```text
type/short-task-name
```

Examples:

```text
feat/add-task-envelope
fix/receipt-chain-validation
docs/update-deployment-guide
security/restrict-worker-egress
ci/add-contract-checks
```

Allowed types are `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`,
`perf`, `ci`, `build`, `revert`, and `security`. Use lowercase and hyphens. When
Jira becomes active, insert the task key: `feat/OKAL-12-add-task-envelope`.

## Commits

Use Conventional Commits in the handbook format:

```text
type(scope): short message
```

Examples:

```text
feat(kernel): add task state transitions
fix(evidence): reject an incomplete receipt chain
docs(security): document worker egress policy
ci(governance): validate pull request metadata
```

Each commit represents one logical change. Do not use messages such as
`update`, `fix`, `final`, or `changes`.

## Pull Requests

Open every Pull Request from a task branch into `main`. Use this title before
Jira:

```text
type: short description
```

When Jira is active:

```text
[OKAL-12] type: short description
```

Complete the Pull Request template, link the task, explain how to review the
change, and include evidence. Keep the PR focused. UI changes include relevant
screenshots; API and behavior changes include tests and contract updates.

## Review

Use the review profile in GOVERNANCE.md. In Solo Maintainer mode the owner may
author, review and merge the same PR; no second person is required. With two or
more eligible human maintainers, request an independent reviewer able to judge
the affected security, architecture, identity, data, routing or deployment area.

While the repository has only one eligible human maintainer, follow the
[Solo Maintainer mode](GOVERNANCE.md#solo-maintainer-mode). There is no calendar
expiry or recurring renewal while that condition holds. The author
cannot approve their own PR; instead, record a non-approval self-review with
findings, evidence, risks, and the merge decision. This changes only the
approval requirement. Pull Requests, checks, conversations, and every other
merge gate remain mandatory.

Use these review prefixes:

- `Must change:` blocks merge.
- `Suggestion:` is optional.
- `Question:` requests clarification.
- `Nit:` is a small non-blocking detail.

The author addresses comments and resolves conversations only after the concern
is handled. Review the work, never the person.

### Solo self-review checklist

1. Read the complete Files changed diff and identify the current head SHA.
2. Check task acceptance criteria, test evidence, privacy/security impact and
   rollback or recovery. Record unresolved limitations rather than hiding them.
3. Wait for required checks on that same SHA; resolve findings and conversations.
4. Submit **Review changes → Comment** or a conversation comment containing:
   reviewed SHA, scope/findings, evidence, risks/rollback, and an explicit
   ready-to-merge or blocked decision. Do not select **Approve** on your own PR.
5. If ready and GitHub's merge gates pass, use **Squash and merge**. Do not use
   **Close pull request** for work that should be integrated.
6. If another commit arrives, review that change and record a refreshed decision
   for the new SHA. A checkbox or an automated review does not replace your review.

For PR #37, the owner review also records the decision on ADR-013 and this ongoing
solo profile. The documentation update itself is not an owner review. No runtime
or laptop deployment is claimed by merging that documentation PR.

## Merge rules

The PR author merges after independent approval or the active documented Solo
Maintainer self-review. Do not merge when:

- the applicable independent approval or Solo self-review record is missing;
- a required check is failing;
- a conversation is unresolved;
- the branch has conflicts;
- the PR contains unrelated work or secrets;
- requested changes remain open.

Delete the task branch after merge when it is no longer needed.

## Definition of done

A contribution is done when its acceptance criteria pass, tests and checks are
green, risks and limitations are documented, required docs are current, review
comments are resolved, the applicable approval or Solo self-review is recorded,
and the PR is merged.

See [Repository Governance](GOVERNANCE.md), [Security Policy](SECURITY.md), and
the [Okal Wiki](https://github.com/0PeterAdel/okal/wiki).
