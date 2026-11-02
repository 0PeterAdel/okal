# FullCalendar Standard Timeline — MIT, Offline Runtime

Issue #82. This PR adds a native FullCalendar Standard v6 day/week/month
calendar view using the existing read-only local OKAL agenda and owner-approved
private Plan My Day blocks. All external Google event writes remain disabled.

## Why v6.1.22 instead of v7

Standard FullCalendar is MIT in both versions, but v7 changed how global
script bundles, themes, Temporal polyfill and premium packages work. For
OKAL's existing zero-build plain JavaScript dashboard, the MIT
`fullcalendar@6.1.22` **global bundle** is more compatible. It includes
standard DayGrid/TimeGrid/List plugins. No premium Scheduler or calendar
provider SDK is used.

Official reference:
[FullCalendar v6 script tag upgrades](https://legacy.fullcalendar.io/v6/upgrading-from-v5).
License: [FullCalendar MIT license](https://github.com/fullcalendar/fullcalendar/blob/v6.1.22/LICENSE.md).
FullCalendar may be studied, used, distributed and modified under MIT,
provided the author notice is retained. Copy of notice included in
`apps/core/src/okal_core/static/vendor/fullcalendar.LICENSE.md`.

## One-time owner installation (requires Internet once, not at runtime)

Because FullCalendar v6 compiled release bundle is **not** tracked in its
GitHub source repository, the PR pins a one-time npm package installer
instead of committing unreviewed/minified third-party code:

```bash
cd "$HOME/Projects/okal-production"
bash scripts/install-fullcalendar-standard.sh
```

The script runs `npm pack --ignore-scripts fullcalendar@6.1.22`, extracts
ONLY `package/index.global.min.js`, checks presence and size, and copies
it with mode 0644 into the local static `vendor/fullcalendar` directory.
npm verifies package integrity as part of download. The compiled bundle is
ignored by Git and is not hosted on any CDN at browser runtime.
The script requires npm, tar and temporary Internet access. No automatic
remote download occurs on dashboard GET or app/service startup.

**Important:** The minified official vendor asset is not in the PR because
the repository source tree does not ship it. The live vendor installation
on Omarchy and browser screenshots remain owner acceptance gates. Until
installed, the new panel displays an explanation; the previously working
Day Focus and Plan My Day remain available.

## Data and safety policy

- Only cached `/api/v1/calendar/plan` event timestamps, owner-confirmed
  local task deadline points and approved local Plan My Day block data are
  projected. No URL feeds, remote providers or OAuth access in FullCalendar.
- Exact provider event intervals, including Cairo timezone, all-day
  exclusive end, and instant events as point indicators.
- Local task deadlines remain points, **not busy time intervals**.
- Approved local Plan My Day blocks are labelled *tentative*; they do not
  claim provider verification or create Google events.
- If Google Tasks PR #83 is later merged, its date-only tasks can be
  projected as **all-day, list-style date markers**, without invented
  time-of-day or deadline semantics. This PR does not require #83.
- `editable=false`, `selectable=false`, `droppable=false`,
  `eventStartEditable=false`, `eventDurationEditable=false`.
  No event write handler. Selecting a loaded day is a local UI action only.
- Visibility of dates outside the loaded week never implies no bookings;
  the explicit incomplete-source warnings remain visible.

## Tests

```bash
node --test apps/core/tests/test_fullcalendar_ui.cjs
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests \
  -p test_dashboard_ui_contract.py -v
```

CI checks mocked FullCalendar data mapping, read-only control flags, no
remote event sources, missing-vendor fallback, strict script order,
existing Gmail/security tests and Markdown/governance.

Owner rollout: after approved merge and private SQLite backup, run the
vendor installer once in Production, restart OKAL and hard refresh Firefox.
Check Week/Day/Month, real Nov 2–5 Google events, approved tentative blocks,
mobile RTL layout, no provider writes, no CDN requests, and local fallback
if installation is skipped. Do not merge this PR as fully accepted without
the real rendered bundle test.
