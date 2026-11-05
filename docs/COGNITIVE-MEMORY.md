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
days cannot be distinguished from its old default. The former default 365-day memory lifetime also becomes indefinite, using
its exact stored duration from the last update; Stage 1 likewise did not record
whether 365 days was explicitly selected. Other finite chat/memory policies
remain intact. The owner can select 90-day chat or 365-day memory expiry again
after migration. Already-purged data cannot be recovered by this change.

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

The next 50-turn pilot at `19f67a0` met numerical recall thresholds: preference
90%, project 100% (two queries), per-chat 100%; extraction precision/recall 100%.
Both remaining wrong name answers mistransliterated a correctly retrieved name.
The prompt now requires exact source spelling for names and identifiers.
All seven real forgetting/cache/vault/rebuild checks passed. This pilot remains
smaller than the required release corpus. Its relevance-at-8 definition counts
unrelated always-present personalization against precision (31.51%), while
recall-at-8 was 100%; it is not equivalent to answer accuracy.

## Private Obsidian desktop

The optional [offline launcher](../apps/core/tools/open_memory_vault.py) requires
Arch Obsidian/Electron 43, Wayland and unprivileged bubblewrap. It mounts only
system runtime/fonts, the curated vault, a separate private profile and the
owner's Wayland socket. Networking, home data, the Core database, credentials
and D-Bus are absent. Chromium's inner sandbox is disabled inside the enclosing
OS namespace; normal Wayland compositor interaction remains possible. This is
not a VM for hostile GUI applications. No remote-debugging listener is enabled.

The dedicated profile disables updates. The curated vault permits only reviewed
built-in navigation/editor plugins, with no community plugins, Sync or File
Recovery. Existing unsupported plugin settings cause an explicit refusal rather
than silently enabling them. Opening the vault with another unmanaged Obsidian
profile has that profile's independent privacy and backup behavior.

Actual on-device Obsidian 1.14.5 / Electron 43.8.6 acceptance opened the synthetic
vault, edited Arabic with the app editor/keyboard, and confirmed that OKAL's
browser import preview showed the change while SQLite remained at revision 1.
Only browser confirmation produced revision 2. Both legacy notes and the new
literal-fence format rendered in the real app. Community plugins, Sync and File
Recovery were disabled; a few standard built-in panels remained enabled.

The [migration rehearsal](../apps/core/tools/verify_cognitive_migration.py)
preserved 100 synthetic bilingual archived turns, checked DB integrity and
foreign keys, preserved explicit legacy expiry, changed the old default retention
to keep-until-deleted, and verified idempotent backfill. Old Core rejected schema
2 and successfully reopened the restored unchanged schema-1 backup. No Production
state was copied or migrated.

Automatic extraction excludes common sensitive health/financial categories.
This conservative pattern gate is not a universal sensitive-data classifier.
The Memory editor requires a separate explicit checkbox and confirmation for
such facts; secrets/credentials remain rejected even with that confirmation.
Controlled Obsidian revision import also requires owner preview and confirmation.

Installed adapter dependency metadata was inventoried (35 distributions), with
no AGPL dependency in the runtime. The [review](evidence/cognitive-memory/dependency-review.json)
records declared licenses and a live OSV package-version query with no advisory
matches. Only public package names/versions were sent. This is not a proof of
absence of vulnerabilities or a substitute for license notices on distribution.

The first complete 200-conversation / 1,000-turn run at `c26075f` generated and
scored 240 real local-model answers. It **failed** the personal-preference gate
(75% against 90%), while project and per-chat recall were 100%. The extractor
omitted the explicit durable language sentence in a multi-fact message. The
failed report and all five failed answers are preserved in the evidence folder.
No completion or merge is authorized by those results.

Explicit identity and durable communication sentences now supplement Mem0's
semantic proposals through lossless source rules. They retain owner wording,
conditions and scope and pass the same sensitive-data, external-content,
question and permission gates. One-off reply overrides remain transient. This
is a hybrid extraction pipeline; reported precision/recall describes approved
pipeline outputs, not raw unfiltered model proposals.

The real governed file acceptance required the exact runtime approval digest
before writing a disposable synthetic file. A stored assertion that approvals
could be skipped did not authorize execution. After approval, the existing
computer engine verified the file postcondition, and a different conversation
in the same explicit project received the verified execution receipt. No live
policy, files or accounts were changed.

The follow-up migration rehearsal also verified that a later archived language
correction supersedes an older Stage 1 source under the same memory ID. Migrated
source ordering uses source turn sequence (or the manual edit's historical
checkpoint), not a fictitious new preference timestamp. New V2 editor revisions
remain newer than historical backfill. Common legacy language keys normalize to
the canonical key when that does not collide with an existing saved key.

Conditional English-for-technical-documentation preferences occupy a distinct
subject from the general reply language. Matching conditional preferences take
precedence within their scope; a higher-priority conversation instruction still
wins. Owner-edited combined language/brevity statements also affect reply style.

Actual Chromium acceptance used a separate local session after detecting
unreliable viewport emulation in the integrated browser. Verified 390×844 and
768×1024 viewports fit with no horizontal overflow and a visible composer.
The desktop and narrow-view screenshots were inspected. Saved real-model
cross-chat recall, memory correction/source versions, archive search/source
resume, forgetting, deleted-state browsing and indefinite-retention controls
passed, with zero page exceptions or external requests. The optional FullCalendar
404 is the existing Stage 3 fallback condition, not a memory regression.

See the [rollout and recovery runbook](COGNITIVE-MEMORY-ROLLOUT.md) for exact
provider configuration, isolated environments, owner-history ingestion, optional
Obsidian launch, index replacement and backup rollback. No Production rollout
has been performed.
