# Mail upstream and dependency review

Inspected 2026-10-30 for [#40](https://github.com/0PeterAdel/okal/issues/40).
Source inspection, not a benchmark or full security audit of competing products.
Selection criteria: one owner, existing Python core, no paid model services,
replaceable adapters, minimal extra running services and explicit permissions.

## Reuse decisions

| Project / revision | What was inspected | Decision |
|---|---|---|
| [Google client c1bdb24](https://github.com/googleapis/google-api-python-client/tree/c1bdb24533614d6fcffeb7b9a93b2fc836c4e4e0) | Official Gmail quickstart, OAuth documentation, bundled discovery | Reuse API schema/client and official authentication libraries |
| [SummerMail ec48ce7](https://github.com/wanleung/summermail/tree/ec48ce7385c642ca4ee64a82dfa8698edcac315b) | Compose, IMAP reader and digest prompt | Reference for fetch/classify/digest decomposition; not its five-service stack |
| [Inbox Zero 0bcf495](https://github.com/elie222/inbox-zero/tree/0bcf49572e295003f12634fc909905a2e77973f8) | Compose, digest claims and database test source | Reference for atomic claims/stale-worker cases; no Next/Postgres/Redis runtime added |
| [n8n 990ca84](https://github.com/n8n-io/n8n/tree/990ca84c230eba462708d18f04c091d352b2a1da) | Gmail/Ollama docs and license | Viable alternative if integration maintenance grows; not another scheduler now |
| [Old Okal 9a0300d](https://github.com/0PeterAdel/okal/tree/9a0300df1b38c914bbb1686cee5843f8573a88bc) | Gmail script and four offline test definitions | Retain requirements; fix inbox-only coverage, separate JSON progress and account-index links |

SummerMail's reviewed fetcher selects INBOX and its deployment includes SMTP
delivery, which does not match the read-only default. Its README declares GPL-3.0
or later. Inbox Zero's LICENSE contains AGPL text plus additional terms; this is
not treated as a plain permissive license. n8n uses Sustainable Use/enterprise
distinctions. No code from these three projects was copied into Okal; no legal
compatibility judgment or license exception is assumed.

Google's client remains officially supported in maintenance mode. The old
google-auth-oauthlib repository was archived after moving into google-cloud-python;
the maintained package is used. Discovery documents add disk size, not an assumed
equivalent amount of process RSS. Optional dependencies load only for mail actions.

Google/Ollama/APScheduler supply the protocol/model/trigger mechanisms. Okal adds
the small account, persistence and approval boundaries specific to this project;
no generic agent framework, vector database or workflow designer is introduced.

## Exact direct dependencies

`requirements-mail.lock` contains 40 exact hash-locked packages, including the
existing core. No upstream source tree is vendored. Reinstall with hash checking.

| Package | Version | Purpose / declared license |
|---|---|---|
| google-api-python-client | 2.201.0 | Discovery client, Apache-2.0 |
| google-auth | 2.62.0 | Credential lifecycle, Apache-2.0 |
| google-auth-oauthlib | 1.5.0 | Desktop consent/PKCE flow, Apache-2.0 |
| google-auth-httplib2 | 0.4.4 | Google client dependency, Apache-2.0 |
| APScheduler | 3.11.3 | Daily timezone trigger calculation, MIT |
| httpx | 0.28.1 | Bounded non-redirecting transport, BSD-3-Clause |

The Gmail discovery client uses a narrow HTTPX transport adapter rather than
httplib2's default connection retry behavior. Inspection of installed httplib2
0.32.1 showed a BadStatusLine resend path even when the client-level retry count
is zero. Sending must not replay an uncertain write. Tests exercise the real
discovery client with a failing fake HTTP transport and assert one POST only.
Google-auth still owns authentication; no hand-implemented OAuth protocol.

## Transitive license intake

Installed distribution metadata was inspected for every locked package. Existing
core pins/license details are in [Core Dependencies](CORE-DEPENDENCIES.md).
Additional transitive components are grouped below; exact versions are in the
lock and [CycloneDX inventory](../apps/core/evidence/mail-sbom.json).

| Declared license | Additional packages |
|---|---|
| Apache-2.0 | google-api-core, googleapis-common-protos, proto-plus, requests |
| Apache-2.0 OR BSD-3-Clause | cryptography |
| MIT | charset-normalizer, httplib2, pyparsing, tzlocal, urllib3 |
| MIT-0 | cffi |
| BSD-3-Clause | httpcore, protobuf, pycparser |
| BSD-2-Clause / BSD declaration | pyasn1 / pyasn1-modules |
| BSD-3-Clause | oauthlib |
| ISC | requests-oauthlib |
| BSD-3-Clause OR Apache-2.0 | uritemplate |
| MPL-2.0 | certifi |

Preserve notices when distributing packages; certifi's MPL declaration is not
relabelled MIT. Metadata intake does not replace a legal review of redistribution.
No enterprise package or paid API is enabled by the install. Provider terms and
any future pricing changes remain an onboarding check, not a promise forever.

`pip-audit 2.9.0` reported no known vulnerabilities for the pinned mail lock on
2026-10-30. SBOM is committed. This is point-in-time advisory evidence, not proof
of absence of vulnerabilities. Existing Starlette/httpx test-client deprecation
warning remains visible; it is not silently suppressed.

## Destinations and privacy

- Desktop OAuth: Google's configured official accounts/token endpoints only.
- Gmail: fixed `https://gmail.googleapis.com/gmail/v1/users/me/` resources.
- Local inference: fixed `http://127.0.0.1:11434`, reviewed local GGUF digest.
- Model/cloud configuration: requires explicit operator local-only attestation;
  remote-model metadata and digest mismatches are rejected before prompts.
- No email-supplied links, remote images, attachment IDs or arbitrary tools are
  executed. No telemetry exporter is configured by this module.
- No full incoming bodies in SQLite; metadata, summaries, outgoing draft bodies
  and send receipts are still sensitive. OAuth files are separate/private.

Rollback swaps the optional adapter/dependencies while retaining core records.
Replacing Gmail later requires a provider-specific adapter, not a second center.
Do not use a smaller unofficial OAuth implementation to save package disk size.

## Evidence limitations and owner acceptance

Unit/transport/model tests use synthetic payloads; no real Gmail authorization,
send, live model inference or quality benchmark was performed. No upstream
project's test suite was claimed as executed. Before enabling live use, verify
the exact account, read-only grant, model digest, cloud-disabled server, a private
Arabic/English digest, source links and recovery. Optional sending additionally
needs a separately consented grant and one explicitly approved native test.

[Validation record](../apps/core/evidence/mail-validation.json): 80 tests on each
of Python 3.12.14 and 3.14.8 (25 core + 55 mail), plus real-process core restart.
The mail unit suite blocks real socket connections; transport/model responses
are mocked. Passing synthetic tests does not measure model quality or GPU speed.

Useful primary documentation:

- [Google Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python)
- [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Gmail pagination](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list)
- [Search timezone differences](https://developers.google.com/workspace/gmail/api/guides/filtering)
- [Reply thread requirements](https://developers.google.com/workspace/gmail/api/guides/threads)
- [OAuth lifecycle](https://developers.google.com/identity/protocols/oauth2)
- [Ollama structured output](https://docs.ollama.com/capabilities/structured-outputs)
- [Ollama local-only setting](https://docs.ollama.com/faq)
- [APScheduler 3.x trigger](https://apscheduler.readthedocs.io/en/3.x/modules/triggers/cron.html)

## Gmail history/triage follow-up review (2026-10-31, PR #42)

The owner also supplied the Google Workspace CLI
([gws-gmail](https://www.skills.sh/googleworkspace/cli/gws-gmail),
[gws-gmail-triage](https://www.skills.sh/googleworkspace/cli/gws-gmail-triage),
[gws-gmail-read](https://github.com/googleworkspace/cli/blob/main/skills/gws-gmail-read/SKILL.md),
[gws-gmail-reply](https://github.com/googleworkspace/cli/blob/main/skills/gws-gmail-reply/SKILL.md),
[gws-gmail-watch](https://github.com/googleworkspace/cli/blob/main/skills/gws-gmail-watch/SKILL.md),
[email-to-task](https://github.com/googleworkspace/cli/blob/main/skills/gws-workflow-email-to-task/SKILL.md),
[executive assistant](https://github.com/googleworkspace/cli/blob/main/skills/persona-exec-assistant/SKILL.md),
[label-and-archive](https://github.com/googleworkspace/cli/blob/main/skills/recipe-label-and-archive-emails/SKILL.md)),
[Google Workspace MCP](https://github.com/taylorwilsdon/google_workspace_mcp),
and [Inbox Zero](https://github.com/elie222/inbox-zero).

The useful patterns are bounded provider operations, source-grounded read and
triage views, and explicit separation between observing a message and executing
a reply/label/archive action. Google Workspace CLI's Gmail watch pattern uses
Google Cloud Pub/Sub infrastructure; for this one-owner, free-only, local
service we chose restart-safe paginated Gmail history polling rather than
adding Pub/Sub/another background daemon. Google Workspace MCP provides a
reference for separable provider tools, but exposing provider writes as
general-purpose agent tools would violate OKAL's exact-content sending gate.
Inbox Zero provides product references for action grouping and inbox views;
its runtime/data architecture and licensing were not imported or copied.

The new code uses the official Gmail history protocol directly and does not
install any of those upstream agents/CLI integrations, execute downloaded
skills, add remote LLM calls, or silently grant send/modify scopes.
See [history sync operations](MAIL-HISTORY-SYNC.md). This was a design-pattern
comparison, not an exhaustive audit or benchmark of every upstream tool.
