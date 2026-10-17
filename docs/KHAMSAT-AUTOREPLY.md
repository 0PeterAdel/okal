# Local Khamsat response pilot

This extends [the request scout](KHAMSAT-REQUEST-SCOUT.md). The agent uses the owner's saved local browser session, checks new community requests, writes a short answer grounded in verified facts from the private owner profile and the particular request, then can **click the actual reply button**. On Khamsat community requests this is a public reply to a request, not a formal order or an accepted project. It never solves CAPTCHAs or attempts to hide automation. Keep your laptop session signed in and running.

## Local control page

Set up the Playwright environment on your laptop, then open the page in your regular browser:

```sh
cd ~/Projects/okal
bash scripts/setup-khamsat-browser.sh --check
bash scripts/setup-khamsat-browser.sh --apply
.venv-okal-freelance/bin/python scripts/khamsat-request-scout.py --init
.venv-okal-freelance/bin/python scripts/khamsat-control.py
# open http://127.0.0.1:8788/ on this computer
```

The setup script reuses an existing Playwright environment under `~/Projects` if it finds one, without downloading a browser. Otherwise, `--apply` creates a local environment and installs only the Python package; a Chromium download is a separate step if the subsequent scan reports a missing browser.

If the Python package is present but Playwright's expected Chromium revision was removed, the scout tries a system Chromium/Chrome or an existing cached Chromium binary before asking you to download anything. An explicit `OKAL_FREELANCE_CHROMIUM=/absolute/path/to/chromium` overrides discovery for a local terminal test. If none is available, use `.venv-okal-freelance/bin/python -m playwright install chromium` once; cached login/profile data is separate from the browser executable. Browser startup errors are shown in the control page instead of returning an empty HTTP response.

The server binds only to `127.0.0.1:8788`, validates the browser origin and a form token, and keeps all settings, queue entries and receipts in private 0600 files. It does not expose the saved Khamsat browser profile. The page now supports **Review needed** only. Older saved `authorization=auto`/`enabled=true` values are ignored for writes, and the timer can only scan. It reads sourced work facts marked `verified: true` from `~/.config/okal/owner-profile.json` (0600), without passing identity or contact fields to the model. The agent infers which facts fit each request; a separate service or proof field is not required. The public HTTPS portfolio link is optional. Set service keywords and exclusions and edit the Egyptian Arabic writing instructions, which are sent as the local model's `system` instruction rather than copied as a proposal template. The reply field and submit button are prefilled from the owner's inspected Khamsat HTML, including when older saved settings contain empty selectors. Click **Scan now**, inspect a queued request and generate a draft. Editing a draft and clicking **review request and text** opens a separate confirmation showing the original link and the exact text; this first click cannot post. Only ticking the confirmation checkbox and clicking **confirm publication** sends that one reply. The one-use confirmation expires after ten minutes or a server restart. A pending receipt can mean the click succeeded and verification did not; inspect the site before doing anything else.

**Scanning and drafting:** The scan visits `https://khamsat.com/community/requests`, clicks the visible `#community_loadmore_btn` twice by default (waiting for each batch and one second before the second click), and reads `#forums_table tr.forum_post` titles, publishers, times and validated request URLs. Its local Ollama model shortlists at most 10 new or legacy candidates against your configured fields and sourced work facts. It then visits each shortlisted request, reads its heading, article and comment-count heading, and runs a second fit check using the full description. Items whose details cannot be extracted are listed as scan errors rather than queued with invented text. The scanner never sends a comment. You can set 0–5 load-more clicks and 1–20 candidate pages per scan on the control page. The model cannot add an ID or URL that was absent from the listing, and changed keywords or exclusion terms are checked again before preview or submission. If the model fails, the scan reports a failure instead of silently falling back to title substring matching.

The request detail page can finish rendering after navigation, and the `div` positions in its XPath may vary. The scanner waits for a heading and article, tries the inspected XPath first, then a visible heading/article fallback. If extraction still fails, the control page shows the shortlisted title, original link and which field was missing, along with `h1` and `article` counts. Such a request remains unavailable for drafting until its actual description can be read; signed-out or visible CAPTCHA pages need manual attention.

