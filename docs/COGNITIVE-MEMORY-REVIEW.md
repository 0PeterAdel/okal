# Cognitive Memory V2 — AI-assisted engineering review

Task [#124](https://github.com/0PeterAdel/okal/issues/124), PR
[#125](https://github.com/0PeterAdel/okal/pull/125). This is AI-assisted verification,
not human approval or an independently authored third-party security audit.
The exact reviewed delivery head and current-head CI are recorded on the PR.
Production rollout remains separate.

## Scope and method

Reviewed the complete runtime diff from baseline
`08d51e8b81468fd82684b28ec5ab8434f22a31cc`: SQLite migration and lifecycle,
conversation/source graph, leases and outboxes, Mem0 process/provider boundary,
Qdrant ownership, learning/retrieval/context, vault/imports, API authorization,
frontend state and accessible controls, dependency locks, evaluation tools,
CI and rollback documentation. Follow-up review inspected each corrective diff.
No computer-action permission architecture or Production configuration was replaced.

The evidence includes real local model inference, real persistent Mem0/Qdrant,
real Chromium/FastAPI processes, a real governed filesystem action and receipt,
an actual Obsidian edit/import, actual parent SIGKILL/lease recovery, and a
synthetic database created and restored with the previous Core code. Scripted
archive assistant turns are labelled fixtures and never counted as model answers.

## Resolved findings

- **Must change: source and scope confusion.** Extraction now accepts exact
  committed owner quotes, validates scope independently of model metadata, keeps
  per-chat pending work separate, and requires explicit stable project identity.
  Owner claims about completed work do not become verified receipts. The real
  action scenario demonstrated that remembered permission claims cannot satisfy
  the existing approval digest or mutate files without runtime approval.
- **Must change: correction/backfill ordering and forgetting resurrection.**
  Logical source/write ordering and CAS fence older jobs and concurrent edits;
  version/source graph checks fence stale vectors and cached/in-flight replies.
  Subject tombstones prevent historical reingestion. Forgotten spans, revision
  bodies and managed notes are removed; other owner text survives. Legacy turns
  receive a conservative dependency chain because their original transitive
  provenance was not recorded. The migration rehearsal and crash tests passed.
- **Must change: credentials bypassing sensitive consent or legacy projections.**
  Credential categories are forbidden even with consent. Legacy credential
  records are quarantined from active recall, FTS, vectors, vault exports and
  owner memory views; the private raw archive is preserved for explicit owner
  review/deletion. Common medical/financial canaries require the controlled
  sensitive editor and cannot be silently learned or added as project notes.
- **Must change: stale or changed vault content acquiring authority.** Imports
  require active ID, base revision/hash and the exact previewed content hash.
  A changed file returns 409 without a ledger write. Curated-kind moves preserve
  independent owner edits as conflicts and reconcile one note per ID. Project
  overviews link only curated note kinds. Real browser race tests passed for
  memory and project imports; forgotten/rediscovered notes cannot resurrect facts.
- **Must change: intelligence package defaults and private-file scope.** Mem0
  runs in a separate hash-locked environment with explicit pinned local providers,
  no default cloud configuration, telemetry or model pulls. Its private
  `cognitive/adapter` scope excludes the authoritative DB, vault and Obsidian
  profile. The real adapter lifecycle/Arabic extraction and denied sibling-file,
  external-DNS/network/subprocess probes passed.
- **Must change: loss of explicit preferences and inaccurate answers.** Earlier
  failed pilots/full results remain published. Exact-source rules supplement
  omitted identity and durable instructions; general and conditional language
  remain distinct. Trusted question guidance distinguishes owner-name spelling,
  dialect and reply length without injecting expected benchmark facts. The
  expanded real-model personalization scenario passed all 26 unchanged checks.
  Full-corpus and final-code answer replay gates remain independently required.
- **Must change: older projects hidden by the recent-200 UI limit.** Name lookup
  now streams the catalog independently of UI paging and resolves descriptions
  and clarification choices by stable ID/name. Paging preserves the active
  project. SQLite and real Chromium checks reached project 201 using keyboard
  controls and verified mobile/tablet fit.

## Privacy and security boundaries

The Core SQLite ledger remains authoritative. Mem0 and Qdrant contain rebuildable
approved projections; SDK change history is purged. The clean Markdown adapter
contains no Basic Memory code or linked AGPL runtime. Basic Memory graph/MCP/cloud
features are unsupported; the documented Obsidian-compatible fallback is used.
Chat, archive and manual memory remain usable without the optional adapter/vault.

All memory routes use the existing owner-browser, Origin/Host and same-origin
boundary; device read tokens do not acquire memory authority. JSON bodies,
model/RPC payloads, responses, selected context and work per tick are bounded.
Frontend text is rendered inertly, source/correction labels remain explicit,
and forgetting/logout/conversation changes fence stale displayed private content.
Memory never supplies action approvals or changes security policy.

Python audit hooks are defense in depth against accidental package access, not
an OS sandbox against malicious native code. The optional offline Obsidian
launcher separately uses a network namespace and minimal filesystem mounts.
No unrestricted root execution is exposed to any model.

## Evidence interpretation and remaining limits

The [implementation report](COGNITIVE-MEMORY.md) links measured runs, failed
attempts, pinned dependencies/digests, performance and limitations. The read-only
answer audit requires support in actual sent ledger revisions or archive excerpts;
it does not credit unjournalled trimmed HISTORY/checkpoints. Keyword/concept
scoring is a bounded benchmark, not proof of general semantic equivalence.
Whole-device sampled RAM/VRAM include the desktop, services and concurrent tests;
they are not exclusive process attribution or unsampled maximums. Network counters
observe Python paths rather than native-code packet captures.

The 200 synthetic conversations/1,000 owner turns are not the owner's history.
There is no claim of recovery of purged data, proprietary ChatGPT parity, or a
complete screen-reader/WCAG certification. Sensitive-category heuristics are
conservative and cannot recognize every possible secret or medical fact in every
language. Small-model answers may still be awkward or excessively cautious.

The old exact 90-day chat / 365-day memory defaults become indefinite under the
owner's directive; historical explicit selection of those exact values was not
recorded, so it cannot be distinguished. Other finite choices are preserved.
Explicit forgetting/expiry invalidates dependent answers and redacts source spans;
independent backups and snapshots require their own retention handling.

## Delivery decision

Keep the PR draft until full ingestion, source-supported answer thresholds,
required negative/lifecycle/correction probes, final-code replay, complete CI and
the exact-head owner-authorized merge gate pass. Never merge a failed run merely
to finish the task. The [rollout runbook](COGNITIVE-MEMORY-ROLLOUT.md) requires a
separate private owner-data backup/rehearsal and rollback check before deployment.
