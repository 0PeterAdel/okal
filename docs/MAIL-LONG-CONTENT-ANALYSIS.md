# OKAL Gmail — long-content analysis and automatic recovery

## Root cause

The old Gmail body parser clipped native message text after 8,000 characters,
set `truncated=True`, and History Sync put any such mail into Manual Review
without calling Ollama. Every quarantined Gmail ID was also stored in the
deduplication set, so old "too long" messages never got another chance. In
some Gmail messages the **inline MIME text body** is delivered through a
separate `attachmentId`, even though it is not a file attachment.

## New local-only behavior

1. Text from a single Gmail message is decoded with a strict 4 MiB encoded
   MIME budget and normalized. Up to 96,000 *visible characters* are held in
   memory for analysis; raw bodies are NOT persisted in the SQLite evidence.
2. Messages up to 5,000 characters are analyzed in one bounded Ollama call.
   Longer messages are analyzed section by section using at most eight
   chunks of 2,800 characters, then a final synthesis call. The pinned local
   GGUF and its digest are verified; no cloud model, paid API or auto-pull.
   The model stays warm between chunks and is released after reduction.
3. Up to 22,400 characters can be inspected in full across chunks. Longer
   messages are sampled deterministically from across the visible message,
   including the ending, and the final summary visibly says
   **"ملخص جزئي — راجع النص الكامل"**. This is a limited, truthful summary,
   not a claim the entire message was read. Dates/amounts absent from
   inspected text must never be fabricated.
4. Gmail's separate **inline body text** attachmentId is fetched via its
   read-only API, within a strict bound. File attachments (including PDFs,
   image attachments and other files) are NOT fetched or sent to the model.
5. History Sync no longer quarantines mail simply for being truncated.
   Previously quarantined emails with the exact known long-body codes are
   rechecked **up to two per successful sync**, up to three failures total
   with a 24-hour cooldown. Once summarized, the historical quarantine is
   cleared atomically with the saved analysis. Already-seen IDs remain
   deduplicated; nothing is sent, deleted or modified on Gmail.

## Owner rollout

This feature is on the stacked Draft branch
`feat/mail-long-content-resilient-analysis` (PR #51), based on the local
planner branch. Back up Core SQLite, inspect Git working tree, fetch and
switch branch only if existing changes permit, and restart the local Core
service.

```bash
cd /home/okal/Projects/okal
git status --short --branch
backup_dir=$(mktemp -d "$HOME/okal-core-backup-XXXXXXXX")
bash scripts/run-okal-core.sh backup "$backup_dir/core.sqlite3"
git fetch origin feat/mail-long-content-resilient-analysis
systemctl --user stop okal-core.service
git switch --track origin/feat/mail-long-content-resilient-analysis
systemctl --user start okal-core.service
```

If the branch is already present locally, use `git switch` to it, and
fast-forward only when the worktree is clean. Do not reset local files.

Request a Gmail sync from terminal to trigger recovery:

```bash
bash scripts/run-okal-core.sh mail sync now
bash scripts/run-okal-core.sh mail status
```

Gmail history can take several sync cycles to recover older long messages;
check Smart Inbox and Manual Review. The automatic worker's normal sync
interval is around 5 minutes. Never reset the SQLite `mail_sync_seen`
table or the Gmail cursor as a workaround. No new OAuth grant is needed.

## Known limits and verification

- Overlarge or corrupt MIME (>4 MiB encoded text), unsupported attached
  body structures or permanent provider failures can still require manual
  review; the message is not silently ignored.
- A 4B model may not extract every important fact from a very long text, and
  source content and model summaries must be verified for high-stakes use.
- Long-mail map/reduce has a bounded number of model calls, but it can
  take longer than ordinary one-pass summarization on a laptop.
- Recovery respects the user's existing Gmail access and never invokes
  Gmail write APIs. It is not a background task initiated by this GitHub PR:
  the owner's laptop must be updated.
- Mocked CI confirms protocol behavior but does not prove the user-local
  Ollama model will summarize every real message correctly. Real Gmail
  acceptance remains pending.