**Optional comment context:** Tick the checkbox and choose 1–10 recent comments per request (default 3). Comments are read from the inspected public comment container; a missing container is reported with the request and supplies no comments to the model. The drafts may use these comments to understand what competing answers overlook, but must not copy them or claim their authors' work. Description, titles, comments and past drafts are untrusted data in the `prompt`, while your writing instructions and the safeguards are in `system`. Comment context never authorizes a submission.

In Review needed mode, tick up to 10 queued requests and choose **prepare selected drafts**. A background worker prepares them one at a time; use **refresh progress** on the page to see the latest state. The page does not reload automatically, so text you are editing stays in place. Each draft is stored locally and remains separately editable; the batch action cannot submit any reply. You can still prepare a single draft as before. The browser/profile and owner settings stay on your laptop; no external model or API is used.

Autonomous submission is disabled, including when an older private settings file still says `auto`. The daily cap applies to manually confirmed replies. The written instructions are included as a bounded context to the local model; the request content itself remains untrusted data.

To keep checking while your desktop session is running, install the user timer after this branch is available in `~/Projects/okal`:

```sh
install -Dm644 systemd/user/okal-khamsat-agent.service ~/.config/systemd/user/okal-khamsat-agent.service
install -Dm644 systemd/user/okal-khamsat-agent.timer ~/.config/systemd/user/okal-khamsat-agent.timer
systemctl --user daemon-reload
systemctl --user enable --now okal-khamsat-agent.timer
systemctl --user list-timers okal-khamsat-agent.timer
```

The timer wakes every five minutes and reads the refresh interval configured on the page (5–1440 minutes); it scans only when due and **never submits**. Turn it off with `systemctl --user disable --now okal-khamsat-agent.timer`. After any unexpected send from an older installation, stop the timer before testing the new branch, inspect that request and the private `replies.json` receipt, and do not retry a pending request. A computer that is asleep or powered off cannot scan. Since the service file uses `~/Projects/okal`, copy or pull the reviewed branch there before installing the timer.

First run the scout `--init` and `--scan` on your laptop, and verify its queue contains recent requests matching your work. Pick one link from `--list` and run:

```sh
.venv-okal-freelance/bin/python scripts/khamsat-request-reply.py --inspect 'https://khamsat.com/community/requests/123456-title'
```

The preview does not require a reply-settings file or a portfolio link. It requires the private owner profile with at least one sourced, verified work fact; if missing, the page explains which profile to review and hides preview. The default template asks for a concise, warm, specific reply and a practical first step, with no invented experience, project, timeline, price or outside-platform contact. Save changes on the control page to create `~/.config/okal/khamsat-reply.json` (0600). A model-produced reply still needs human review before the first live send. The runner accepts nonempty replies up to the inspected textarea's `maxlength=2000`; it does not impose a minimum length. A longer reply or an unapproved link remains an editable private draft with a reason, and the submit path independently rejects it until corrected. Empty model output or output above 4000 characters is rejected without a draft.

When you edit a draft and the site visibly confirms its submission, Okal privately saves the original and your final wording in `~/.local/share/okal/khamsat/style-memory.json` (0600). The next drafts use up to three recent before/after examples to follow your phrasing and structure, while only the verified owner profile supplies claims about your work. This is local few-shot style guidance, not training model weights. At most five examples are kept. No edit is learned from an unsent, unverified, unchanged or failed reply. If saving style memory fails after a confirmed post, the page reports that separately and retains the submitted receipt; it does not suggest reposting.

For the local Qwen thinking model, draft generation requests `think: false` and allows up to 700 generated tokens so the response budget goes to the public reply rather than reasoning. Ollama is already managed by its existing service on the owner's laptop. A `bind: address already in use` error from a separate `ollama serve` means the port is occupied; check `ollama list` and the running service instead of starting another server. No model download is required for this adjustment.

The owner's inspected request form has a `textarea[name="content"]`, a `#confirm` checkbox for Khamsat's comment terms, and `#commentable_submit`. Only after the separate Okal confirmation does the runner locate the unique textarea (with the inspected XPath and name fallback if needed), check the terms box, fill it through Playwright, dispatch `change`, wait 500 ms and verify the exact field value, checkbox, and visible enabled submit button. A styled form may hide the native checkbox behind a visible label or activate the button only after consent; the runner checks these states after clicking the terms rather than rejecting the form beforehand. It then records the pending attempt before clicking. The delay or Khamsat's checkbox never substitutes for the owner's separate Okal confirmation. Do not include outside contact information or text violating the site's terms. A visible site validation error is reported in the local control page, with the receipt left pending until you inspect the request on Khamsat. Do not retry a pending request automatically.

