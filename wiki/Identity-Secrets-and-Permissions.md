# Identity, Secrets, and Permissions

## Identity model

The MVP has one human operator, multiple trusted devices, multiple sessions, and
many non-human capability identities. Every action is attributable to an operator
request, schedule, webhook, or approved system maintenance event.

## Principals

- `operator` — the human authority;
- `device` — an enrolled desktop, mobile companion, or worker host;
- `session` — a bounded interaction context;
- `task` — a durable unit of intent;
- `capability-version` — an immutable executable identity;
- `worker-instance` — an ephemeral runtime identity;
- `service-account` — an external connector identity.

## Grant model

A grant contains principal, task, purpose, capability version, resources,
filesystem paths, network destinations, secret handles, action classes, expiry,
usage count, and revocation state. Grants are short-lived and non-transferable.

## Secret broker

Secrets remain outside prompts, manifests, logs, traces, and task artifacts. A
worker receives a handle that can be redeemed only by the approved capability
inside the allowed environment and time window.

Initial storage uses the operating-system keyring or an encrypted local store.
Vault/Infisical-style providers may be added behind the broker interface for
shared deployments.

## Connector scopes

Read and write credentials are separate when the provider permits. Examples:

- GitHub read context versus review/comment/push;
- Jira read issue versus edit/transition;
- email read versus draft versus send;
- calendar read versus create/edit/cancel;
- file read versus workspace write versus host write.

## Approval model

Approvals cannot be inferred from conversational politeness or third-party
content. They are structured decisions that display exact material fields. An
approval can be one-time, N-use, session-scoped, time-limited, or a narrow
standing rule. R3 actions are one-time by default.

## Device enrollment

New devices require operator verification, receive individual keys, declare
capabilities, and can be revoked independently. Device trust does not imply
unrestricted access to all memory or connectors.

## Redaction

Logs use allowlisted fields and structured redaction. Tests seed canary secrets
and verify they do not appear in prompts, traces, exceptions, stdout/stderr,
artifacts, model output, or network payloads outside the authorized connector.

## Recovery

The operator can list active sessions, grants, devices, and connector identities;
revoke them; rotate secrets; pause workflows; and export a sanitized incident
bundle. Recovery never prints secret values.
