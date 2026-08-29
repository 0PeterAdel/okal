# Security Policy

## Reporting a vulnerability

Do not report exploitable vulnerabilities, credentials, or personal data in a
public issue. Use GitHub's private vulnerability reporting from the repository
Security tab when available. If it is unavailable, contact the repository owner
through GitHub to establish a private reporting channel before sharing details.

Include the affected component and version, impact, minimal reproduction,
suggested mitigation if known, and whether the issue is already being exploited.
Never include live secrets.

## Response

Maintainers will acknowledge a valid private report, assign a severity and
owner, contain exposure, prepare a reviewed fix, and coordinate disclosure.
Exact timelines depend on severity and reproducibility.

## Secret handling

Never commit `.env` files, tokens, passwords, private keys, credentials,
database dumps, or private configuration. Use `.env.example` with names and safe
placeholders only.

If a secret is committed:

1. Report it immediately.
2. Revoke or rotate it before treating repository cleanup as sufficient.
3. Remove it from the repository and history where appropriate.
4. Check logs, artifacts, forks, caches, and downstream systems.
5. Add preventive ignore and scanning rules.
6. Record the incident and corrective action privately.

## Security-sensitive changes

Authentication, authorization, sandboxing, policy, secrets, network egress,
memory privacy, receipt integrity, supply chain, and release changes require a
qualified security review. Failing checks, unresolved `Must change` comments,
or uncertain side effects block merge.

The project's detailed threat model is maintained in the
[Security and Threat Model](https://github.com/0PeterAdel/okal/wiki/Security-and-Threat-Model).
