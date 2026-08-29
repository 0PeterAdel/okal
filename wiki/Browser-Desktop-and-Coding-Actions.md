# Browser, Desktop, and Coding Actions

## Action hierarchy

Okal selects the most structured and least ambiguous interface available:

1. Official API or dedicated connector.
2. Deterministic CLI or library.
3. Structured browser automation through Playwright accessibility snapshots.
4. Browser Use for adaptive web tasks.
5. Visual coordinate interaction.
6. Full desktop computer use through an isolated Cua environment.

Moving down the hierarchy requires evidence that the higher-level option is
unavailable or insufficient.

## Browser session policy

- Use isolated profiles by default.
- Separate browsing identity and cookies by task scope.
- Restrict downloads and uploads to the task workspace.
- Apply destination allowlists and SSRF protection.
- Mark website content as untrusted.
- Require approval before form submission, messaging, purchasing, sharing, or
  other consequential state changes unless a narrow standing grant exists.
- Capture before/after state and provider confirmation for writes.

## Desktop policy

Visual desktop control runs in a VM or isolated desktop session where possible.
Host control is disabled in the MVP. The operator can view the session, cancel
it, and inspect granted devices, paths, and network destinations.

## Coding worker

OpenHands is the priority specialist adapter, while the kernel remains agent-
agnostic. codebase-memory-mcp supplies structural context. Coding work occurs in
an isolated worktree or checkout with an explicit base commit.

## Coding workflow

1. Resolve repository, base, head, and cleanliness.
2. Create isolated workspace and record source commit.
3. Retrieve architecture context and relevant requirements.
4. Produce an implementation or review plan.
5. Apply changes only inside the workspace.
6. Run formatting, targeted tests, full relevant tests, static checks, and build.
7. Capture diffs, commands, exit status, artifacts, and environment.
8. Verify no untracked secret or unrelated change is included.
9. Request approval before pushing, opening a PR, or submitting review text.

## Repository truth

Receipts bind to repository, commit, worktree state, command, environment, and
output hashes. Passing tests against a different commit cannot satisfy the task.
The system distinguishes build success, test success, static analysis, and
functional acceptance.

## High-risk boundaries

- No access to host SSH keys or broad home directories.
- No arbitrary `sudo`.
- No execution of repository instructions that widen permission.
- New dependencies pass license and vulnerability checks.
- Secrets are injected as short-lived handles, never written to files or prompts.
- Force push, branch deletion, release publication, and merge are separate R3/R2
  actions according to repository policy.

## MVP acceptance

Okal can inspect a repository, run a pinned test workflow, produce a review with
evidence, and draft—but not submit—a GitHub response until approved. Desktop host
automation is post-MVP; isolated browser automation is included in the showcase.
