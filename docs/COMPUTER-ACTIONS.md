# Governed computer actions — Stage 2

Task [#117](https://github.com/0PeterAdel/okal/issues/117), built on Stage 1
`7553b464c2139bb0619c4365bdc2e27864bc535c`. This implements the owner's November
2026 directive for personal computer operations. It supersedes the earlier reset
proposal's deferral of these bounded personal capabilities; it does not introduce
coding/research agents, voice, a second application or a second state authority.

## Audit and architecture

The recovered `feat/computer-actions` worktree was clean at Stage 1. Production
remained in the original checkout at `4aba4f3`, active under the same systemd
process throughout development. Its database and configuration were not copied,
replaced or migrated. All development used separate private SQLite state,
synthetic folders/accounts, a dedicated virtual environment and preview port 8876.

Available on-device: Chromium 156.0.8078.79, Hyprland 0.57.0, Bubblewrap,
pdftotext, gtk-launch, xdg-open and notify-send. Playwright was absent, as were
pypdf/python-docx/openpyxl. The implementation reuses native PDF extraction and
bounded standard-library OOXML/CSV/JSON parsing rather than adding three document
frameworks. Browser automation adds optional Playwright 1.64.1, hash-locked with
its dependencies in `apps/core/requirements-actions.lock`. Existing mail lock
versions constrain resolution, so core/provider versions are preserved.

The same Core owns permissions, plans, steps and receipts. The
`okal_core.computer` package separates contracts, directory-fd filesystem access,
document parsing, subprocess control, isolated browser execution, tool adapters,
durable orchestration, natural-language routing and owner-only API transport.
Adding a tool requires a typed schema, manifest, preview, handler and observed
postconditions. There is no dynamic plugin installation or model-provided code.

Lifecycle: understand owner request → validate typed plan → check grants → capture
exact resource preview → obtain approval when required → persist attempted step →
execute → observe postconditions → append receipt → advance. A plan has at most
ten steps. It can use a previous verified step's output file; its input is bound
to that step's actual hash/inode receipt, not an assumed path. Normal chat can see
recent authoritative action status; `continue`/`resume`/`كمل` opens the preceding
conversation action. Task state is shared with Stage 1's persistent conversation.

## Permission and API contract

Default: **no tools, no filesystem roots, no origins, no commands or accounts**.
The Actions panel in Chat grants/revokes individual tools and explicit resources.
Each directory line starts with `read /absolute/path` or `write /absolute/path`;
mixed grants remain distinct. A grant must identify an owner-owned directory,
not a broad system directory, hidden path or the private runtime state.

- Read-only: only granted read tools can run.
- Assisted: every modifying plan requires explicit preview approval.
- Autonomous: granted low-risk new-file/copy/directory/task/draft operations may
  run within standing scopes. Moves, trash, organization, browser interactions,
  command profiles, window focus/close and Calendar saves still require a specific
  exact-plan approval. No model can approve, configure or widen grants.

Approvals bind the typed plan, resource snapshots and complete policy revision.
Changing a policy, including revoking and restoring identical settings, invalidates
old plans. Approval expires after ten minutes; execution checks expiry, revocation
and cancellation at bounded I/O boundaries. Recovery requires explicit owner
approval, current tool grants and writable scopes; changed files are never
silently replaced. No unrestricted root or privilege-elevation tool exists.

All routes below are bounded JSON POSTs under `/api/v1/actions/`. They use the
existing same-origin owner-browser gate, including its protected HttpOnly session
and configured remote Access requirements. An `inbox:read` bearer cannot invoke
any route. Payloads reject unknown fields/wrong types; errors do not echo input.

| Suffix | Purpose |
| --- | --- |
| `capabilities` | Typed manifests, limits, readiness and current policy |
| `policy` | Owner-only compare-and-swap policy edit by revision |
| `propose` | Conversation/request ID, owner instruction, optional typed plan |
| `history` / `get` | Conversation actions / detailed current plan and receipts |
| `execute` | Start once, with exact approval digest where required |
| `cancel` | Persistent cancellation observed by worker/process boundaries |
| `resume` | Explicit continuation of safely stopped work; never ambiguous writes |
| `recover` | Receipt-based supported inverses, with fresh owner confirmation |

Plans, steps and append-only events live in additive version-guarded SQLite tables.
Request digests prevent changed-payload retries. A private cross-process flock
serializes execution; a daemon thread runs bounded work while HTTP polling shows
real step states. Verified steps are not rerun. A restart with no live lock owner
marks started work `needs_reconciliation`. Partial organization checkpoints permit
recovery of observed moves. Failed read work can resume; ambiguous writes cannot
be blindly retried. Recovery records per-operation completion so a partial
recovery does not repeat already verified inverses. Deleting a conversation with
a running action is blocked until cancellation; normal conversation deletion
cascades its completed action records.

## Capability matrix

| Capability | Working behavior | Limits / recovery |
| --- | --- | --- |
| Files | List/search metadata, bounded recursive inventory, hash duplicates, read, create directories/new files, copy, move/rename, extension-based organization, recoverable trash | Owner scopes; no hidden/symlink/special/hard-linked files; 8 MiB/file; 200 listed entries, depth 5; no overwrite or permanent-delete tool |
| Recovery | Restore moves/trash, preserve newly created files in private recovery, remove unchanged empty created directories | Requires unchanged hashes/inodes and absent restore destination; interrupted unknown changes need manual reconciliation; organization can leave empty category folders |
| Documents | TXT/Markdown/CSV/TSV/JSON, PDF, DOCX, XLSX extraction; comparison with shared/unique source quotations, paths and hashes | PDF first 30 pages, text 12k chars/source, bounded archive expansion; XLSX cached values only, no macro execution/OCR/formula recalculation |
| Local intelligence | Pinned Ollama interpretations with source index and exact quotation validation; extractive evidence remains available offline | Interpretations are labelled model analysis, not verified truth; excerpt coverage is bounded |
| Browser | Real Chromium navigation, text/links, multi-source Markdown research, typed fill/click and authorized downloads | Fresh isolated profile, exact origins and pinned DNS, request/time limits, 64 KiB downloads; no personal cookies, arbitrary JavaScript tool, credentials, financial-field fill, CAPTCHA/MFA bypass or authenticated personal-browser takeover |
| Desktop | Hyprland window classes/addresses, verified focus/close, allowlisted desktop launch, scoped file open, notification dispatch | Uses installed Lua dispatch API with validated hex addresses; launch/open/notification acceptance is reported honestly and does not assert application readiness or screen visibility |
| Commands | Exact owner-configured argv profiles, process-group timeout/cancel | Bubblewrap mount/PID/network namespaces; only `/usr` and granted roots, private temporary HOME, no network or credential directories; no model shell text or sudo |
| Tasks / Calendar | Existing local TaskBoard create/transition/read and LocalCalendar revision/idempotency/save/readback | Existing local contracts; no new Google external-write authority |
| Gmail | Account-granted cache search and local reply draft through the existing provider/source-validated service | Correct configured account required. Real sending remains the existing Inbox exact-recipient preview/token/confirmation/reconciliation flow; live account sending was not tested or activated |
| Chat | Natural English/Egyptian-Arabic plan requests, understandable previews, approval, status, cancellation, recovery, resume and durable receipts | Permissions are configured first; incomplete/invalid plans fail honestly; no fabricated percentages or unobserved success |

Generic shell profiles are deliberately owner-authored fixed commands inside a
namespace sandbox. They cannot access the whole home directory or host processes.
Desktop operations are separate typed adapters with exact-action confirmation.
Unsupported formats, unavailable native libraries, invalid model output, missing
sessions or ungranted resources stop with an error; no weaker fallback is enabled.

## Security review and resource controls

Filesystem traversal opens every ancestor with `O_NOFOLLOW` and directory FDs.
Reads reject foreign/special/multiply linked files. New writes use `O_EXCL`, fsync
and hash readback; Linux `renameat2(RENAME_NOREPLACE)` prevents collision clobbering.
Trash uses owner-private recovery inside the granted folder. Recovery paths come
only from server-created receipts, never model input. Mutation intents are saved
before dispatch. A crash can leave a partial new file; the ledger reports
reconciliation rather than removing unknown content or claiming no change.

PDF processing uses Bubblewrap with stdin/stdout and no home/network access.
OOXML extraction caps entry count and expanded bytes and rejects entity/DOCTYPE
XML; macros and external relationships are never executed. Source documents and
web pages are untrusted evidence. Plans are fixed before those tools execute;
embedded text cannot add a step or change policy. Interpretive model output must
quote an actual source and cannot authorize actions.

Chromium's sandbox stays enabled. A separate worker uses an ephemeral profile,
blocks service workers/WebSockets, enforces exact origin/method/request limits
and pins allowed DNS mappings, preventing DNS-rebinding into private networks.
Numeric owner-granted loopback origins support test/dev pages, but Core/model
ports 8766/8876/11434 are prohibited. Cookies/profiles from personal browsers are
never loaded. Password/OTP/financial fields stop for the native owner workflow.
Subprocesses receive a minimal environment, bounded output and process-group
cancellation. Native stderr and rejected secret-like inputs are not returned.

Known credential patterns are rejected before persisted plans/results; this is
not comprehensive secret classification. Do not provide credentials in chat,
command profiles or documents. All state is local/private. Only owner-granted
browser origins receive browser traffic; private documents are not uploaded.

Fresh AI-assisted review fixed: dependent-file chaining, revoke/restore replay,
interrupted executor state, recovery pagination/checkpoints, mixed root grants,
private UI clearing, poll races, current Hyprland syntax and sandboxed PDF parsing.
No independent human approval or general security certification is claimed.

## Reproducible verification

Run with `PYTHONPATH=apps/core/src` and the isolated Core Python:

```bash
python -m unittest discover -s apps/core/tests -v
node --test apps/core/tests/test_*.cjs
python apps/core/tools/computer_acceptance.py --public
python apps/core/tools/computer_desktop_acceptance.py
python apps/core/tools/verify_runtime.py
bash scripts/validate-governance.sh
```

The device acceptance tool uses temporary roots, SQLite and synthetic accounts.
Its optional public research reads the official Python sqlite3 and SQLite atomic
commit documentation. No Gmail send, production write or personal file cleanup
is attempted. Tests requiring native PDF namespaces can report an explicit skip
on CI hosts without that capability; the owner-device PDF path was actually run.

On this Omarchy host: 475 Python tests and 79 Node tests passed at final local
verification. The device runner passed ten scenarios plus real English and Arabic
model-planned execution: A file organization/hash integrity; B three-report
comparison with validated model quotations; C real browser source research and
local report; D search → report → local task → workspace; E hostile document as
inert data; real browser form submission/download; public credible sources;
Hyprland window observation; and a real sandboxed command. Separate native tests
observed desktop launch through a disposable desktop entry and verified focus;
a dedicated synthetic Foot window was created, focused and closed successfully.
No persistent desktop configuration or application entry was installed.

Browser acceptance through the actual Chat UI verified natural plan creation,
no move before approval, verified execution, persisted receipts after reload,
and zero browser local/session storage entries. The inherited optional
FullCalendar vendor asset is still absent; its existing fallback and workflows
remain covered by inherited tests. The process smoke preserved summaries/token
across restart and graceful shutdown (approximately 0.263 s startup, 60.4 MiB peak
RSS); its static environment label is generic, not production/boot acceptance.
Final current-head CI, review and merge evidence are recorded on the PR.

## Dependencies and rollback

Playwright is [Apache-2.0](https://github.com/microsoft/playwright-python/blob/main/LICENSE),
with pyee (MIT) and greenlet (MIT/PSF) in the hash lock. Chromium, Bubblewrap and
Poppler are existing machine dependencies, not vendored source. No model download,
paid API or persistent privileged service was added. Browser documentation:
[Playwright library](https://playwright.dev/python/docs/library).
Current desktop dispatch documentation:
[Hyprland dispatchers](https://wiki.hypr.land/configuring/core/dispatchers/).

Installing the optional action environment uses the reviewed hash lock:

```bash
python -m pip install --require-hashes -r apps/core/requirements-actions.lock
```

This PR is not a production deployment. Before a separately authorized rollout,
use the existing private SQLite backup procedure, record the reviewed commit,
verify native executables/session availability, then configure only intended
scopes in the owner UI. Never grant the private state directory or all of home
merely to make a tool pass. Keep remote/session protections unchanged.

Rollback code to the preceding main; additive action tables remain recoverable
and older Core ignores them. Revoke grants/cancel active work first. Receipt-based
recovery can restore supported unchanged resources; do not restore an old database
over newer mail/calendar/task writes or drop tables to undo filesystem actions.
Backups, other open tabs and already performed external effects have their own
lifecycle. Preserve ambiguous receipts for reconciliation.
