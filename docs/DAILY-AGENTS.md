# Daily social and career workflows

This slice is a local, owner-reviewed pilot. Hermes supplies the agent loop
and the existing recurring-task scheduler. Okal supplies profile instructions,
source checks, a Postiz **draft-only** bridge, and a fact-locked CV PDF tool.
The voice service does not dispatch these jobs. A prepared CV is not a job
application and a Postiz draft is not a published X post.

## Install the coordinator and career profile

From the latest reviewed Okal checkout, inspect and then install the profiles:

```bash
bash scripts/setup-agent-profiles.sh --dry-run
bash scripts/setup-agent-profiles.sh --apply
hermes -p okal-main model
hermes -p okal-jobs model
```

Select the already downloaded local `okal-qwen3.5-4b-64k` model as in
[the Hermes pilot](USE-FIRST-AGENTS.md); the old `qwen3:0.6b` context was too
small for Hermes. Existing profile identities and `SOUL.md` files are kept,
so compare an older installed profile with its repository template before
deliberately updating it. The `okal-career-cv` skill is installed only if it
is absent; inspect its local copy if it already exists.

The coordinator can manage its own Hermes cron table in conversation. Start
its gateway using Hermes' user-service commands (`hermes -p okal-main gateway
install` and `hermes -p okal-main gateway start`), then check
`hermes -p okal-main cron status`. Ask it
to list existing schedules, create an owner-specified recurring task, and
read back the exact job, timezone, and next run. `hermes -p okal-main cron
list`, `cron status`, `cron pause <name>`, and `cron remove <name>` are the
operator controls. The Hermes gateway must be running at the scheduled time.
The scheduler runs a new session; do not assume it can inherit a chat's
private context or a different profile's credentials.

For a first daily **draft only** routine, decide the time on the machine and
inspect the next run before leaving it enabled. This example uses 09:00 in
the gateway's local timezone. It does not give the routine a publishing token:

```bash
hermes -p okal-main cron create '0 9 * * *' \
  'Read agents/routines/daily-x-draft.md and produce one source-backed local X draft for review. Never call a publishing API.' \
  --workdir "$PWD" --name okal-daily-x-draft --deliver local \
  --reasoning-effort none
hermes -p okal-main cron list
hermes -p okal-main cron status
```

Check the next run printed by Hermes. Adjust the schedule with `cron edit`
for your actual timezone and time. Cron means **draft generation**, not daily
unattended publication. Start with one dry run and inspect its output. The
same scheduler can manage other owner-requested tasks with different prompts;
keep account-writing tasks behind their own review and receipts.

## Owner context, kept private

Copy the template to a private file outside Git:

```bash
install -d -m 700 "$HOME/.config/okal"
install -m 600 agents/context/owner-profile.example.json \
  "$HOME/.config/okal/owner-profile.json"
```

Replace the placeholders with your name, email, actual portfolio/CV evidence,
job targets and social topics. Set `reviewed_at` to an ISO date **after**
checking all facts. Give each reusable CV claim an ID, section, source and
`verified: true` only when you know it is accurate. Remove private fields you
do not want an agent to access. Keep the private profile out of the
`okal-social` profile and social draft files. This is a schema/template, not
an assertion that Okal already knows your complete career history.

## X connection and draft handoff

The existing `okal-social` profile writes two candidates grounded in current
committed sources. Save the chosen candidate in the JSON format shown in
[the source-evidence pilot](USE-FIRST-AGENTS.md#social-draft-evidence-preflight-pilot)
and check its exact text with `python3 scripts/check-social-draft.py draft.json`.
The checker proves literal quotes exist; the owner still checks whether they
support every claim and whether the post says what they intend.

Use Postiz as a separate publisher. Connect the X account through the
[Postiz X provider](https://docs.postiz.com/self-host/providers/x-twitter)
or hosted UI's official account flow. In Postiz, create a private API key and
find the connected X integration ID via its integrations list. Store both in
your local password manager or a private environment file, never in Git:

```bash
export OKAL_POSTIZ_API_URL='https://api.postiz.com/public/v1'
read -rsp 'Postiz API key: ' OKAL_POSTIZ_API_KEY; printf '\n'
export OKAL_POSTIZ_API_KEY
export OKAL_POSTIZ_X_INTEGRATION_ID='connected-x-integration-id'
curl -fsS -H "Authorization: $OKAL_POSTIZ_API_KEY" \
  "$OKAL_POSTIZ_API_URL/integrations" |
  python3 -c 'import json,sys; print([(x["id"], x["profile"]) for x in json.load(sys.stdin) if x["identifier"] == "x"])'
