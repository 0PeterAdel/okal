# Deployment and Operations

Okal is local-first and operationally boring by design. The default deployment runs on one trusted workstation; remote workers and cloud models are optional extensions with explicit data-routing rules.

## Supported topologies

| Topology | Use | Characteristics |
|---|---|---|
| Developer | contribution and tests | local processes, SQLite allowed, mock providers |
| Personal workstation | default production | Docker Compose or native services, PostgreSQL, local artifact store |
| Hybrid | constrained local hardware | local kernel plus authenticated remote model or GPU workers |
| Lab | evaluation and research | isolated workers, benchmark datasets, expanded telemetry |

Multi-tenant SaaS is not an MVP topology.

## Workstation services

The initial Compose profile contains the kernel API, web UI, PostgreSQL, policy service, telemetry collector, and optional model/voice/document workers. Heavy workers use profiles and are off by default. The artifact store begins as a protected local directory; an S3-compatible adapter is optional.

## Network boundaries

- Bind the UI and API to loopback by default.
- Do not expose model, database, browser, or execution-worker ports publicly.
- Authenticate every non-loopback worker with short-lived credentials and transport encryption.
- Apply egress allowlists per capability and workspace.
- Put remote workers behind a private overlay or equivalent trusted network.
- Treat inbound channel messages as untrusted content, not commands with inherited authority.

## Configuration

Configuration follows this precedence: secure runtime overrides, environment, local configuration file, compiled defaults. A startup report shows effective non-secret settings and their source. Unknown keys and invalid combinations fail fast.

Separate profiles define:

- model providers and privacy classes;
- resource budgets and GPU policy;
- enabled capabilities and risk levels;
- retention and redaction rules;
- telemetry destinations;
- channel and integration credentials by reference.

## Secrets

Production secrets are stored in the operating-system credential store or an approved secret manager. They are injected at execution time, scoped to the adapter, never written to receipts or logs, and rotated without rebuilding images.

## Backup and restore

A backup consists of a consistent database snapshot, artifact objects, encrypted configuration metadata, and receipt-chain checkpoints. Secrets are backed up separately by the user's credential system.

Restore is tested quarterly and before storage migrations. The recovery procedure verifies artifact digests and receipt chains before reopening execution.

## Updates and rollback

- Pin containers, Python/JavaScript dependencies, models, skills, and prompts.
- Verify signatures and checksums before installation.
- Run database migrations as explicit, reversible release steps.
- Retain the prior application image and compatible schema path.
- Roll out model and routing changes independently from kernel releases.
- Never auto-install a skill directly into the production trust tier.

## Health and readiness

`/api/v1/health` reports process liveness only. Readiness evaluates database migrations, artifact access, policy engine, queue state, and required capability adapters. Optional provider outages degrade named features without marking the kernel dead.

## Operational runbooks

Maintain tested runbooks for:

1. provider or network outage;
2. queue congestion or stuck task;
3. GPU out-of-memory and worker crash;
4. suspected secret leakage;
5. malicious or compromised skill;
6. corrupted artifact or receipt mismatch;
7. failed migration or rollback;
8. uncertain external side effect and reconciliation.

## Minimum workstation target

The reference constrained environment is 16 GB system RAM and an NVIDIA RTX 4060 with 8 GB VRAM. The system must remain usable by limiting concurrency, unloading idle models, using quantized local models, and routing oversized work to an approved remote provider.

## Acceptance criteria

- A new user can launch the default profile from documented prerequisites.
- The default installation exposes no service beyond loopback.
- Backup restore is automated, verified, and produces a report.
- A failed worker does not corrupt the task ledger and can resume safely.
- Upgrade and rollback procedures are exercised in release CI.

