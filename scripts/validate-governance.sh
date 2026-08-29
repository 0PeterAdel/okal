#!/usr/bin/env bash

set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

failures=0
types='feat|fix|docs|style|refactor|test|chore|perf|ci|build|revert|security'
branch_pattern="^(${types})/([A-Z][A-Z0-9]+-[0-9]+-)?[a-z0-9]+(-[a-z0-9]+)*$"
commit_pattern="^(${types})(\([a-z0-9][a-z0-9-]*\))?: [a-z0-9].+"
pr_pattern="^(\[[A-Z][A-Z0-9]+-[0-9]+\] )?(${types}): [a-z0-9].+"
dependabot_branch_pattern='^dependabot/[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)+$'
dependabot_pr_pattern='^build\(deps(-dev)?\): (bump|update) .+'

report_failure() {
  echo "ERROR: $*" >&2
  failures=$((failures + 1))
}

trusted_dependabot=0
if [[ "${OKAL_PR_AUTHOR:-}" == "dependabot[bot]" ]] &&
  [[ "${OKAL_BRANCH_NAME:-}" =~ $dependabot_branch_pattern ]]; then
  trusted_dependabot=1
fi

if [[ -n "${OKAL_BRANCH_NAME:-}" ]] &&
  ((trusted_dependabot == 0)) &&
  [[ ! "$OKAL_BRANCH_NAME" =~ $branch_pattern ]]; then
  report_failure "Branch '$OKAL_BRANCH_NAME' must use type/short-task-name or type/JIRA-ID-short-task-name."
fi

if [[ -n "${OKAL_PR_TITLE:-}" ]]; then
  if ((trusted_dependabot == 1)); then
    if [[ ! "$OKAL_PR_TITLE" =~ $dependabot_pr_pattern ]]; then
      report_failure "Trusted Dependabot PR title '$OKAL_PR_TITLE' must describe a build(deps) bump or update."
    fi
  elif [[ ! "$OKAL_PR_TITLE" =~ $pr_pattern ]]; then
    report_failure "PR title '$OKAL_PR_TITLE' must use 'type: short description' or '[JIRA-ID] type: short description'."
  fi
fi

if [[ "${OKAL_REQUIRE_PR_BODY:-0}" == "1" ]]; then
  if [[ -z "${OKAL_PR_BODY:-}" ]]; then
    report_failure "Pull Request description is required."
  elif ((trusted_dependabot == 1)); then
    if [[ "$OKAL_PR_BODY" != *"Dependabot"* ]]; then
      report_failure "Trusted Dependabot Pull Request description is missing its generated attribution."
    fi
  else
    required_headings=(
      "## What changed?"
      "## Why?"
      "## How to review?"
      "## Related task"
      "## Risk and security"
      "## Evidence"
      "## Checklist"
    )
    for heading in "${required_headings[@]}"; do
      if ! grep -Fq "$heading" <<<"$OKAL_PR_BODY"; then
        report_failure "Pull Request description is missing '$heading'."
      fi
    done
  fi
fi

if [[ -n "${OKAL_BASE_SHA:-}" && -n "${OKAL_HEAD_SHA:-}" ]]; then
  while IFS= read -r subject; do
    [[ -z "$subject" ]] && continue
    if [[ ! "$subject" =~ $commit_pattern ]]; then
      report_failure "Commit message '$subject' must use type(scope): short message."
    fi
  done < <(git log --format='%s' "${OKAL_BASE_SHA}..${OKAL_HEAD_SHA}")
fi

required_files=(
  .editorconfig
  .gitattributes
  .gitignore
  .github/CODEOWNERS
  .github/PULL_REQUEST_TEMPLATE.md
  AGENTS.md
  CONTRIBUTING.md
  GOVERNANCE.md
  SECURITY.md
)
for required_file in "${required_files[@]}"; do
  [[ -f "$required_file" ]] || report_failure "Required governance file is missing: $required_file"
done

while IFS= read -r -d '' path; do
  base="$(basename "$path")"
  case "$base" in
    .env.example)
      ;;
    .env|.env.*|*.pem|*.key|*.p12|*.pfx|id_rsa|id_rsa.pub|*.dump|*.bak|*.sqlite|*.sqlite3|*.db)
      report_failure "Sensitive or local file must not be tracked: $path"
      ;;
  esac
done < <(git ls-files -z)

if git grep -I -q -E -- '-----BEGIN ([A-Z0-9]+ )?PRIVATE KEY-----|github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9]{20,}'; then
  report_failure "A potential credential or private-key marker is present in tracked content."
fi

if git grep -I -q -E -- '^(<<<<<<< |=======|>>>>>>> )'; then
  report_failure "Unresolved merge-conflict markers are present."
fi

if ! bash scripts/check-markdown-links.sh; then
  report_failure "Markdown link or fence validation failed."
fi

if ((failures > 0)); then
  echo "Governance validation failed with $failures error(s)." >&2
  exit 1
fi

echo "Governance validation passed."
