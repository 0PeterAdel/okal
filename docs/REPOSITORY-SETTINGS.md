# Required GitHub Repository Settings

Repository files express policy, but GitHub Settings must enforce it. Apply and
verify these settings before product implementation begins.

## `main` ruleset

Create an active branch ruleset named `main-protection` targeting the default
branch with:

- require a Pull Request before merging;
- require all conversations to be resolved;
- require the `Repository policy` and `Markdown` status checks;
- block force pushes and branch deletion;
- prevent direct pushes, including administrator bypass during normal work;
- allow squash merge and require linear history;
- keep the ruleset enforcement status set to `Active`.

Apply the review profile that matches the repository phase:

| Setting | Solo Maintainer | Two or more eligible maintainers |
|---|---:|---:|
| Required approvals | 0 | At least 1 |
| Dismiss stale approvals | Not applicable | Enabled |
| Require CODEOWNERS review | Disabled | Enabled |
| Require last-push approval | Disabled | Enabled when practical |

Solo Maintainer mode is a bounded approval exception only. The Pull Request,
status-check, conversation, deletion, force-push, and direct-push protections
remain active. Its owner, evidence requirement, review date, and automatic exit
condition are defined in [Repository Governance](../GOVERNANCE.md#solo-maintainer-mode).

Do not enable a bypass that defeats the handbook workflow. Emergency fixes use
an expedited PR and review.

## Pull Request settings

- Enable squash merge and disable merge commits and rebase merge while linear
  history is required.
- Automatically delete head branches after merge.
- Enable automatic update branches if available.
- Do not enable auto-merge until required checks and review rules are active.

## Security settings

- Enable private vulnerability reporting.
- Enable Dependabot alerts and security updates.
- Enable secret scanning and push protection where the plan supports them.
- Review access using least privilege; reserve Admin for repository owners.
- Require each contributor to use their own account and verified Git identity.

## Verification

After applying the settings:

1. Confirm GitHub reports `main` as protected.
2. Attempt a harmless direct push from a non-bypass account and confirm denial.
3. Open a test PR and confirm the active phase's review profile, conversation
   resolution, and status checks are required.
4. Confirm a failed check prevents merge.
5. Confirm the REST branch response reports `protected: true` and the
   `main-protection` ruleset reports `enforcement: active`.
6. Record the verification evidence in the governance task.

The GitHub integration used to bootstrap Okal cannot modify branch protection
or repository rulesets, so an administrator must apply this one-time settings
change in GitHub.
