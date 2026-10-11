# Freelance proposal pilot: Mostaql first

This pilot runs on the owner's laptop and uses a **separate Chromium browser
profile** for Mostaql. The same profile can hold manual sign-ins for Khamsat
and Freelancer, though project scanning and submission are implemented only
for Mostaql. Sign in yourself once. The script does not handle
passwords, copy Firefox cookies, bypass CAPTCHA, send messages, or follow up.
It does not run unattended. Khamsat has a different selling flow; Freelancer
has different bid fields and limits. Neither is connected in this pilot.

## Set up once

From a clean checkout on `main` after the pilot PR is merged:

```bash
cd ~/Projects/okal
python3 -m venv .venv-okal-freelance
.venv-okal-freelance/bin/python -m pip install playwright
# If Chromium is already installed, avoid downloading another browser:
command -v chromium || command -v chromium-browser || true
export OKAL_FREELANCE_CHROMIUM="$(command -v chromium || command -v chromium-browser)"
# If neither command found Chromium, instead run:
# unset OKAL_FREELANCE_CHROMIUM
# .venv-okal-freelance/bin/python -m playwright install chromium
mkdir -p -m 700 "$HOME/.local/share/okal/freelance"
install -m 600 agents/freelance-profile.example.json "$HOME/.local/share/okal/freelance/profile.json"
```

Edit `~/.local/share/okal/freelance/profile.json` privately. Replace TODO
values with services you really deliver, a relevant genuine work sample or
portfolio URL, and two or three examples of proposals you actually like.
Set your real minimum price and delivery days. This file and the browser
login stay outside Git. The matching is a rough keyword filter, so reject
irrelevant projects yourself. Keep the laptop's Ollama service running with
the already cached `okal-qwen3.5-4b-64k` model; no new model download.
To create a separate Hermes identity for later style conversations, run
`bash scripts/setup-freelance-agent.sh --dry-run` and then `--apply`.
Choose the existing Ollama model with `hermes -p okal-freelance model`.
The pilot script does not give Hermes direct access to the account; all
submissions go through the reviewed local browser flow below.

## Sign in to the dedicated browser

From the same checkout and virtual environment used above:

```bash
.venv-okal-freelance/bin/python scripts/freelance-mostaql.py accounts
# Later, if you need another site: accounts --site khamsat
# Or: accounts --site freelancer
```

This opens **Mostaql only** in one visible browser. Complete
login and any CAPTCHA yourself, then press Enter in the terminal to
close the browser cleanly. Cookies and other browser data are stored locally
at `~/.local/share/okal/freelance/browser/`. Later `scan` and `apply`
reopen this exact directory. You do **not** need to copy browser profile
files into the repository or into Hermes. Close the browser before another
command uses the profile; the script refuses concurrent access. If you later
use another local AI process, configure it to use this same directory only
when this pilot browser is closed. The directory contains account sessions:
keep it private and out of Git or shared archives. Visible browser operation
does not guarantee a platform will treat automation as human activity.
The browser now uses the actual resizable window size instead of a fixed
1280x720 page viewport. In a tiling desktop, maximize the window with your
desktop shortcut if needed. The profile can hold multiple accounts, but open
and sign in to **one platform at a time**. If Hsoub displays its login attempt
limit, stop retrying and wait for the site to allow another attempt; no
browser setting or automation should try to evade that limit. Google Search's
unusual traffic page concerns Google/network traffic and does not on its own
establish that Mostaql blocked the account. Do not run automated Google searches.

## First application

The first `scan` creates the private per-site configuration
`~/.local/share/okal/freelance/sites/mostaql.json` with this listing:

```json
{
  "projects_url": "https://mostaql.com/projects?category=development,ai-machine-learning,support&sort=latest"
}
```

You can change the filters in that file later. The pilot checks that the URL
is an HTTPS Mostaql `/projects` page before opening it. This configuration
only selects the listing; the private profile's services and exclusions still
filter individual projects. Other platforms can get their own site files when
their distinct discovery and application flows are implemented. Account sign-in
for Khamsat and Freelancer does not enable their submission flows.

```bash
py=.venv-okal-freelance/bin/python
"$py" scripts/freelance-mostaql.py scan --limit 5
# In the dedicated Chromium window, sign in to Mostaql yourself, then Enter.
# Alternatively add a project URL you picked in the browser:
# "$py" scripts/freelance-mostaql.py add 'https://mostaql.com/project/123456-example'
cat "$HOME/.local/share/okal/freelance/queue.json"
"$py" scripts/freelance-mostaql.py draft PROJECT_ID
```

Edit `~/.local/share/okal/freelance/drafts/PROJECT_ID.json`: verify the
project requirements, every claim, the exact proposal, price and duration.
Set `"reviewed": true` only after you finish. First try filling the form
without submitting:

```bash
"$py" scripts/freelance-mostaql.py apply PROJECT_ID
"$py" scripts/freelance-mostaql.py apply PROJECT_ID --submit
```

The second command asks you to type the project ID, then clicks a unique
Mostaql submit button. It records an **attempt** before clicking, to avoid
retrying an uncertain submission. Check the project/account page for the
actual submitted proposal. If the site form changed, the script stops; fill
that proposal manually and report the field names/labels so the adapter can
be updated. A failure, CAPTCHA, or login prompt is not a successful bid.
The pilot waits for the visible project links and form fields to load, then
stops if they are missing or login redirects away from the project. It does
not repeat login attempts or submission clicks automatically.
The `history.json` and drafts contain private project and proposal data.
Do not share them or commit them to Git. Subsequent buyer messages and
follow-up are entirely manual.

## Pilot acceptance

One real Mostaql project matching the private profile is found, one draft is
edited and reviewed, the browser form is filled, a bid is deliberately
submitted, and the owner can see that exact bid in their Mostaql account.
An attempt log alone does not establish success. Only then adapt the workflow
to other platform forms or consider more autonomous batches.
