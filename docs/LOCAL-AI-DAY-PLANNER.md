# Local AI Plan My Day — constrained Ollama estimates

Issue #81. This feature is opt-in, free and entirely on the owner's
localhost Ollama runtime. It never creates Calendar events or modifies
Google Tasks, Gmail or approved local tasks.

## Flow

1. Choose 1–12 locally open tasks in the existing Plan My Day form.
2. Click **«اقترح مدة وأولوية المهام باستخدام Ollama المحلي»**.
   A same-origin POST sends **only selected task IDs, shortened local task
   titles and optional Cairo deadline day** to `127.0.0.1:11434/api/chat`.
   There are NO OAuth tokens, Gmail message bodies, calendar event titles,
   account emails or external network URLs in the model prompt.
3. Use `format` as a strict Ollama JSON schema, temperature=0 and an
   eight-second timeout. Allow only existing IDs exactly once, duration in
   `{15,30,45,60,90,120,180,240}`, priority in
   `{high,normal,low}`. Any unknown ID, invented action, malformed JSON,
   provider/model outage or missing result fails closed.
4. Accepted estimates populate **editable** duration and priority dropdowns.
   The human still checks the values, explicitly clicks Plan My Day Preview,
   reviews the deterministic conflict-free *tentative* time blocks, then
   explicitly confirms a local-only saved plan through the preexisting
   one-use approval ticket.
5. No model result can write or approve a plan. Any unverified calendar
   source keeps availability unverified. Manual estimates work when Ollama
   is offline.

## Model setup

Default model alias: `okal-qwen3.5-4b-64k:latest`. Override if needed
using `OKAL_PLANNER_MODEL` in the private **user service environment**,
but only with an actually installed local Ollama model. The model selection
accepts a strictly bounded local name; no URL injection or remote endpoint.
No extra API keys or paid services.

Official Ollama structured-output reference:
[Ollama structured outputs](https://ollama.com/blog/structured-outputs).

## Tests

```bash
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests -p test_day_plan_ai.py -v
node --test apps/core/tests/test_inbox_status.cjs
```

Owner Firefox acceptance after approved merge: choose 2 tasks; click AI
estimates (with Ollama locally running), inspect editable values, then
preview. Verify no local plan saved until clicking Confirm, no Google
Calendar writes, and complete manual fallback when Ollama is stopped.
CI unit tests mock Ollama, not proof of model availability on the owner's
Omarchy device. This PR is independent of Google Tasks PR #83 and can be
reviewed separately.
