---
name: okal-career-cv
description: Prepare an English CV PDF and review packet using only owner-verified facts for one specific job.
version: 1.0.0
---

# Tailored CV

Read the private profile from `~/.config/okal/owner-profile.json` only for a
career task. Do not copy it into the repository, a social prompt, or logs.
Gather the actual job URL, title, company, and full description in a local
job JSON file. The profile contains stable fact IDs, source references, and
owner verification flags. Choose relevant IDs based on the job requirements;
never rewrite those facts as new achievements.

From the Okal repository run:

```bash
.venv-okal-agents/bin/python scripts/prepare-job-application.py \
  --profile "$HOME/.config/okal/owner-profile.json" \
  --job /path/to/private/job.json \
  --out-dir /path/to/private/new-job-directory
```

The program creates `cv.pdf` and `review.json` with private permissions. Read
the review packet, show the owner the PDF and original listing, and ask them to
check all facts and answers. Never press Submit, automate LinkedIn Easy Apply,
or report that an application was submitted. The owner's native confirmation
on the job site is the receipt for an application.
