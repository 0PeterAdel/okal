# Delivery Workflow and Contributing

Okal welcomes focused contributions that preserve the kernel's authority, replaceable boundaries, and evidence model.

## Working model

- Keep `main` releasable.
- Use short-lived branches and small, reviewable pull requests.
- Open a draft PR early for architectural or security-sensitive work.
- Prefer vertical increments that include contracts, behavior, tests, telemetry, and docs.
- Do not merge generated artifacts whose source is missing.

Conventional Commit prefixes are recommended: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`, and `security`.

## Issue readiness

An implementation issue should state the user outcome, scope and non-goals, acceptance criteria, dependencies, risk class, data/privacy impact, resource budget, and expected evidence. Larger work links to an epic in the [Initial Backlog](Initial-Backlog).

## Change path

1. Confirm an issue or decision record exists.
2. Update the relevant contract before adding an adapter-specific shortcut.
3. Implement the smallest end-to-end slice.
4. Add failure, denial, retry, cancellation, and resume coverage.
5. Run local fast checks and applicable integration/evaluation suites.
6. Update Wiki pages, manifests, migrations, and runbooks in the same PR.
7. Request the required reviewers and resolve findings with evidence.

## Review ownership

| Change | Required review focus |
|---|---|
| Kernel state or receipts | architecture and reliability |
| Policy, identity, secrets, sandbox | security |
| Public API, event, manifest | compatibility and SDK |
| Memory or personal data | privacy and deletion |
| Model/routing/prompt | evaluation and cost |
| Dependency or skill | supply chain and license |
| UI/voice accessibility | product and accessibility |

Until CODEOWNERS is established, maintainers assign these roles explicitly.

## Pull request evidence

A PR description includes:

- the behavior before and after;
- linked issue and ADR where applicable;
- test and evaluation results;
- screenshots or traces only when they add verification value;
- threat, privacy, migration, compatibility, cost, and resource impacts;
- rollback plan for operational changes.

## Architecture decisions

Open an ADR when a change affects authority, trust boundaries, protocol choice, data lifecycle, compatibility, or a hard-to-reverse dependency. Small implementation details stay in code and tests.

## Dependencies

New dependencies require purpose, maintenance health, exact license, transitive/license report, alternatives considered, security posture, update policy, and boundary classification. Model weights and datasets are reviewed independently from code.

## Security reports

Do not publish exploitable vulnerabilities in a public issue. Use the repository's private security reporting once enabled. Until then, contact the maintainer privately and include minimal reproduction details without live credentials or personal data.

## Release process

1. Freeze contract and migration changes for the candidate.
2. Generate SBOM, provenance, license, and evaluation reports.
3. Exercise install, upgrade, backup, restore, and rollback.
4. Review critical risks and waived regressions.
5. Tag and sign the release from protected main.
6. Publish notes with compatibility and known limitations.
7. Monitor the canary and retain the previous release.

## Community standard

Discussion must be specific, respectful, and evidence-led. Generated contributions are acceptable only when the contributor understands, tests, and takes responsibility for the result.

