# Gmail backend trial

Task: [#40](https://github.com/0PeterAdel/okal/issues/40). This branch depends on
the unmerged foundation PR #39. Do not merge ahead of foundation acceptance.
The owner requested backend implementation now; #39 is frozen for acceptance,
not a second active feature. No UI/voice changes or automatic provider onboarding.

## Delivered scope

| Capability | Boundary |
|---|---|
| OAuth | Official Google libraries; account checked; read-only by default |
| Search/read | Bounded live Gmail queries; all pages or explicit budget failure |
| Digest | Archived incoming included; explicit UTC interval; local Ollama |
| Classification | Action/information/low-priority suggestions, not verified facts |
| Sources | Native IDs, metadata, body hashes and account-specific links |
| Follow-up | On-demand native thread check: last received or last sent |
| Compose/reply | Local immutable drafts; AI reply text never chooses recipient |
| Send | Separate OAuth grant, interactive exact-content approval, one recipient |
| Reconciliation | Verify sent content/ID; uncertain attempts cannot be resent |
| Scheduling | Opt-in daily digest, one core-owned worker, coalesced read catch-up |
| Storage | Same core database; atomic inbox/provenance/checkpoint commit |
| Retention | Explicit local prune of old digest data; send ledger retained |

This is a bounded personal Gmail module, not every Gmail feature. No attachments,
CC/BCC, reply-all, automatic replies, bulk sending, inbox deletion/archiving,
mark-as-read, remote approval, Outlook/IMAP, push notification or full mailbox
mirror. Follow-up is an observation on request, not a continuously running reply
tracker and not proof that someone owes a reply. Daily digest covers incoming
messages, including replies available during that interval.

All automated verification uses synthetic mail and mocked providers/models.
Real OAuth, account link navigation, actual delivery, Arabic summary quality and
owner hardware performance remain owner acceptance gates. No account was accessed.

## Safe trial installation

Do not switch a running service's source files. Preserve all old untracked files,
worktrees, virtualenvs and voice data. No reset/clean commands are required.

Before changing branches, stop only the core and create a new private backup:

```bash
cd /home/okal/Projects/okal
git status --short --branch
systemctl --user stop okal-core.service
okal_mail_backup="$(mktemp -d /home/okal/Projects/okal-mail-backup-XXXXXXXX)"
bash scripts/run-okal-core.sh backup "$okal_mail_backup/core.sqlite3"
echo "BACKUP: $okal_mail_backup/core.sqlite3"
git fetch origin feat/core-mail-backend
git switch --track origin/feat/core-mail-backend
.venv-okal-core/bin/python -m pip install --require-hashes -r apps/core/requirements-mail.lock
bash scripts/run-okal-core.sh mail status
systemctl --user start okal-core.service
```

If any step fails, stop and inspect; do not continue blindly or overwrite an
existing branch. If the branch already exists, inspect it and use ordinary
`git switch feat/core-mail-backend`, not force/reset. The optional mail lock includes
the core/test client dependencies. The root Python package is legacy voice and
is NOT installed by these commands. Python 3.12 and 3.14 have separate test runs.

Installing the code does not connect an account, download a model, grant sending
or enable a schedule. Until configured, the service remains the foundation inbox.

## Local model and private configuration

Select an already installed model that actually works on the laptop. Do not
infer Arabic quality from parameter count. Record its exact name and digest:

```bash
ollama --version
ollama list
curl --fail --silent http://127.0.0.1:11434/api/tags
```

Ollama itself must have cloud features disabled (`OLLAMA_NO_CLOUD=1` on the
actual Ollama server, or its documented `disable_ollama_cloud` server setting).
See [Ollama's official configuration](https://docs.ollama.com/faq). Setting an
environment variable only on Okal's client does NOT configure the Ollama server.
Do not expose Ollama to the LAN or change an unrelated service blindly.

Make a new owner-only directory outside the checkout, then copy
`apps/core/mail-config.example.json` there as `mail-config.json` with mode 0600.
Edit it locally: account, installed model name, exact 64-hex model digest. Set
`local_only_confirmed` to true only after configuring the actual server.
Keep `send_enabled: false` and `daily_at: null` on first setup.

```bash
bash scripts/run-okal-core.sh mail configure --file /absolute/private/mail-config.json
```

Configuration is copied into the private core state directory under `mail/`.
Another account cannot silently replace this account; use separately scoped
state and review migration. No old pilot credentials are automatically imported.

## Explicit Gmail onboarding

Use the [official Desktop OAuth setup](https://developers.google.com/workspace/gmail/api/quickstart/python):
enable Gmail API in your Google project, configure consent/testing users, create
a Desktop client and download the JSON into an owner-only file outside Git.
Use the correct owner account in Google's consent dialog. No Gmail password or
app password is used. Google may require app verification depending on its
audience, scopes and deployment; do not bypass consent or verification rules.

```bash
bash scripts/run-okal-core.sh mail authorize --client /absolute/private/google-desktop.json
bash scripts/run-okal-core.sh mail doctor
```

This opens your local browser for consent, verifies account identity and stores
credentials privately. Do not paste OAuth URLs, client JSON, tokens, mail bodies,
drafts or database backups into chat or PRs. External apps in Google Testing mode
normally receive seven-day refresh tokens for Gmail scopes. `authorization_required`
needs local reauthorization; the background worker never opens a browser itself.

Only Google receives OAuth/Gmail requests; email text goes to the configured local
Ollama server. Gmail needs Internet; this is local inference, not offline Gmail.

## Manual read workflows

```bash
# Default: last successful contiguous interval through now; first run: 24 hours.
bash scripts/run-okal-core.sh mail digest

# Explicit half-open UTC interval [start,end), maximum 31 days; end cannot be future.
bash scripts/run-okal-core.sh mail digest \
  --start 2026-10-29T00:00:00Z --end 2026-10-30T00:00:00Z

bash scripts/run-okal-core.sh mail search 'newer_than:7d' --limit 20
bash scripts/run-okal-core.sh mail read MESSAGE_ID
bash scripts/run-okal-core.sh mail sources JOB_ID
bash scripts/run-okal-core.sh mail followup MESSAGE_ID
bash scripts/run-okal-core.sh mail status
```

Uppercase IDs are placeholders: use exact IDs from command results. CLI prints
JSON with escaped Unicode/control characters, preventing mail text from executing
terminal control sequences. Existing inbox displays Arabic digest text normally.

Default digest coverage includes archived received mail, excluding SENT, DRAFT,
SPAM and TRASH. Self-sent messages carrying SENT are excluded. Listing is not a
historical snapshot: messages deleted during fetch fail the run; previously
deleted mail cannot be recovered; later imports/backdated arrivals need a manual
backfill. A manual interval that skips a gap does not advance the contiguous
checkpoint over it. Older backfill never moves progress backwards.

All pages are consumed up to the explicit message/page budgets. Over-budget
intervals fail visibly; narrow the interval. A truncated body or body requiring
an attachment fetch also fails the digest rather than claiming complete reading.
Attachments are counted but never fetched/interpreted. Metadata/body hashes and
summaries persist; raw inbound bodies do not. Hashes are provenance, not proof of
summary factual correctness. Review dates, amounts and proposed actions yourself.

Ollama is checked before each generation: installed GGUF, matching digest, no
remote-model metadata. No tools, model pulls, redirects, proxy-env routing or
cloud fallback. Requests are serial, bounded and unload the model after each
generation; this favors memory release over warm latency. Measure on the laptop
before changing residency/context defaults. Tags must not be modified while a
run is active. Same-user compromise of Ollama or local config is out of scope.

## Local drafts and reviewed sending

Create a private JSON based on `apps/core/mail-draft.example.json`, mode 0600.
It contains exactly the recipient address, subject and body you want to review.

```bash
bash scripts/run-okal-core.sh mail draft --file /absolute/private/draft.json
bash scripts/run-okal-core.sh mail reply MESSAGE_ID --instruction 'اكتب رد قصير بدون التزام بموعد أو سعر'
bash scripts/run-okal-core.sh mail drafts
bash scripts/run-okal-core.sh mail preview DRAFT_ID
```

These drafts exist only in Okal, not in Google's Drafts folder. A reply uses the
native Reply-To/From header; review the actual address because headers can be
spoofed. No inferred contact matching or reply-all. To edit, make a new draft;
old approval never applies to a modified draft. In-reply-to/thread metadata is
bound into the draft; subject is preserved for thread matching.

Sending is optional and a separate permission grant:

```bash
bash scripts/run-okal-core.sh mail authorize \
  --client /absolute/private/google-desktop.json --enable-send
bash scripts/run-okal-core.sh mail send DRAFT_ID
```

`send` requires an interactive terminal and displays the exact From/To/subject/
body and full approval digest. Type `SEND`, a space, then that digest only after
reviewing everything. Approval expires after ten minutes. There is no `--yes`,
scheduled send or approval via model/HTTP read token. The durable uncertain-send
record is committed before making the request. A lost response never retries.

```bash
bash scripts/run-okal-core.sh mail reconcile DRAFT_ID
bash scripts/run-okal-core.sh mail pause-sending
```

Reconciliation checks the native Message-ID, SENT label, sender, sole recipient,
subject and body. `sent_verified` is a native Sent-folder receipt, not proof of
recipient delivery/read. Search absence or mismatch stays uncertain: inspect
Gmail manually, do not create a replacement just to force another send. Pausing
blocks local sends but does not revoke Google's grant; reauthorize without
`--enable-send` to narrow the locally stored credentials, and use Google's account
permissions screen to revoke access if desired. Read workflows still work while
local sending is paused, even if the existing token also has the send scope.

## Optional daily digest, pause and recovery

```bash
bash scripts/run-okal-core.sh mail schedule 09:00
systemctl --user restart okal-core.service
bash scripts/run-okal-core.sh mail status
# Stop scheduled reads without stopping the inbox:
bash scripts/run-okal-core.sh mail schedule off
```

Time uses the configured IANA zone (Africa/Cairo default), calculated with
APScheduler's CronTrigger. Enabling/changing a schedule starts at the next slot,
not immediately. The core's worker polls every 30 seconds; no second service or
legacy Gmail timer is installed. It serializes with manual mail commands through
an OS lock. Read catch-up coalesces into one interval from the successful
checkpoint; more than 31 missed days requires explicit backfill. Only reads
retry, with bounded backoff/cooldown. No unattended sending occurs.

Graceful service stop asks the worker to exit; in-flight read work may be
interrupted at process exit. SQLite completion is transactional and unfinished
read jobs can be reclaimed after restart. Watch `mail status` for failed runs,
next-due time and retry state. A paused/disconnected model must not block the
inbox HTTP server. Provider failures before a job starts appear in scheduler
status, not as a successful empty digest.

## Storage, backup, deletion and rollback

Mail tables are an additive extension of core schema 1 with their own
`mail_meta.version=1`. Future mail versions are rejected. Baseline core code can
read the inbox without touching mail tables. Backup before upgrading; stop
the service before changing code. Do not drop/overwrite existing tables.

`backup` includes mail jobs, provenance, local drafts, outgoing bytes and send
receipts in the same SQLite snapshot. It does NOT include the separate OAuth/
config JSON files. Keep credentials private, or reauthorize after recovery.
There is no promise of encrypted storage; file permissions do not protect against
the logged-in user, root, malware or an unlocked disk.

**Never send from an old restored database.** It can predate a successful send
and make the old draft look unsent, or revive revoked device tokens. Restore for
read-only validation in a new directory with no mail config/token; revoke old
read tokens before serving. Reconcile send history against Gmail and re-onboard
explicitly before enabling any writes. Do not restore over the live database.

Raw inbound bodies are ephemeral. Digest/provenance retention is configured
(30 days default) but deletion is explicit, not automatic:

```bash
bash scripts/run-okal-core.sh mail prune --confirm-delete-old-digests
```

This removes old mail summaries/provenance only. Idempotency tombstones, progress,
drafts and send receipts are retained to avoid replay; backup files may retain
deleted data. SQLite logical deletion is not secure physical erasure. Draft/
receipt removal or account migration requires a separately reviewed recovery
plan; no broad cleanup command is provided.

For code rollback, stop core, return to the previously reviewed branch, restore
its dependency lock, then start the inbox. Preserve the current database and
private mail directory; old core ignores the additive mail tables. Keep scheduled
mail off until you return to the tested mail code.

## Verification

### Inbox status evidence

Opening or refreshing the authenticated inbox reads local summaries and a local
capability snapshot only. It does not contact Gmail or run inference. The snapshot
separates configuration, latest recorded attempt, latest successful digest and
configured schedule/send gates; it exposes no account address, credential, draft
or mail body. Configuration is not proof of valid OAuth, an enabled schedule is
not proof of worker health, and past success is not current provider/model health.
Zero-message runs do not prove inference. Demo fixtures never count as mail jobs.
Snapshot reads do not initialize or migrate mail tables; unsupported history
schemas and invalid configurations are displayed as unknown/error, not success.

Status and summaries are cleared on page lock/navigation, with no browser token
storage. Refresh errors clear success labels; late responses cannot unlock a
locked page. Retained summaries may still be visible after an ordinary refresh
failure, explicitly marked stale. The UI never grants sending permissions.

### Thinking-budget regression

Mail summary and reply requests explicitly set `think: false`, with the existing
8K context and 1200-token output limit. The owner's synthetic Qwen3.5 4B probe on
2026-10-31 exhausted 1200 tokens with an empty answer under the model default;
the same probe with thinking disabled stopped normally after 67 tokens and
passed schema validation. This is owner-reported synthetic compatibility evidence,
not acceptance of real-mail factual quality. No private mail or reasoning text
is included in the regression fixtures.

Truncated responses remain failures even if their content parses as JSON. There
is no automatic larger-budget retry or relaxed schema validation. See
[Ollama thinking controls](https://docs.ollama.com/capabilities/thinking).

After updating, retry the exact failed interval with explicit `--start`/`--end`.
Do not rely on a default incremental digest to recover an older failed backfill.

### Automated checks

```bash
PYTHONPATH=apps/core/src .venv-okal-core/bin/python -m unittest discover -s apps/core/tests -v
PYTHONPATH=apps/core/src .venv-okal-core/bin/python apps/core/tools/verify_runtime.py
```

See [upstream and dependency review](MAIL-UPSTREAM-REVIEW.md). Local automated
tests are not owner OAuth/model/delivery acceptance and not a human PR review.
No production-readiness or complete Gmail feature-parity claim is made.
