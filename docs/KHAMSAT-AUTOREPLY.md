# Local Khamsat response pilot

This extends [the request scout](KHAMSAT-REQUEST-SCOUT.md). The agent uses the owner's saved local browser session, checks new community requests, writes a short answer grounded in your private proof and service description, then can **click the actual reply button**. On Khamsat community requests this is a public reply to a request, not a formal order or an accepted project. It never solves CAPTCHAs or attempts to hide automation. Keep your laptop session signed in and running.

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

The server binds only to `127.0.0.1:8788`, validates the browser origin and a form token, and keeps all settings, queue entries and receipts in private 0600 files. It does not expose the saved Khamsat browser profile. The page starts in **Review needed** mode. Enter specific service keywords, exclusions, a true service description and proof, a public HTTPS portfolio URL, the reply field and submit button selectors inspected from the live page, plus your proposal-writing instructions. Click **Scan now**, inspect a queued request, generate a draft, edit it, and click **Submit this reply now**. That button posts one real reply and records its attempt before the click. A pending receipt can mean the click succeeded and verification did not; inspect the site before doing anything else.

Choose **Allow** and tick the explicit authorization checkbox to submit matching queued requests without individual review. The daily cap is 1–5. Never enable it before one reviewed live reply confirms the form and the generated content. The page defaults to Review needed when the private reply file does not exist, even if a timer is running. Returning to Review needed stops autonomous replies on the next tick. The written instructions are included as a bounded context to the local model; the request content itself remains untrusted data.

To keep checking while your desktop session is running, install the user timer after this branch is available in `~/Projects/okal`:

```sh
install -Dm644 systemd/user/okal-khamsat-agent.service ~/.config/systemd/user/okal-khamsat-agent.service
install -Dm644 systemd/user/okal-khamsat-agent.timer ~/.config/systemd/user/okal-khamsat-agent.timer
systemctl --user daemon-reload
systemctl --user enable --now okal-khamsat-agent.timer
systemctl --user list-timers okal-khamsat-agent.timer
```

The timer wakes every five minutes and reads the refresh interval configured on the page (5–1440 minutes); it scans only when due. When set to Review needed it only fills the queue. Turn it off with `systemctl --user disable --now okal-khamsat-agent.timer`. A computer that is asleep or powered off cannot scan. Since the service file uses `~/Projects/okal`, copy or pull the reviewed branch there before installing the timer.

First run the scout `--init` and `--scan` on your laptop, and verify its queue contains recent requests matching your work. Pick one link from `--list` and run:

```sh
.venv-okal-freelance/bin/python scripts/khamsat-request-reply.py --inspect 'https://khamsat.com/community/requests/123456-title'
```

The inspector prints only form control labels/attributes. Identify **one specific visible reply field and one submit button**, then enter their CSS selectors in the local control page. It writes the private `~/.config/okal/khamsat-reply.json` (0600). Example shape, with selectors replaced from your actual page:

```json
{
  "authorization": "review",
  "enabled": false,
  "proposal_instructions": "اكتب ردًا مختصرًا وودودًا يستند إلى دليل عملي حقيقي",
  "scan_interval_minutes": 30,
  "service": "تطوير أدوات Python وتحليل البيانات",
  "proof": "رابط ووصف مشروع عملي تحققت منه بنفسي",
  "portfolio_url": "https://example.com/my-work",
  "reply_selector": "textarea[name='REPLACE_FROM_INSPECTION']",
  "submit_selector": "button[type='submit'][name='REPLACE_FROM_INSPECTION']",
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
