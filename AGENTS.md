# Repository Instructions for AI Agents

These instructions apply to the entire repository. The [ShiftCore Team
Handbook](https://platform.shiftcore.workers.dev/docs/handbook) is the source
of truth for Git and review behavior.

## Required workflow

1. Start from the latest `main`.
2. Work from a task with explicit acceptance criteria.
3. Create one branch per task using `type/short-task-name`.
4. Keep changes focused and commits small.
5. Use `type(scope): short message` for every commit.
6. Push only the task branch and open a Pull Request into `main`.
7. Request an eligible reviewer and address every review comment. If the
   documented Solo Maintainer mode is active, record the required non-approval
   self-review instead.
8. Merge only after the applicable approval or Solo self-review, resolved
   conversations, and passing checks.

Never commit or push directly to `main`. Never merge a Pull Request merely to
finish an automated task.

Allowed branch and commit types are `feat`, `fix`, `docs`, `style`, `refactor`,
`test`, `chore`, `perf`, `ci`, `build`, `revert`, and `security`.

## Review communication

Prefix review comments with one of:

- `Must change:` for a merge blocker.
- `Suggestion:` for an optional improvement.
- `Question:` when clarification is required.
- `Nit:` for a small non-blocking detail.

Comments must be respectful, specific, and directed at the work rather than the
author.

## Engineering requirements

- Do not mix unrelated changes.
- Do not add secrets, private keys, tokens, local configuration, or personal
  data. Use documented placeholders and `.env.example`.
- Update contracts, tests, documentation, threat notes, and runbooks with the
  behavior they govern.
- Preserve the thin authoritative kernel and adapter boundaries documented in
  the Wiki.
- Run `bash scripts/validate-governance.sh` before requesting review when the
  script is present.
- Treat failing CI, unresolved comments, conflicts, or a missing applicable
  approval or Solo self-review as hard merge blockers.
- Do not imitate trusted automation. Generated metadata is accepted only when
  GitHub authenticates the exact automation account documented in governance.

## Source-of-truth order

When instructions conflict, use this order:

1. Legal, security, and platform policy.
2. ShiftCore Team Handbook.
3. Accepted Okal architecture decisions and Wiki requirements.
4. The task and its acceptance criteria.
5. Local implementation preferences.
