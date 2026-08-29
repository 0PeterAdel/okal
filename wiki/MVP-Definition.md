# MVP Definition

The MVP proves one complete, governed workflow rather than a collection of disconnected demos.

## Product statement

On a personal workstation, Okal accepts an Arabic or English text/voice request, gathers evidence from an Arabic PDF, a GitHub repository, and a GitHub or Jira work item, plans and executes a code change in a sandbox, runs tests, prepares a review, and requests approval before publishing any external change. Every material action is attributable and verifiable.

## Showcase scenario

> “Read this Arabic specification PDF and the linked GitHub/Jira work item, find the affected code, implement the change, test it, and prepare the result for my approval.”

The happy path is:

1. Ingest the request by text or push-to-talk voice.
2. Resolve the repository, work item, attached PDF, and intended outcome.
3. Extract Arabic document structure and cite relevant pages/regions.
4. Index and retrieve the affected code with provenance.
5. Generate a plan with risks, permissions, resource estimate, and approval points.
6. Create an isolated workspace and execute the code change.
7. Run deterministic tests and relevant evaluation checks.
8. Produce a diff, explanation, citations, artifacts, and evidence receipts.
9. Ask for approval before opening or updating a pull request.
10. On approval, perform the GitHub action and verify the native state.

## In scope

- Single user and one primary workstation.
- Web UI, CLI, and push-to-talk voice; wake word is optional after stability.
- Arabic and English input/output.
- GitHub, local filesystem, shell sandbox, and PDF/document capabilities.
- One local model path and at least one optional remote provider.
- Durable task state, pause/resume, approvals, cancellation, and reconciliation.
- Layered memory with provenance, user controls, and deletion.
- Resource broker for RAM/VRAM and one GPU-heavy job at a time.
- Capability manifests, policy decisions, sandboxing, and evidence receipts.
- Evaluation harness and a reproducible clean-install demo.

## Out of scope

- Multi-tenant SaaS, organization administration, or billing.
- Unsupervised high-risk actions or autonomous financial/legal/medical decisions.
- Always-on ambient surveillance or automatic recording.
- General phone/desktop control without capability-specific grants.
- Self-modifying production code or automatic skill promotion.
- Training a foundation model from scratch.
- Supporting every upstream runtime or channel in the first release.

## Required capabilities

| Capability | MVP behavior |
|---|---|
| Conversation | streaming Arabic/English, attachments, task state |
| Voice | local STT/TTS path, interruption, visible recording state |
| Documents | PDF parsing/OCR, page citations, artifact provenance |
| Code | repository map, search, patch, tests, diff, sandbox |
| GitHub | read issue/repo, propose PR, approve-before-write |
| Jira | read work item and acceptance context; no MVP write required |
| Models | local/remote routing with privacy and budget constraints |
| Memory | task, episodic, semantic, code, and preference layers |
| Governance | manifests, grants, approvals, policy, receipts |
| Operations | metrics, logs, traces, backup, resume, resource limits |

## Release acceptance

The MVP is accepted only when:

- the showcase completes on the reference 16 GB RAM/8 GB VRAM system;
- every answer about the PDF or code links to provenance;
- no GitHub write occurs before a clearly previewed approval;
- a worker or provider can fail mid-task and resume without duplicate writes;
- policy denial, cancellation, and uncertain-outcome paths are demonstrated;
- receipt verification detects any changed request, output, or manifest;
- clean installation and rollback work from published documentation;
- security and evaluation gates have no unwaived critical failure.

## MVP deliverables

- runnable kernel, UI, CLI, and selected workers;
- versioned capability SDK and starter manifests;
- local deployment profile and setup wizard;
- documented showcase repository and Arabic PDF fixture;
- evaluation suite, threat model, SBOM, license report, and signed release;
- complete Wiki, runbooks, contributor guide, and roadmap for the next release.
