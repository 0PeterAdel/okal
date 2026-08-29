# Required GitHub Repository Settings

Repository files express policy, but GitHub Settings must enforce it. Apply and
verify these settings before product implementation begins.

## `main` ruleset

Create an active branch ruleset named `main-protection` targeting the default
branch with:

- require a Pull Request before merging;
- require at least one approval;
- dismiss stale approvals after new commits;
- require review from CODEOWNERS;
- require all conversations to be resolved;
- require the `Repository policy` and `Markdown` status checks;
- block force pushes and branch deletion;
- prevent direct pushes, including administrator bypass during normal work;
- require linear history if squash/rebase is the selected merge policy.

Do not enable a bypass that defeats the handbook workflow. Emergency fixes use
an expedited PR and review.

## Pull Request settings

- Enable squash merge; retain another merge method only when the team needs it.
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
3. Open a test PR and confirm approval, conversation, CODEOWNERS, and status
   checks are required.
4. Confirm a failed check prevents merge.
5. Record the verification evidence in the governance task.

The GitHub integration used to bootstrap Okal cannot modify branch protection
or repository rulesets, so an administrator must apply this one-time settings
change in GitHub.
