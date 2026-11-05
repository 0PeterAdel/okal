# Cognitive Memory V2

Implementation task: [#124](https://github.com/0PeterAdel/okal/issues/124).
This document tracks implementation and verified evidence. It is not a release
or deployment claim. Production remains on the Stage 3 release during development.

## Authority and isolation

SQLite remains the only authoritative conversation and memory ledger.
`chat_turns` stores committed owner messages and assistant answers;
`chat_memories` remains the current memory view. Cognitive tables add revisions,
exact source quotes, project associations, extractive conversation checkpoints,
durable ingestion leases, deletion tombstones and a reconciliation outbox.
Neither vector results nor Markdown can create authority on their own.

Mem0 OSS runs in a separate Python process and environment. Its Qdrant index and
internal history are disposable projections. Retrieval returns ledger IDs and
revisions; Core validates those against the active SQLite records. Mem0's own
change history is erased after reconciliation, rather than becoming an
independent personal archive. An exclusive filesystem lock gives the embedded
index one process owner. Core must remain usable when this adapter is unavailable.

## Reviewed dependencies and local inference

The dedicated [input](../apps/core/requirements-memory.in) and
[hash lock](../apps/core/requirements-memory.lock) pin Mem0 2.2.1,
qdrant-client 1.20.0 and Ollama's Python client 0.6.3. The Core dependency lock is
unchanged: Mem0 requires protobuf below 7 while Core pins protobuf 7.36.2.
Combining those environments is unsupported.

The adapter explicitly configures both providers, a private persistent Qdrant
path, collection ownership and a model/dimension fingerprint. It sets
`MEM0_TELEMETRY=False` before importing Mem0. Importing with an already-active
telemetry singleton is rejected. The stock Ollama embedder can automatically
pull missing models; the reviewed provider implementation instead verifies
explicit GGUF digests and fails closed. It never pulls or downloads models.
Mem0's process-local Ollama factory entries select those reviewed providers;
installed third-party source is not patched.

Inference permits only literal `127.0.0.1:11434`, disables environment proxies
and redirects, bounds input/output and execution time, and denies model tool
calls. A process audit hook additionally rejects external DNS/connections,
listeners and subprocess creation. This is defense in depth, not a claim of an
operating-system sandbox against malicious native dependency code. The adapter
receives no credentials and does not open the authoritative database. Its additional
file audit guard limits Python-level reads to reviewed runtime/code/system paths
and its projection directory, and writes to the projection directory. Core state
and credential reads, code writes and subprocesses are denied. Native compromise
remains outside the guarantees of Python audit hooks.

BGE-M3 on CPU is selected from the real-device pilot. These small-sample
results are diagnostic evidence, not the complete acceptance benchmark:

| Embedding | Dimensions | Top-1 recall | Top-3 recall | CPU query p50 / p95 |
| --- | --- | --- | --- | --- |
| BGE-M3 | 1024 | 85% | 100% | 1.344 / 1.350 seconds |
| Nomic Embed v2 MoE | 768 | 75% | 95% | 1.890 / 1.904 seconds |

Both tested 20 English/Arabic questions over 12 synthetic facts. Both passed
actual Mem0 insert/update/search/delete, persistent reopen, exclusive ownership
and network-denial scenarios. Raw rankings and tested digests are recorded in
[evidence](evidence/cognitive-memory/). The conversational Qwen pin was unchanged.
BGE-M3 leaves the GPU available to the pinned conversational model.

A changed embedding fingerprint requires a fresh private index followed by
reconciliation from current approved records. Never reuse incompatible vectors.
Before a model upgrade, stop the worker, preserve a verified private backup,
archive the old derived index/manifest/history under the repository preflight
rules, keep the vault and authoritative SQLite, configure approved new pins,
verify actual dimensions, and request a ledger rebuild. Retired index archives
have independent retention and must not be silently reactivated.

[Mem0](https://github.com/mem0ai/mem0) uses Apache-2.0. Its transitive cloud
clients are installed by the upstream distribution but are never configured as
providers. Network denials must be exercised in acceptance tests.

[Basic Memory](https://github.com/basicmachines-co/basic-memory) uses AGPL-3.0.
Its current distribution introduces an extensive web/MCP/database dependency
stack. No Basic Memory code is copied or linked into OKAL. The owner directive
expressly permits a clean Obsidian-compatible vault adapter when the direct
integration cannot meet licensing/privacy/reliability boundaries. That clean
adapter is the selected direction; Basic Memory's own server, graph, MCP and
cloud synchronization remain unsupported. The Markdown vault must stay optional.

## Lifecycle and migration

The additive migration upgrades `chat_schema` from 1 to 2 and adds
`cognitive_schema=1`. Old Core refuses the newer chat schema. Migration does
not recover previously purged history or import external ChatGPT conversations.
Backfill uses existing committed turns and persistent, idempotent jobs.

The requested default is now `retention_days=0` and memory `expires_at=0`, meaning
keep until explicitly deleted. Optional 1–365 day policies remain supported.
On first migration, the former 90-day chat policy becomes keep-until-deleted.
Stage 1 stored no setting provenance, so an explicit owner choice of exactly 90
days cannot be distinguished from its old default. Other existing finite chat
policies and existing finite memory expiry are preserved. The owner can select
90 days again after migration.

Corrections preserve source conversations and superseded snapshots, advance the
revision, fence dependent in-flight answers and queue replacement projections.
Forgetting removes exact quoted source spans, clears transitively dependent archive/history answers
and checkpoints, erases revision contents and FTS entries, fences ingestion, and
queues projection deletion. Unrelated owner sentences survive. Tombstones carry
IDs, revisions and timestamps without the forgotten text. Cached/stale vectors
cannot pass active-ledger revision validation.

A hashed subject cutoff prevents older unrelated-chat backfill jobs from
recreating a forgotten canonical subject. A genuinely new owner statement after
forgetting is new evidence. Duplicate reaffirmations retain independent source
references, so deleting one chat does not erase a fact independently restated in
another. Deleting source history purges its old revision snapshots and fences
answers that used archive excerpts.

Project identity is captured per source turn. Switching the active chat project
cannot relabel earlier source turns. Unique full owner project references may
establish an association; shared keywords never merge projects. Conflicting
references require one clarification, and unresolved messages wait for scope.
Automatic association binds the current turn and future turns, never earlier
unrelated history. Explicit owner association can bind previously unassigned
history. Distinctive decision lookup can retrieve one project without writing
an association; multiple matching projects require clarification.

Private backups and independent filesystem snapshots have separate retention;
forgetting live memory cannot erase previously exported offline copies.

## Development verification

The initial ledger milestone passed 496 Python tests. Later scope and privacy
milestones increased that coverage; final current-head counts remain a release
gate. Dedicated adapter CI uses actual Mem0 and persistent Qdrant with clearly
labelled deterministic vector fixtures. It does not claim model-quality results.
On-device tools use the real pinned Ollama models.

The first 12-case local extraction pilot had precision 60%, recall 37.5% and one
provider error. Constrained exact-sentence extraction then reached 100% on those
12 cases. The larger 10-conversation/50-turn diagnostic pilot exposed additional
classification and scope problems: preference recall 75%, project recall 100%
(two queries), per-chat recall 60%, extraction precision/recall 52.94%. These
failed results are preserved; none meets or replaces the full release gates.

The interruption scenario exposed an empty initial manifest after a killed
embedding probe. Creation is now atomic and recoverable only for a demonstrably
empty initial index; a corrupt manifest on a populated index fails closed.
The adapter lifecycle suite verifies both cases.

The [corpus](../apps/core/evals/cognitive-corpus.json) contains 200 fictional
conversations and 1,000 owner turns, with scripted synthetic assistant dialogue.
Those scripted replies are archive fixtures, never scored as generated answers.
The [evaluation harness](../apps/core/tools/evaluate_cognitive_memory.py) runs
real local extraction, projections, retrieval and held-out model answers,
retains actual output journals, and reports failed cases without substituting
expected facts. Full-corpus numerical gates, actual UI acceptance, fresh security
review, migration/rollback rehearsal and current-head GitHub CI are still pending.

The optional clean vault curates durable owner/project facts and lessons rather
than every conversational task. Stable IDs, revisions and base hashes govern
owner-confirmed imports; stale/deleted notes cannot overwrite SQLite. Statements
are rendered inside literal dynamically sized text fences, preventing automatic
remote-image/HTML fetching from extracted Markdown. Note edits remain local and
never authorize computer tools. Project overview notes provide controlled links
to current knowledge and editable project descriptions. Separate revision and
generation checks prevent lost project-note updates; owner-confirmed description
imports use the same project CAS as the UI. Inert unquoted identifier properties
from Obsidian are supported without evaluating general YAML.

## Rollout boundary

Merging is not deployment. Before Production rollout, stop writers for a verified
private SQLite backup, rehearse the migration on a copy, check integrity and
conversation counts, verify local provider pins, install the separate locked
adapter environment, and run resumable backfill with visible health. Do not
replace the live database with a synthetic evaluation database. Downgrade requires
the pre-migration backup and the corresponding old code; do not run old code
against schema 2. A detailed measured rollout/runbook is required before release.

The frozen 50-turn pilot at `72b3192` recovered interruption, reached 100% per-chat
recall and 97.06% extraction recall, but omitted the explicitly stated name. Its
original strict scores were preference 65%, project 50% (two questions). Two
correct paraphrases also exposed scorer vocabulary gaps; the original report is
preserved. Explicit first-person name sentences now supplement model proposals
through the same exact-source gate. The scorer recognizes equivalent concurrent
writing and direct-response phrases; numerical acceptance thresholds are unchanged.
