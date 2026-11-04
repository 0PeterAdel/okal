# Intelligence Core — Stage 1

Task: [#112](https://github.com/0PeterAdel/okal/issues/112). Owner directive,
2026-11-05: persist conversations and explicit personal memory first; deliver
computer actions only after this stage's independent verification and merge.
This supersedes the older reset's deferral of bounded conversation memory.

## Discovery and implementation plan

Baseline `4aba4f3`: chat uses eight client-supplied turns, one nonblocking process
semaphore and the existing pinned GGUF adapter. No transcript or reusable memory
is persisted. SQLite uses private 0700/0600 state and transactional additive
module schemas. Existing browser-origin checks gate writes; bearer read tokens
must never grant conversation or memory access. Remote Access remains mandatory
when configured. Calendar drafts still require the existing explicit save.

Production is active in the original checkout on port 8766; private database
exists at the documented owner state path. Development uses a separate worktree,
synthetic private state and port 8876. No production reads of message content,
private config publication, service restart or deployment are part of discovery.
Hardware: RTX 4060 Laptop, 8188 MiB VRAM; 15 GiB RAM, approximately 6.6 GiB
available during discovery. Installed models: Qwen3.5 4B (Q4_K_M), its existing
OKAL variant and Qwen3 0.6B. No model download/change is planned.

Implementation sequence:

1. Add transactional conversations, ordered turns, request digests, expiring
   inference leases, replay and interruption handling; keep the existing schema.
2. Add explicit owner-statement memories, scopes, kinds, provenance, versioned
   correction, expiry, retention, bounded lexical retrieval and deletion.
3. Build bounded server context from recent turns, compact older owner excerpts,
   relevant memories and existing cached daily context; reuse pinned inference.
4. Integrate history/resume/delete/retry and inspect/edit/forget controls into
   the existing fullscreen chat, including mobile layouts.
5. Verify migration, persistence, idempotency, concurrency, authorization,
   secret filtering, forget propagation, offline/invalid model responses and
   Arabic/English behavior using synthetic fixtures and the actual local model.
6. Review the complete diff and security boundaries, record measured evidence,
   rollback and limitations; pass governance and CI before a dedicated PR merge.

Acceptance is the Stage 1 checklist in the owner's directive plus #112. A model
response is never evidence of a performed action. No tools, external provider
writes or cloud inference are added by this stage.

## Implemented contract

All new endpoints are JSON POSTs under `/api/v1/chat/`. Even listing private
history requires the same-origin owner browser boundary. An `inbox:read` bearer
cannot use any endpoint. Protected mode additionally requires the existing
HttpOnly browser session; configured remote Access checks run before dispatch.
The legacy `/api/v1/chat` contract remains compatible and ephemeral; the UI now
uses the durable contract. Neither endpoint can execute tools.

| Path suffix | Input | Result |
| --- | --- | --- |
| `conversations` | optional `before` conversation ID | 50 titles, next cursor |
| `create` | optional title, at most 100 characters | stable conversation ID |
| `get` | conversation ID, optional `before` turn sequence | 40 ordered turns, next cursor |
| `delete` | conversation ID | cascade conversation and sourced memory deletion |
| `turn` | conversation ID, 32-hex request ID, message, optional retry | durable response or honest conflict |
| `memories` | optional conversation ID | owner and matching conversation memories |
| `memory-save` | key, content, kind, scope, revision, expiry | validated owner statement |
| `memory-delete` | memory ID | forget source and dependent context |
| `settings` | optional retention days | current retention policy |

Inputs reject unknown fields and wrong JSON types. Bodies are streamed with a
6000-byte cap; validation responses never echo rejected input. SQL parameters
are bound. All writes use short immediate transactions; no transaction spans
model I/O. The module schema has its own version guard and uses additive tables;
existing core schema version 1, devices, mail, calendar and tasks are preserved.

One turn record owns the ordered user message and validated assistant response.
The unique conversation/request key and content digest prevent duplicate or
changed-payload submissions. Chat inference has a database lease across
conversations/processes, plus the existing process semaphore. A late response
cannot replace a retried, deleted or forgotten turn. A failed model call stores
a labelled fallback; replay returns that fallback until explicit retry. Retry
reuses the turn ID and is permitted only for the latest failed turn. A crashed
worker's lease becomes retryable after 180 seconds. No automatic inference retry
or silent model replacement occurs. Existing model timeout and response limits
remain 90-second read / 120-second stream bound and 1 MiB respectively.

## Memory decisions and privacy

Working memory is recent server dialogue. Compact older context is a bounded,
extractive view of owner messages rebuilt from original turns, with truncation
visible. Semantic, episodic and task entries are explicit owner statements, with
key, scope, kind, source turn or editor, revision, timestamps and expiry.
Confidence 1 means confidence in the owner attribution, not external truth.
There is no automatic extraction from model speculation or incoming mail.
`remember key: value` and `افتكر الاسم: القيمة` save an exact owner quote;
conflicting values require an explicit editor correction using the current
revision. The owner can record decisions and pending task notes; task notes are
not executable workflows or verified action receipts.

Correction removes the old current value and invalidates dependent dialogue.
Forget removes the memory, its original source turn text, generated responses
that depended on it (including through later dialogue), and automatic titles.
This is deliberately conservative: unrelated text in a dependent turn can also
be redacted. Original messages not linked to that memory are unaffected.
In-flight affected responses are fenced. No independent summary or retrieval
index can resurrect removed content. `secure_delete` clears deleted SQLite
cells; retained backups, filesystem snapshots and already-open other browser
tabs are separate copies and require their own lifecycle. Reload other tabs
after forgetting. Normal browser lock/new conversation clears rendered text
without deleting server history. Only conversation identifiers enter browser
history; no transcript is written to localStorage/sessionStorage.

Known credential patterns are rejected at input/output and removed from cached
context; private credential/config files never enter prompt construction.
Pattern recognition is a defence, not comprehensive secret classification.
Do not enter passwords or tokens in chat. State uses existing owner-only
0700/0600 storage. Conversation retention defaults to 90 idle days, configurable
1–365; memory expiry defaults to 365 days, configurable 1–365. Expired state is
purged on subsequent chat access. Limits are 500 conversations, 2000 turns per
conversation and 500 total saved memories. The UI confirms immediate retention
changes, conversation deletion and forgetting.

## Context and model measurements

Retrieval ranks explicit memories by lexical overlap and recency, filters scope
and expiry, and selects at most five. Source IDs/revisions in the response refer
to memory actually supplied to the model; history dependencies are also tracked
internally for deletion. Four recent exchanges and eight older owner excerpts
are candidates. Prompt construction drops low-priority evidence to a conservative
approximately 6000-byte input ceiling including system and schema, leaving room
in the existing 8192-token model context and 1200-token generation budget.
Cached data remains explicitly incomplete; no absence claim establishes a free
calendar or empty mailbox. Old calendar requests cannot authorize new drafts.

At 500 synthetic memories, 20 retrievals measured median 2.49 ms, maximum
2.72 ms on this machine. SQLite FTS5 is available, but no index or vector store
was added because the bounded lexical scan is inexpensive. Retrieval does not
provide semantic similarity, cross-language translation, stemming or exhaustive
recall across all historical messages. Save important facts explicitly.

The existing `qwen3.5:4b` Q4_K_M model and reviewed digest remain unchanged.
`apps/core/tools/intelligence_acceptance.py` is an opt-in reproducible benchmark
using disposable state and synthetic content. It passed 9/9 cases: English save,
recall and follow-up; Arabic save and recall; corrected value; forgotten value;
genuine pinned-digest verification failure; and recovery with the same turn ID.
The final measured inference cases took 3.74–4.36 seconds. Deterministic saves
took at most 0.01 seconds. An earlier run exposed unwanted Arabic answers to
English questions; simplifying the system prompt and putting required language
first corrected the measured cases. This small benchmark is not a general
reasoning or multilingual quality certification. No models were downloaded.

Chat serializes its own inference, not all historical mail/planner workloads
across separately running processes or different state directories. Ollama
resource admission for those existing callers remains an operational limit.

## Verification and fresh AI-assisted review

2026-11-05, isolated task worktree and private synthetic database:

- Python 3.14: 451 core tests passed, including 19 new durable-state/security
  tests. Existing dependency deprecation and unclosed-connection ResourceWarnings
  were observed in the inherited suite; they did not fail the run.
- Node: 77 tests passed, including updated durable chat and existing navigation,
  calendar, Gmail, Tasks, Sidebar, glass theme and Markdown rendering checks.
- Existing process smoke: summaries/token survived restart, graceful shutdown
  passed. Approximately 0.262 s startup and 56.88 MiB peak RSS in that smoke.
  That tool's static environment label is generic; this run used the owner host
  with disposable fixtures and is not production or boot acceptance.
- Actual preview on port 8876: explicit memory save, browser reload/resume,
  process SIGTERM/restart and reload, editor revision 2, forgetting source
  transcript/title, desktop 1365×1000 and mobile 390×844, no horizontal overflow,
  and zero browser local/session storage entries verified through browser tools.
  Management opens as a scrollable view so it cannot push the composer offscreen.
- Browser found a pre-existing missing optional FullCalendar vendor script in
  both checkout layouts. Calendar's fallback path remains in the inherited tests;
  no production vendor install or dependency change was attempted.
- Real-model benchmark: 9/9; retrieval measurement above; governance passed.

Fresh review covered the full diff, auth path allowlist, strict payloads, SQL
transactions, replay/lease fencing, memory provenance, retention, prompt budgets,
source deletion and UI lifecycle. Findings fixed: forgotten title leak, inherited
context resurrection, stale historical calendar authority, oversized prompts,
English response selection, older failed-turn retry UI, and management overflow.
This is AI-assisted verification; no independent human approval is claimed.
Current-head CI and merge evidence belong in the PR before merge.

## Rollback and deployment

No production deployment or service restart is included. Before later deployment,
use the existing SQLite backup API to an owner-private destination, record the
reviewed commit and service configuration, and follow the current core runbook.
Deploy only through the separate authorized production procedure.

The schema is additive. Rolling back code to the preceding main continues to
read the original core tables and ignores the chat tables; durable chat becomes
unavailable in that UI but its data remains recoverable. Do not drop tables or
restore an old backup over new mail/calendar/task writes. For full restoration,
stop only the authorized service, preserve the current database separately and
use the reviewed backup/restore procedure. Deleting a conversation or forgetting
memory is intentional data removal; rollback does not undo it without a retained
private backup.

Stage 2 must remain a separate issue/branch/PR after Stage 1's verification and
merge gate. No desktop control, document ingestion, browser automation, general
shell, external send or autonomous action grant is implemented here.
