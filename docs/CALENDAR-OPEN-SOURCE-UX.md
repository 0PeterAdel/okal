# OKAL Calendar UX — first external-code integration

Task: [#76](https://github.com/0PeterAdel/okal/issues/76).

## Decision: make the product useful before adding another agent

A personal assistant should answer "what is next and what should I do now?"
in one glance, not require users to read sync counters and a wall of event
cards. This batch adds a focused date navigator and selected-day context to
the existing read-only unified calendar. The full seven-day timeline remains
available on demand behind a native `details` panel.

### Code sources and licensing

- **Vendored production source:** [Vanilla Calendar](https://github.com/senese/vanilla-calendar) by Yury Uvarov,
  **MIT**. Exact upstream Git commit:
  `688a381e76e80750ca25f9a72866ba2b6c4cf747`.
  Directly copied *unmodified*:
  `build/vanilla-calendar.min.js` (30,343 bytes),
  `build/vanilla-calendar.min.css` (15,538 bytes), and `LICENSE`
  into `apps/core/src/okal_core/static/vendor/`.
  Authors retain copyright; see `vanilla-calendar.LICENSE`.
  Includes no runtime analytics, remote calls, or paid features.
  This component provides **date selection**, not automatic scheduling.
- **Future event-time grid:** [FullCalendar Standard](https://fullcalendar.io/license), MIT. Day/week/month timeline, event
  density, responsive controls. No source from FullCalendar is copied in
  this PR; its v7 build requires a JavaScript bundling/Temporal integration
  that should be measured separately.
- **Product-pattern research only:** [Horolog](https://github.com/ujjwalredd/horolog), AGPL-3.0:
  stable deadline-aware re-planning, local Ollama, preserving existing blocks.
  [Atomic](https://github.com/Cephren/atomic), AGPL-3.0:
  priorities, time constraints, task templates. No code copied from either,
  to avoid accidentally imposing reciprocal license obligations on the
  current private repo or future product.
- **UX-pattern research only:** [Open Sunsama](https://github.com/ShadowWalker2014/open-sunsama) uses a custom
  non-commercial license; its day planning, focus mode and time-boxing
  patterns are useful, but source reuse is excluded.

## Three user improvements delivered

1. **Open-source monthly date navigator** — lightweight month/day picker
   embedded directly in OKAL; restricted to the **loaded day/week range**.
   Disabled dates must never signal the absence of real Google events.
   Entirely offline from the same localhost origin and honoring the
   existing strict CSP.
2. **Day Focus** — first screen in Calendar shows one selected Cairo day,
   count of cached provider events vs local confirmed task deadlines, an
   upcoming item when there is one, and individual event/task titles.
   Events crossing Cairo midnight appear on every applicable date; all-day
   ends are exclusive and instant events are points, not busy intervals.
   User names are inserted as text nodes, never HTML.
3. **Less UI noise, clear action** — long week list is collapsed under a
   native accessible toggle, with an obvious link to the current local
   Tasks board for editing/finishing tasks. The previous sync/coverage
   warning and conflict panel are retained; a zero-event day never claims
   free time. No Google write, auto-scheduling, private browser storage or
   extra permissions.

## What is deliberately not promised

This is a day-focus navigator, **not** the FullCalendar time grid, AI planner
or automatic task placement. An existing Gmail proposal branch remains
separate, and Google Tasks aren't available via Calendar Events API.
True time-blocking requires owner-configured task estimates, verified
calendar sources and a strict approval policy; Horolog-like auto-replanning
cannot be honestly claimed yet.

## Developer tests and owner acceptance

```bash
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests \
  -p test_calendar_planning.py -v
node --test apps/core/tests/test_inbox_status.cjs
bash scripts/validate-governance.sh
```

After approval, back up private SQLite as usual, fast-forward production
`main` and restart `okal-core.service`. Open
`http://127.0.0.1:8766/#calendar-section` in Firefox and hard-refresh.
The new Focus panel must show correctly labelled cached events for Nov 2,
Nov 3 and Nov 5 (as applicable within the currently loaded seven days).
Selecting Nov 3 should show its event; clicking a date outside the loaded
range is disabled. Open the native "all events" details to see the previous
list, use the link to visit Tasks, and verify no background CDN requests.
Keyboard access, Arabic text, 375px/768px widths and dark mode need
real owner checks. Unit/CI tests are not substitutes for real UX acceptance.

This slice does not touch or reset existing OAuth, Gmail, background
Calendar sync or personal SQLite. PR should be reviewed and squash-merged
through main only after exact-head CI and license notice checks.
