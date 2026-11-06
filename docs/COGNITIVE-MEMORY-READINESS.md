# Cognitive Memory V2 Production readiness

Task [#126](https://github.com/0PeterAdel/okal/issues/126). This work prepares
an owner-authorized cutover; it does not migrate the live database or deploy
schema 2. Owner-specific reports, exact conversation counts, backup checksums,
configuration, raw responses and recovery exports remain in owner-private local
storage, outside Git. The final readiness verdict belongs in that private report.

Read the [rollout runbook](COGNITIVE-MEMORY-ROLLOUT.md),
[engineering review](COGNITIVE-MEMORY-REVIEW.md) and
[Stage 3 release](STAGE3-RELEASE.md) together with this document.

## Findings that must be included in the cutover revision

### Interpreter ownership in a hardened user service

The adapter worked in a shell but failed in an actual hardened user-systemd
namespace. Host-root executable ownership appeared as overflow UID 65534.
The old owner/root-only check rejected the legitimate Python executable before
starting the adapter. Do not allow that UID generally or weaken service hardening.

Configuration now accepts an otherwise unmapped executable only when its device
and inode match `/proc/self/exe`, the interpreter already running Core. Regular-
file and group/world-write checks remain mandatory. Foreign executables with a
different inode/device and writable files still fail closed. The real hardened
namespace test must exercise the separate adapter, not merely import its config.

Prepare both staged environments using the actual serving interpreter. A shell's
`python` can resolve to another installed version; that happened during readiness.
Core and Mem0 remain separate hash-locked environments because their protobuf
requirements conflict. Do not upgrade the serving environment in place.

### Model keys do not establish memory subject identity

A real canary showed a project goal replacing a database decision because the
model reused `architecture.database`. Another showed a review label replacing
an unrelated saved phrase, despite both being semantic memories.

Project/conversation goals use governed scope-specific keys. Automatic updates
cannot change an unrelated memory type. Literal single-value semantic preference
statements receive an independently derived subject anchor, indexed in the
authoritative metadata. Distinct fields remain distinct even if the model reuses
one key; a later value for the same supported field preserves its ID and revision
history. Existing owner-editor keys and IDs remain intact when anchors are added
to a previously created schema-2 database.

Other ambiguous key collisions defer with `candidate_subject_conflict`, bounded
retry and an owner-visible review count. They do not overwrite the old fact or
erase the source archive. The owner editor remains the explicit correction path.
This conservative behavior does not claim universal semantic equivalence across
all phrasing/languages. Existing bilingual behavioral preferences and governed
project decisions retain their source validation and priority.

Forgetting purges stored historical contents as well as source evidence and
adds subject-anchor tombstones. A changed model key cannot restore an older
value of the same supported field through delayed ingestion. Explicit current
conversation markers also constrain identity facts to that conversation.

## Private snapshot tool

The standard-library [snapshot tool](../apps/core/tools/readiness_snapshot.py)
never imports Core and never migrates or replaces its input database. Example:

```bash
umask 077
/ABSOLUTE/REVIEWED/PYTHON apps/core/tools/readiness_snapshot.py \
  --state /ABSOLUTE/PRIVATE/LIVE/STATE \
  --output /ABSOLUTE/PRIVATE/FRESH/BACKUP \
  --service okal-core.service \
  --production-repo /ABSOLUTE/PRODUCTION/CHECKOUT
```

It requires an owner-private source, regular private database, fresh destination
outside the source, and a matching active service. SQLite's read-only backup API
captures a consistent database snapshot, verified by integrity/FK checks and exact
row fingerprints/counts. Other state files must remain hash-stable throughout
capture. The archive preserves file contents, modes and link metadata; the
manifest records ownership and timestamps. Referenced external environment files
and nonstandard filesystem attributes require separate inspection/preservation.
Do not mistake a symlink to an external credential for a backup of its target.

The CLI also captures installed units/drop-ins, the process environment and a
tracked baseline source archive. **These files contain secrets.** Output stays
0700/0600 and must never be pasted into a PR, CI artifact or screenshot. Only
`verified-private.json` indicates completion; failed/raced directories are not
verified backups and must be retained for inspection under the archive policy.

For a later approved maintenance-window backup, `--quiesced` requires the service
already be inactive with PID zero. It never stops the service itself and rejects
an active service before creating a backup directory. Check that no other CLI or
operator process writes state. An online readiness snapshot never substitutes
for this fresh cutover backup.

## Real-data rehearsal boundaries

1. Verify the archive and every restored file/hash/permission before migration.
2. Use a separate private state root and independently staged Core environment.
   Never pass the live path to the new application's `Store` or CLI.
3. Capture exact original table/row fingerprints. After migration, permit only
   documented schema, default-retention and memory-metadata changes. Every
   original conversation ID, ordered message and saved response must survive.
4. Quarantine restored provider credentials from active paths; disable sync,
   send, Trash, notifications and daily scheduling on the copy. Preserve the
   originals in the verified backup and restored quarantine.
5. Run the actual application entrypoint in a separate hardened user service.
   Make live state inaccessible; grant writes only to the rehearsal state.
   Use extra local-network/subprocess denials and no action-tool grants.
6. Append authorized synthetic canaries only to new conversations. Do not edit
   owner conversations to manufacture fixtures. Verify old chat resume and
   archive search without appending questions to those chats.
7. Exercise learning, correction, unrelated subjects, per-chat state, three-chat
   project decisions, fourth-chat continuation, source provenance, semantic
   search, vault preview/import, forgetting, cached-response fences and reindex.
8. Interrupt a verified adapter process with a pidfd, observe the persistent
   retry, and require successful completion without duplicates. Restart the
   private application, remove only its copied adapter configuration temporarily,
   and verify Chat/ledger/FTS fallback and later processing recovery.
9. Read cached Gmail/Tasks/Calendar APIs; run real filesystem action/receipt
   acceptance against fresh synthetic resources. Do not send provider messages,
   mutate external calendars, reuse personal browser profiles or grant root.

The offline Obsidian launcher remains optional. A governed vault file edit must
pass exact-preview/revision import; stale and forgotten IDs must remain rejected.
Native application launch, file editing and model inference are separate pieces
of evidence and must not be described as though one proves the others.

## Measurement and acceptance

Record device RAM/VRAM headroom while the normal service and Ollama stay active.
Distinguish whole-device samples from process/cgroup peaks and from unsampled
maximums. A rehearsal-only memory cap does not imply the existing Production
service has that cap. Ollama allocations occur outside Core's cgroup.

Require bounded ingestion, visible delays/failures, no failed integrity/FK checks,
no duplicate current keys and no changed original owner-chat rows. Test actual
foreground Chat while a background ingestion job is running; do not infer
contention behavior from idle measurements. Adapter unavailability must degrade
to authoritative profile/FTS/archive context, without fabricated completion.

The original 200-chat/1,000-turn real-model evaluation remains documented in the
[implementation report](COGNITIVE-MEMORY.md). Replaying its recorded proposals
checks Core policy regressions; it is not another LLM extraction benchmark.
The new same-subject/goal cases require their own real-model acceptance.

## Exact cutover and rollback gates

The owner-private cutover plan must name the reviewed merged SHA, actual tested
Core/Mem0 executables, local model manifest/blob digests, private backup location,
proposed last-sorting interpreter drop-in and verification commands. Keep all
existing Stage 3 hardening, provider configuration and action grants.

Use a maintenance window with owner write traffic held until acceptance finishes.
Quiesce writers, create and verify a fresh backup, then rehearse any material data
changes since readiness. Install only reviewed proposed configuration, fast-
forward the clean Production checkout to the exact reviewed SHA, and restart
only Core. Compare original conversation/turn fingerprints, retention, local
provider settings, service mounts and health before starting resumable backfill.
Do not restore a synthetic/rehearsal database into Production.

Pre-handoff rollback is permitted only when the new writes are the explicitly
tracked synthetic acceptance canaries. First preserve the complete upgraded state
and export/checksum all post-migration conversations. Restore the verified baseline
backup, corresponding code and environment in a controlled location; never set
`chat_schema` back to 1 on an upgraded database. Old Core refuses schema 2, but
its base-store initialization can still touch the database header before refusal.
The refusal test must therefore use a disposable copy, never the live database.

If unaccounted owner writes occurred after cutover, **stop automatic rollback**.
Retain both states and reconcile those writes before ordinary owner use resumes.
Do not silently replace newer conversations or rotating provider state with an
older snapshot. This boundary is part of lossless recovery, not permission to
discard data merely because a backup exists. Backups and independent snapshots
have separate privacy/retention handling from live forgetting.

`READY_FOR_OWNER_CUTOVER` is valid only after all private rehearsal, recovery,
security, performance and current-head GitHub gates pass and the readiness fixes
are merged. It is not authorization or evidence of live deployment.
