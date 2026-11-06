# Cognitive Memory V2 rollout and recovery

Task: [#124](https://github.com/0PeterAdel/okal/issues/124).
This is an operator runbook, **not evidence of a Production deployment**.
Development, evaluation and desktop acceptance use synthetic private state.
The existing service and owner database remain unchanged until a separate rollout.

## Release gates

Use only the exact merged revision after current-head GitHub checks, complete
AI-assisted verification, resolved findings and the owner-authorized merge gate.
Inspect the [implementation/evidence](COGNITIVE-MEMORY.md) first. A successful
merge does not mean any owner history has been migrated or indexed.

The [Production-readiness findings](COGNITIVE-MEMORY-READINESS.md) in task #126
must be included in the cutover revision. The initial Memory V2 merge alone
does not include the hardened-systemd interpreter fix or subject-consolidation
guards found by real-data rehearsal. Use the actual serving Python version for
both staged environments, not an unverified shell `python` alias.

The baseline rollback code is `08d51e8b81468fd82684b28ec5ab8434f22a31cc`.
Never run that old Core against the upgraded schema. Never substitute a benchmark
database, synthetic account config, development vault or vector index for owner data.

## Prepare without changing live state

1. Verify the live service, checkout SHA, clean status, free disk/RAM and existing
   Ollama configuration. Preserve the approved conversational model and digest.
2. Review the [Stage 3 rollout](STAGE3-ROLLOUT.md), service hardening and private
   backup handling. Do not remove branches, private state or previous backups.
3. Install the new optional adapter into a separate Python 3.14 environment from
   [requirements-memory.lock](../apps/core/requirements-memory.lock), using
   `pip install --require-hashes`. Keep the existing Core/actions environment;
   its protobuf 7 pin is incompatible with Mem0's protobuf 6 requirement.
4. Confirm the installed local models match the tested GGUF pins. The adapter
   does not download missing models or silently choose another provider.
5. Set aside enough private disk for a complete pre-migration state backup and
   a rollback archive, not just the vector index. Do not publish these copies.

## Quiesced backup and rehearsal

During a separately scheduled rollout, stop service writers before backing up.
Use SQLite's backup API for the database and preserve the rest of private state,
permissions and relevant configuration. Record a private manifest of SHA-256,
`PRAGMA integrity_check`, `PRAGMA foreign_key_check`, conversation/turn counts,
settings and code revision. Verify the backup is readable before proceeding.

Rehearse on a private owner-data copy under the same protection as Production.
Inspect the migration, source/turn counts, retention and source provenance.
Keep the original backup immutable. Development's synthetic rehearsal already
demonstrated old-schema creation, additive migration, refusal by old code and
successful old-code restart after backup restoration; it does not replace this
owner-data rehearsal.

Migration changes `chat_schema=1` to `2`, adding the cognitive ledger, source
graph, FTS index, project state, jobs, versions, tombstones and outboxes.
It preserves stored conversations. Legacy completed turns receive a conservative
privacy dependency chain, so later assistant answers may be invalidated when a
legacy fact is explicitly forgotten; unrelated owner messages remain. Credential-
related legacy memories are withheld from active recall and projections, with an
owner-visible quarantine indicator. Their private archive/ledger data remains for
owner review/deletion. Migration cannot recover already-purged data.

The old 90-day chat default and exact 365-day memory default become indefinite
retention. Stage 1 did not record whether those exact values were explicitly
chosen. Other finite policies remain unchanged; the owner can select 90/365
again. Review this specific compatibility tradeoff before the live cutover.

## Local provider configuration

Create an owner-only `cognitive.json` in the private Core state root. Use this
shape with the actual installed executable path; the following pins were tested:

```json
{
  "version": 1,
  "local_only_confirmed": true,
  "python": "/home/okal/Projects/Okal/.venv-memory/bin/python",
  "llm": {
    "name": "qwen3.5:4b",
    "digest": "d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04"
  },
  "embedding": {
    "name": "bge-m3:latest",
    "digest": "7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab"
  },
  "dimensions": 1024,
  "embedding_gpu": false
}
```

The file must be a regular owner-only 0600 file inside private 0700 state.
Do not put API keys, proxy URLs or cloud provider configuration in it. The
reviewed provider permits only literal loopback Ollama at port 11434, verifies
GGUF digests and dimensions, rejects redirects and does not inherit proxies.
The conversational mail/model config remains separate and unchanged.

Core imports no Mem0 package. A dedicated subprocess receives only bounded
JSON over private pipes, with a clean environment and private working directory.
Its writable/readable projection scope is `cognitive/adapter`; the vault and
Obsidian profile are siblings outside that scope. It has one exclusive
embedded-Qdrant owner. Never start a second worker against
the same index. Do not expose Qdrant's HTTP service or use a temporary `/tmp`
index for durable memory. Runtime Python audit hooks provide additional denials;
they are not a native-code-compromise sandbox.

## Cutover and resumable owner-history ingestion

After verified backup/rehearsal and a separate rollout decision, update only to
the reviewed merged code using the established deployment process. Keep service
hardening and filesystem permissions. Start the existing service and verify
health, original conversation counts, owner-browser authorization, Chat, Tasks,
Calendar and computer-action policy. Do not grant new computer permissions.

The worker automatically schedules bounded batches from committed existing
turns. Each source turn has one persistent job, a content digest, ordering,
scope snapshot, lease and bounded retry state. The Memory UI shows pending,
running, failed and completed work. Backfill is resumable and idempotent; do
not manually reinsert exported chat content or delete job rows to force replay.

Automatic learning uses only committed owner messages. Sensitive categories,
external/quoted instructions, model guesses and tool outputs cannot authorize
memory or actions. The complete archive remains independently searchable.
Approved exact-source facts enter SQLite first; indexes and curated Markdown
follow through retryable outboxes. A worker interruption must never be reported
as completed ingestion.

Sample owner canaries only after the migration passes: original chat resume,
new-chat preference recall, correction, project continuation, source view,
retention, forgetting and index/vault health. Keep provider accounts read-only
unless an independently authorized action is required. Record exactly which
canaries passed before calling the rollout successful.

## Optional Obsidian vault

Curated notes live under private state at `cognitive/vault`. General computer
actions cannot read the Core state or vault, even under a broader home grant.
Chat does not require Obsidian or Basic Memory. No AGPL Basic Memory code/server
is installed; its graph/MCP/cloud features are unsupported.

Run the optional owner-operated offline desktop launcher from the reviewed Core
environment with `--state-dir` pointing to the actual state root:

```bash
PYTHONPATH=apps/core/src .venv-okal-core/bin/python apps/core/tools/open_memory_vault.py --state-dir /home/okal/.local/state/okal-core
```

Adjust only the environment executable to the installed Core environment. The
launcher uses a separate profile, disables updates, rejects unreviewed plugin
settings and isolates networking, home files and D-Bus using bubblewrap. It
requires the reviewed Arch Obsidian/Electron 43 packages and Wayland. It never
mounts the authoritative database. Normal compositor interaction remains possible.
No remote debugger is enabled by the launcher.

Edit only the owner-statement text block, preserving ID, revision and base hash.
Then use OKAL's Memory UI to preview and explicitly import the displayed edit.
Project description notes have a separate preview/import control. Concurrent
or stale notes return conflicts; they do not silently overwrite SQLite.
Deleted memory IDs cannot be reimported. Do not enable Sync, File Recovery or
community plugins in this governed vault. Another unmanaged Obsidian profile
has independent privacy, network, plugin and backup behavior.

## Failure handling and index replacement

- Chat must continue with authoritative profile, FTS and archive retrieval when
  Mem0 is busy or unavailable. Semantic lookup has a bounded opportunistic wait.
- A failed index or vault update remains visible. Inspect safe error codes and
  conflicts before selecting retry; repeated retries are bounded.
- If an owner note was edited, import or preserve/discard that exact edit
  intentionally. Do not overwrite it to hide a failed outbox entry.
- Rebuild semantic indexes only from current approved SQLite records. Forgetting
  immediately removes active retrieval authority, before physical projection
  reconciliation. A stale vector or note cannot bypass the ledger.
- For changed embedding model/digest/dimensions, stop the worker, preserve the
  old derived index under archive/preflight rules, and initialize a fresh private
  index with the reviewed new fingerprint. Reindex from SQLite. Do not reuse
  incompatible vectors or delete the authoritative ledger/vault.

## Rollback

Stop writers and preserve the entire failed upgraded state as a private rollback
archive. Preserve any post-cutover conversations for explicit reconciliation;
do not overwrite or silently lose them. Restore the verified pre-migration state
backup and its corresponding baseline code/config/environment, then check
integrity, conversation counts, settings, health and normal Chat behavior.
Only then resume ordinary owner use. Never run old code against schema 2.

Offline backups, filesystem snapshots, unmanaged vault copies and the rollback
archive have their own retention. Forgetting live memory cannot erase those
independent copies. Follow the existing archive/local-preflight governance
before any later disposal.


Vault import requests must include the preview's `content_sha256` and revision.
An HTTP 409 after an Obsidian edit means preview again and review the new text;
do not retry with a manufactured hash. Moving a note after changing its memory
kind preserves independent file edits as a sync conflict rather than discarding
them. Explicit forgetting still removes all managed projections of that ID.