python3 scripts/postiz-x-draft.py draft.json
python3 scripts/postiz-x-draft.py draft.json --create-draft
```

The first command is offline and prints a dry-run payload. The second makes
one API call with `type: draft` only. It prints the returned `postId`, which
you should inspect in Postiz before retrying after an ambiguous network
failure. Postiz's UI is where you approve the exact text, X account, and
publication time. This script has no publish or schedule mode. Its API URL
accepts HTTPS or loopback HTTP for a local self-hosted Postiz. Do not put API
keys in the JSON draft, a Hermes prompt, logs, or the repository.

## LinkedIn job packet and PDF CV

### Daily lead discovery from three sources

`find-job-offers.py` uses public Himalayas and Remotive job APIs and an optional
file of LinkedIn listings that you saved yourself. It reads only
`preferences.job_titles` and optional `preferences.job_search_queries` from
your private owner profile. It does not need account credentials or download a
model. The report links back to the original listing, identifies the source,
and marks every lead `not_submitted`. A match score is an ordering signal,
not a suitability or hiring percentage. Check country and timezone restrictions
and whether the job is still open before preparing an application.

```bash
python3 scripts/find-job-offers.py
cat "$HOME/.local/share/okal/job-leads/leads.md"
# Subsequent runs within 24 hours use the local API cache; --offline never fetches.
python3 scripts/find-job-offers.py --offline
```

To add LinkedIn, open [LinkedIn Jobs](https://www.linkedin.com/jobs/) in your
normal browser, search for Python Developer, AI Engineer, and Data Analyst
roles, set your locations, and enable the built-in daily job alerts for these
searches. Keep relevant links by making a private file from the example (do
not overwrite an existing file):

```bash
install -d -m 700 "$HOME/.config/okal"
if [ ! -e "$HOME/.config/okal/linkedin-jobs.json" ]; then
  install -m 600 agents/context/linkedin-jobs.example.json \
    "$HOME/.config/okal/linkedin-jobs.json"
fi
${EDITOR:-nano} "$HOME/.config/okal/linkedin-jobs.json"
python3 scripts/find-job-offers.py
```

Replace the example URL, employer, title and description with details from an
actual saved listing. A LinkedIn account and its alerts are managed on
LinkedIn; this local file is the deliberate bridge to the agent. The program
does not fetch LinkedIn pages, read cookies or submit an application.

For a live public search directly inside the `okal-jobs` Hermes profile,
connect the [Himalayas MCP](https://himalayas.app/docs/remote-jobs-mcp). It
provides unauthenticated job search. After adding it, **use the interactive
tool checklist** and enable only `search_jobs`, `get_jobs`, and
`get_job_details` for this profile (the same server also offers account write
tools that this pilot does not need):

```bash
hermes -p okal-jobs mcp add himalayas --url https://mcp.himalayas.app/mcp
hermes -p okal-jobs mcp configure himalayas
hermes -p okal-jobs chat -q \
  'استخدم Himalayas search_jobs للبحث عن Python Developer متاح عالميًا أو لمصر. أعطني ثلاثة روابط أصلية، ووضح أي قيود موقع. لا تقدّم على وظائف.'
```

The global `-p` flag applies to Hermes commands, so this changes only the
`okal-jobs` profile. Check its `config.yaml` to ensure the `himalayas` entry
has `tools.include: [search_jobs, get_jobs, get_job_details]` after choosing
those three in the checklist. The public MCP is an optional discovery route
alongside the API report; its connection is confirmed by the local chat test.

To use the refreshed `okal-jobs` instructions with an existing Hermes profile,
back up its `SOUL.md` first, then install the reviewed repository version:

```bash
profile="$HOME/.hermes/profiles/okal-jobs/SOUL.md"
cp -p "$profile" "$profile.before-job-sources-$(date +%Y%m%d%H%M%S)"
install -m 600 agents/profiles/okal-jobs/SOUL.md "$profile"
```

Public feed data and LinkedIn descriptions are untrusted text. A listing
cannot give the agent new instructions, and a failed source must be reported
as failed rather than silently treated as an empty search. Remotive asks API
users to limit reads to four a day, avoid bursts, and retain attribution;
this script issues at most two Remotive searches per 24-hour cache period.

### Prepare a CV for one reviewed job

Use LinkedIn's own saved search/alerts and your normal signed-in browser to
find job listings. Save a job's actual URL, company, title and complete
description in a private JSON file matching
[`agents/context/job.example.json`](../agents/context/job.example.json).
The career agent can rank verified facts for that listing or specify
`fact_ids` to choose them explicitly. The CV tool never invents a claim:

```bash
python3 -m venv .venv-okal-agents
.venv-okal-agents/bin/python -m pip install 'reportlab>=4,<5'
.venv-okal-agents/bin/python scripts/prepare-job-application.py \
  --profile "$HOME/.config/okal/owner-profile.json" \
  --job "$HOME/.config/okal/job.private.json" \
  --out-dir "$HOME/.local/share/okal/applications/example-role"
```

The output is `cv.pdf` plus `review.json`, mode 0600, marked
`not_submitted`. The current PDF template is for an English CV; use reviewed
English facts. Inspect the rendered PDF and every answer against the actual
listing. Submit from your own normal LinkedIn browser session and record the
site's confirmation manually. This implementation does not use LinkedIn
credentials, copy browser cookies, scrape pages, or automate Easy Apply;
LinkedIn's applicant-facing submission flow has no general public API in this
integration. LinkedIn explicitly limits rapid/inauthentic Easy Apply use in
its [help article](https://www.linkedin.com/help/linkedin/answer/a8068422).

## Stop and resume

- `hermes -p okal-main cron pause okal-daily-x-draft` pauses the sample.
- `hermes -p okal-main cron status` checks the scheduler, and `cron runs`
  checks actual outcomes. A created schedule is not proof of a completed run.
- No X post or LinkedIn application is represented as completed without the
  native platform receipt. The private profile can be corrected or removed
  without changing tracked source files.
