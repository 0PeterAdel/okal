# OKAL Local Task Board — Phase 2 foundation

This phase upgrades the existing OKAL single-user local inbox to manage
**owner-approved tasks**, while keeping all Google integrations and outgoing
actions disabled. It is stacked on the unmerged Gmail PR #42. It is NOT part
of the current local production checkout until reviewed and fetched.

## Scope actually implemented

- One `local_tasks` table in the existing owner-only SQLite database.
- Explicit add/complete/dismiss commands and durable, idempotent status changes.
- A real saved Gmail source may be previewed as a local task, but **nothing
  is created until the owner passes `--approve`**.
- One task per Gmail message/account, even after restart or repeated approval.
- Dates require an explicit timezone-aware ISO 8601 value supplied by the
  owner; no AI guesses become calendar events or deadlines.
- Read-only `GET /api/v1/tasks` and a **مهامي ومواعيدي** dashboard section.
- Local Task Board does not invoke Gmail, Ollama, Google Tasks, Calendar,
  email send, external reminders, or paid APIs. No OAuth permission change.

## Operator commands on Omarchy

Use after switching/updating the *new* task-planning branch in a reviewed
checkout. Do not overwrite a dirty checkout or reset unrelated files.

```bash
cd /home/okal/Projects/okal

# Safe local task listing:
bash scripts/run-okal-core.sh tasks list

# Create a task with an owner-verified date and timezone:
bash scripts/run-okal-core.sh tasks add \
  --title "Review the project proposal" \
  --due "2026-11-02T18:00:00+02:00"

# View Gmail message ID and suggestion locally in Inbox Actions.
# FIRST: see task proposal, no mutation.
bash scripts/run-okal-core.sh tasks from-mail 0123456789abcdef

# Only AFTER verifying the correct Gmail source in your browser:
bash scripts/run-okal-core.sh tasks from-mail 0123456789abcdef \
  --title "Follow up on the project" \
  --due "2026-11-03T12:00:00+02:00" --approve

# Mark a task complete (replace with task ID returned by the CLI):
bash scripts/run-okal-core.sh tasks done TASK_ID

# Or dismiss:
bash scripts/run-okal-core.sh tasks dismiss TASK_ID

# View historical task states:
bash scripts/run-okal-core.sh tasks list --status all
```

The hexadecimal Gmail ID is an **example**: substitute a real saved source
ID from the local Inbox Actions preview, never paste real email contents,
Gmail tokens or your entire database to GitHub or chat.

`tasks from-mail` with no `--approve` previews a task but has no state
changes. An explicit duplicate approval returns `already_recorded`;
it never creates another local task for the same Gmail message.

### Dashboard

Open `http://127.0.0.1:8766`. Under the saved Gmail previews find
**مهامي ومواعيدي**. It shows confirmed open tasks with owner-entered due dates
and links to source emails. **It cannot create, edit, delete or approve tasks
from an HTTP request**. Use the owner's local CLI for writes.

The read endpoint `/api/v1/tasks` inherits the existing loopback-only
read boundary: Local Auto-Unlock in single-user mode, or optional read-key
protection. A future task-write API cannot be automatically granted local
passwordless access.

### Limitations and next phases

The new `local_tasks` table stores explicit owner approvals and deadlines.
The page reads this table only; it does NOT auto-create tasks from AI suggestions.
No desktop reminder notification or background alarm is scheduled yet.
Upcoming development can add an offline desktop notification worker with a
durable per-task receipt, followed by optional Google Calendar/Tasks syncing
only with separately reviewed OAuth and opt-in approval.

The Gmail insight itself is untrusted and a `From:` header is not proof of
identity. The default proposed title is `Review email: <subject>` rather
than turning AI-supplied instructions into tasks. All due dates must be
entered by the owner.

PR remains Draft until tests, local review and release gates pass.
