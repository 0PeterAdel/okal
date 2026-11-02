# Source-verified Gmail to Calendar suggestions (review-only)

Issue [#68](https://github.com/0PeterAdel/okal/issues/68).
This is the **remaining independent portion** of superseded Draft PR #69.
Owner-reviewed local task time-blocking is already implemented with explicit
estimates in merged PR #79, rather than reusing the old 30-minute assumption.

## Source-backed user workflow

An eligible locally seen Gmail message has a new, disabled-until-read
**اقتراح موعد من البريد** button. On explicit click only, the same-origin
`POST /api/v1/calendar/mail-proposal` checks the message against the owner's
local native Gmail source identity and reads exactly that message from native
Gmail. The existing pinned local Ollama runtime proposes a title and literal
excerpt from the message. Server code rejects excerpts not present verbatim in
the original Gmail body and never treats natural-language time, unsourced
timezones or hallucinated dates as confirmed timestamps. Only timezone-aware
ISO instants directly present inside that excerpt become candidate timestamps.

Gmail body text is untrusted model input. The UI uses text nodes only;
results are tied to the viewer generation and message ID; closing the
viewer clears all content. The result is for **human inspection only**:
no Google Calendar write scope, no event create/update/delete, no local plan
save or task mutation, no OAuth changes and no external LLM service.

## Limits and risks

- Source-grounding validates quoted text, **not** that an email actually
  represents an accepted invitation. The owner must decide.
- The native Gmail read occurs on click, so a configured Gmail account and
  healthy local Ollama are required. A stale, truncated, unverified or
  disallowed message is rejected.
- Date/time extracted without a full ISO offset remains unresolved.
- Calendar availability may be incomplete; no free-time claims or automatic
  booking is provided.
- Existing #79 Plan My Day time-block engine remains the safe, review-only
  alternative to outdated PR #69's invented 30-minute task effort.

## Acceptance gates

```bash
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests -p 'test_calendar_mail_proposals.py' -v
node --test apps/core/tests/test_inbox_status.cjs
```

Run GitHub CI on exact PR head. Before merging, obtain a legitimate human
review approval under ShiftCore methodology; CI cannot substitute for it.
Owner must open one non-sensitive email containing explicit ISO times in
Firefox, click suggestion, compare title/quote/date against Gmail, and
confirm no Google Calendar event was created. Then test an ambiguous or
unrelated email to verify safe refusal. No production deployment until
approved and owner's SQLite is backed up.
