# Impeccable for OKAL UI

Impeccable is a third-party open-source design skill, **not** an OKAL runtime dependency. Review the official [Impeccable repository](https://github.com/pbakaus/impeccable) and [installation guide](https://impeccable.style/tutorials/getting-started/) before running its code.

## Local Codex installation

From the owner's trusted Omarchy project checkout:

```bash
cd /home/okal/Projects/okal
npx impeccable install
```

Choose **project scope** when prompted, reload Codex, and run `$impeccable init` inside the agent. Inspect the resulting skill, any `PRODUCT.md` / `DESIGN.md` files and automatic hooks **before enabling or committing them**. The upstream installer was not run on the owner's laptop by this PR. Do not install with sudo, and never commit credentials, private browser data or local mail.

## Design direction: Operate

- OKAL is an Arabic-first, RTL private productivity command center. The primary user reads saved Gmail insights, manages local tasks and explicitly approves Gmail actions.
- Keep the established dark ink/teal design tokens in `design-system/okal/MASTER.md`. Prefer hierarchy and legible content over decorative tags, unnecessary cards or motion.
- Maintain original HTML, CSS and vanilla JavaScript. No frontend framework, hosted font, analytics asset, paid service, external CDN or extra local browser storage.
- Preserve the native Gmail reader iframe's script-disabled sandbox and existing image-loading privacy notice. Never weaken Gmail action previews, approval tokens or permission checks.
- Every section label and status should reflect current behavior. In particular, Gmail modifications can be **approved in the browser**; the old Delete PIN is retired; voice playback is deferred.
- Polish mobile navigation, focused controls, long mixed Arabic/English content and responsive text with minimal churn.

## Verification and acceptance

- This change addresses [UI issue #56](https://github.com/0PeterAdel/okal/issues/56) following the official Impeccable `audit` and `polish` recommendations.
- Test source logic with `node --check apps/core/src/okal_core/static/app.js` and `node --test apps/core/tests/test_inbox_status.cjs`. Also require GitHub Governance, Markdown, Python 3.12 / 3.14 and UI CI.
- The owner should test Firefox at 375px, 768px and desktop width, 200% zoom, keyboard Tab/Shift+Tab, mouse and touch selection, and email dialogs using real but noncritical data.
- A source audit and passing CI do not prove a flawless visual result. Do not claim real browser acceptance without screenshots or a human trial.
- Do not merge until the owner has recorded the required Solo Maintainer non-approval self-review against the current commit SHA; AI comments cannot substitute for human review.
