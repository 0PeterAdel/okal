# OKAL Inbox Actions — local Gmail triage and email-to-task previews

This module builds on the **existing** Gmail History ingestion and pinned
local Ollama summarization. It does **not** add Google Workspace CLI as a
runtime dependency, install another MCP server, change OAuth scopes, or run
Inbox Zero's hosted stack. It borrows narrow *workflows*, not third-party code.

## What works now

- **Gmail triage helper:** read-only action, information and low-priority
  groups are already in the dashboard. Inbox Actions adds action priority,
  review tasks, reply candidates and read-later buckets over the saved evidence.
- **Rule-based assistant:** owner-only, strict JSON policy matched against
  provider metadata and saved AI classification; a rule never grants the AI
  permission to send, delete, unsubscribe, archive, or create a calendar event.
- **Email-to-task preview:** proposes a title and native Gmail source link;
  due date stays `null` until an owner verifies the actual date. The item is
  **not** created in Google Tasks, Calendar, or an external task service.
- **Reply review:** a matching rule only surfaces a candidate. To generate a
  draft intentionally, use the pre-existing CLI `mail reply` with an owner
  instruction and preview before any manual send.
- **Manual review:** quarantined/unreadable messages are shown with links,
  never silently treated as complete.
- **No extra polling:** the existing restart-safe Gmail History worker drives
  all snapshots. Dashboard GETs and `mail assistant` read local SQLite only.

## Use on the Omarchy machine

From `/home/okal/Projects/okal` after updating the branch:

```bash
# Safe counts: no private subjects or sender addresses printed
bash scripts/run-okal-core.sh mail assistant --view summary

# Full preview of messages/tasks: ONLY inspect on the private machine.
# Contains email subjects, senders and AI suggestions. Do not paste it to chat.
bash scripts/run-okal-core.sh mail assistant --view queue
```

Open `http://127.0.0.1:8766`, pair with the usual local inbox-read key, and
look for **اقتراحات المهام والردود / INBOX ACTIONS**. Dashboard requires no
new tokens/scopes; it only displays already-recorded information.

### Optional, editable rules

The initial built-in policy is: action -> task_review/high;
information -> read_later/normal; low_priority -> read_later/low.

To customize, create `~/.local/state/okal-core/mail/assistant-rules.json`
as a **0600 owner-only file** in the same mail private state path:

```json
{
  "version": 1,
  "rules": [
    {
      "name": "project-replies",
      "sender_domain": "example.org",
      "subject_contains": "project",
      "bucket": "reply_review",
      "priority": "high"
    },
    {
      "name": "other-action-tasks",
      "category": "action",
      "bucket": "task_review",
      "priority": "high"
    },
    {
      "name": "low-priority-mail",
      "category": "low_priority",
      "bucket": "read_later",
      "priority": "low"
    }
  ]
}
```

Rule selectors are optional `sender_domain`, `subject_contains`,
`category` or `label`; at least one must be present. If multiple selectors
are specified, **all** must match. The first matching rule wins; unmatched
messages remain read-later. Up to 32 uniquely named rules are allowed.
`category` is one of `action`, `information`, `low_priority`.
`label` is one of `INBOX`, `UNREAD`, `STARRED`. Buckets are
`task_review`, `reply_review`, `read_later`, `manual_review`.
Priorities are `high`, `normal`, `low`.

These are **untrusted heuristics**: email From headers can be spoofed, a
category comes from a fallible local AI model, and unread labels are a saved
snapshot rather than an up-to-the-second Gmail query. Rules cannot create
external side effects, so an attacker-controlled email cannot turn a rule
into a send/archive/delete operation. All suggested actions are subject to
human confirmation.

To use policy without creating a config file, keep the built-in defaults.
If the file exists but is malformed or has unsafe permissions, the service
fails closed for the assistant view rather than ignoring it.

## Integration roadmap (not falsely marked as connected)

- **Google Tasks / Calendar:** implement explicit owner-approved, scoped
  provider adapters before external creation; do not request write scopes
  until needed. Current proposals have `status=suggested_not_created` and
  `due_date=null`; no events are scheduled.
- **Follow-up monitoring / Reply Zero:** existing `mail followup <id>`
  checks a live Gmail thread on an explicit operator call. A durable
  reply-awaiting monitor requires a separate, reviewed state machine.
- **Gmail Watch / Pub/Sub:** no extra subscription, renewals or Cloud
  dependencies. Existing 300-second polling and history checkpointing remain.
- **Inbox Zero bulk actions:** deliberately NOT implemented. Bulk archive,
  unsubscribe, auto-send and rule-driven destructive changes would require
  independent authorization and reconciliation tests.
- **Workspace MCP:** later expose narrowly scoped tool calls to OKAL's
  central agent, initially read-only; do not spin up a second OAuth store or
  merge arbitrary third-party tools into the Core security boundary.

## Security & acceptance

Only local SQLite is read by the view; no model inference, Gmail API calls or
state transitions on display. Sender, subject and recommendation text are
inserted with `textContent` in the browser; the API remains loopback-bound
and uses existing owner read sessions. The queue is a preview, not actual
tasks or replies. It processes up to the newest 60 saved insights plus a
bounded manual review sample, and returns a sample count, **not** the total
historical inbox size.

Reference ideas, not copied code: Google Workspace CLI helper skills;
google_workspace_mcp service segmentation/read-only capabilities; Inbox Zero
rule/Reply Zero/task patterns.