For multiline drafts, the control page normalizes HTML form `CRLF` line endings to the textarea DOM's `LF` before showing the separate confirmation. The runner checks the terms first, then fills and verifies the reviewed text. If the site changes the value, it stops without a receipt or click and reports only the expected and actual text lengths, not the private draft itself. Reloading an old `/confirm-submit` URL after restarting the control server returns 404 because confirmation tokens are kept only in memory; start a fresh review from `/`.

After a click, verification waits for the request's comment area to render and compares one complete comment body after normalizing layout whitespace. A pending receipt still blocks any repeat if the site does not expose a matching comment within the wait period. If you independently see your published reply on the same request, stop the control server and reconcile only that pending local receipt, without reposting:

```sh
.venv-okal-freelance/bin/python scripts/khamsat-request-reply.py \
  --acknowledge-posted 'https://khamsat.com/community/requests/123456-title'
```

The command prints the recorded request URL and requires you to type its numeric ID after inspecting the published comment yourself. It updates only `replies.json` from `pending` to `submitted`, records `verified_by=owner`, and does not open the browser or send anything to Khamsat. It rejects other statuses and request IDs. Do not use this command if the comment is not visible on Khamsat.

The form can render after the request page reaches `domcontentloaded`. The runner waits up to 12 seconds for a visible textarea in a form, checks the configured selector, the inspected XPath, `textarea[name='content']`, and `form textarea`, and accepts only one visible enabled field whose own form also contains the terms checkbox and submit button. If every candidate selector is absent, it verifies the request ID, reloads once, waits again and verifies the ID before any write. A second failure reports the sanitized page URL, request match and structural counts from the actual submission page; it records no send attempt. Re-open the request in the saved browser session and inspect it manually if the error persists. No JavaScript `prompt()` or site-side delayed click bypasses the Okal confirmation step.

If every selector count is zero, the HTML seen by your regular browser and the saved Okal browser profile may differ. With the control page stopped to release the browser-profile lock, run `.venv-okal-freelance/bin/python scripts/khamsat-request-reply.py --diagnose 'https://khamsat.com/community/requests/123456-title'` on the affected request. This opens the same visible saved profile used by the runner, prints only structural counts, a query-free page URL and a same-request flag, then waits for you to inspect or sign in manually before collecting a second snapshot. It never fills or submits a reply. If the form remains absent, check whether that particular request still permits comments in this account; never reuse a textarea observed in a different browser session or a different request.

An older draft may contain a saved warning from an earlier version of the length rule. The page now checks the draft against the current rule when displaying it, so a 1283-character reply no longer shows the old 1000-character warning. Before submitting, the runner validates that the browser remains on the same numeric request ID; the listing link and page heading do not have to be identical.

Example private settings:

```json
{
  "authorization": "review",
  "enabled": false,
  "proposal_instructions": "اكتب بالمصري المهني الودود، واربط عرضك بهذا الطلب باستخدام حقائق عملي الموثقة فقط",
  "scan_interval_minutes": 30,
  "portfolio_url": "",
  "reply_selector": "textarea[name='content'].c-form__control",
  "submit_selector": "button#commentable_submit[type='submit']",
  "max_per_day": 2,
  "ollama_model": "okal-qwen3.5-4b-64k"
}
```

The existing private `khamsat-watch.json` controls allowed and excluded keywords. Do not put client information or a secret in the model prompt. Preview one candidate without writing:

```sh
.venv-okal-freelance/bin/python scripts/khamsat-request-reply.py --respond-once 'REQUEST_URL' --dry-run
```

Inspect the result and live form. Use the control page for reviewed submission; setting `enabled=true` alone does not authorize background submission. Verify your answer in Khamsat and in `~/.local/share/okal/khamsat/replies.json`. A `pending` receipt means the click may have happened but verification failed: inspect the site before any manual retry. Every request ID is attempted at most once, with a configurable daily limit of 1–5. The agent only processes queue entries found in the past 48 hours. Keep the 0600 browser profile and settings out of Git.

The visible browser may open at the configured interval. If Khamsat changes the form, has a CAPTCHA, or shows a login page, the runner stops for manual inspection. No humanizing or account-evasion mechanism is used.
