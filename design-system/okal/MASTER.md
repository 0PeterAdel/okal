# OKAL Dashboard V2 — Design System

**Direction:** dark professional desktop productivity application with premium editorial hierarchy, inspired by the MIT-licensed [UI/UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) skill's accessibility, layout, interaction, and design-token guidance. This is an implementation-specific synthesis, **not** a claimed output from the skill's optional BM25 generator script.

## Intended user and architecture

- Single-user private Omarchy workstation, Firefox, responsive to tablet/mobile.
- Static semantic HTML, CSS variables, and vanilla JS — no React/framework migration, fonts downloaded from the internet, runtime CDN or paid service.
- Existing local FastAPI GET endpoints remain unchanged; send / Gmail Trash writes stay in the owner-reviewed terminal workflow.
- Arabic-first interface with supplementary English labels, right-to-left reading, support for long bilingual email subjects.

## Product design language

- **Style:** Content-first dark dashboard with calm editorial whitespace and restrained surface depth. Avoid excessive glass effects, animated gradients, and giant email summary blocks.
- **Roles:** background `#090e16`, nav `#0d1420`, surface `#101a27`, raised `#152131`, foreground `#eff6f6`, secondary `#a3b7c4`, border `#263747`, accent `#7de8c1`.
- **Status:** action accent, manual review warm amber, information cool blue, destructive review soft rose. State always includes words, not color alone.
- **Typography:** local system UI stack (system-ui/Segoe UI/Tahoma), fluid headings, readable 15–17px summaries, metadata 11–12px. Avoid external font/CDN privacy dependency.
- **Spacing:** 8px-based rhythm with 12/16/22px radii and predictable 14–24px card padding.
- **Motion:** 160ms lightweight color transitions; `prefers-reduced-motion` disables non-essential transitions.
- **Layout:** 244px persistent sidebar at >=900px; tablet/mobile horizontal navigation. 3 KPI cards; hero-style daily brief; two-column triage and secondary panels where enough width. Single column below 1230 for inbox categories and below 900 for lower panels. No off-screen fixed overlays.
- **Loading/privacy:** built-in read-only dashboard auto-opens on localhost, no need for new key. All email/AI text is written using `textContent`, never `innerHTML`. `lock()` clears cached displayed private data.

## Desktop selection contract

- **Ordinary Click:** select exactly one eligible Information email.
- **Ctrl+Click or Cmd+Click:** toggle one while preserving other selections.
- **Shift+Click:** select contiguous eligible range anchored at previous selection (without Ctrl replaces; with Ctrl/Cmd adds).
- **Checkbox:** independently toggle a single email; `Shift+click` uses range selection where available.
- **Keyboard:** Tab to an eligible email, Enter/Space toggles its selection; `Ctrl/Cmd+A` selects first 20 only when focus is inside Information, `Escape` clears it.
- **Buttons:** Select all (first 20), Clear, Prepare Gmail Trash command. Never any Gmail modifying request from the browser.
- **Guard:** limit 20, duplicate source IDs ignored, protected Gmail labels excluded, selection reset on full refresh or hide, copied preview invalidated on every selection change.
- **Feedback:** visible selected backgrounds and checkboxes, contextual live count and explicit instruction about Terminal approval.
- **Touch:** native checkbox and select/clear buttons are the discoverable non-modifier alternatives.

## Skill checklist and known limits

- Contrast-aware semantic colors and distinct focus ring, keyboard focus, no hover-only core actions.
- Breakpoints considered: 375px, 768px, 1024px, 1440px; screenshots and owner-browser review still required on Omarchy at actual zoom levels.
- No browser write endpoint, no mutation of OAuth account scopes, no permanent Gmail delete.
- The command builder is a **preview only**. Owner must still use the native Gmail API through the separate CLI `mail trash --ids ... --apply` with explicit interactive approval.
- This branch is stacked on the AI Morning editor draft, which is itself stacked on previously unmerged Gmail/Task PRs. Do not blindly force/reset the owner's production checkout.
