# OKAL Chat public web browsing — read-only

Issue #132. This change is engineering code only, not a Production deployment.

## User experience

- Say `ابحث في النت عن ...`, `Search the web for ...` or ask for current
  updates to create a bounded, deterministic `browser.search` plan.
- Say `افتح https://example.org/` or `open https://example.org/` to create
  a `browser.public_read` plan for that exact public HTTPS URL.
- When the plan finishes, the existing Chat Actions card displays the *observed*
  title, bounded excerpt and user-clickable source links. Empty/failing browser
  results produce failure receipts, not fabricated answers or success claims.
- Existing `browser.read`, `browser.research` and `browser.interact`
  continue to require exact owner-approved origins. No auto-grant migration.

## Security and privacy

- Both new tools are **opt-in individually** in Actions. They are read-only and
  cannot execute clicks/fills/downloads, provider mutations or desktop commands.
  The current owner-browser authorization and revocable policy apply to every
  action request, including a previously planned read-only action.
- `browser.search` sends the owner's explicit (at most 180-character) query
  to external `https://www.google.com`. It is **not fully offline**. Do not
  search private data or credentials. No external AI provider or paid API.
- `browser.public_read` supports public DNS-based HTTPS websites on the
  standard port only. DNS results must be globally routable; numeric IPs,
  loopback, private/reserved/link-local ranges, local hostnames and local Core
  model ports are rejected. The DNS-pin and exact-origin network router are
  checked at preview *and again at execution*. Cross-origin redirects and
  non-GET requests are blocked by the existing isolated Chromium worker.
- The browser uses an ephemeral profile: no personal browser cookies, private
  account sessions, credentials, local DB mounts or arbitrary JavaScript tool.
  Returned page text/links are untrusted evidence, not instructions. Source
  links are only rendered as plain HTTPS anchors after validation, with
  `noopener noreferrer`.
- New tools do not silently authorize `system.terminal` or unrestricted
  browser interaction. This is not a substitute for exact account-login flows.

## Acceptance

Run the complete Python/Node regression suites and governance checks. Focused:

```bash
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests -p 'test_chat_public_web.py' -v
node --test apps/core/tests/test_computer_ui.cjs
```

Owner browser acceptance **after reviewed deployment**, with explicit tool
grants: search one public topic and open a public HTTPS page; verify a visible
source/receipt from actual Chromium. Repeat offline or with denied origin,
then revoke the tool and confirm the action cannot execute. Confirm no new
network call when the tool is not granted. Real Google results, CAPTCHAs or
consent redirects may vary by location/browser and must be reported honestly.

## Remaining work

A follow-up can synthesize a bounded, cited answer from verified search
sources (never from search snippets alone), and allow user-confirmed research
on more than one site. Existing private/core application credentials remain
isolated. Terminal changes, personal browser sessions, voice and non-read
browser workflows are separate scoped tasks. Memory #128 remains open.
