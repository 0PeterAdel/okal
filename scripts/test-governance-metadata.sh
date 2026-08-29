#!/usr/bin/env bash

set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

human_body=$'## What changed?\n\nTest metadata.\n\n## Why?\n\nProtect governance.\n\n## How to review?\n\nRun the test.\n\n## Related task\n\nCloses #5\n\n## Risk and security\n\nNo runtime impact.\n\n## Evidence\n\nRegression test.\n\n## Checklist\n\n- [x] Complete.'
dependabot_body=$'Bumps [actions/checkout](https://github.com/actions/checkout) from 4.4.0 to 7.0.1.\n\n<details>\n<summary>Release notes</summary>\nGenerated release details.\n</details>'

run_success() {
  local name="$1"
  shift
  local output
  output="$(mktemp)"

  if ! env "$@" bash scripts/validate-governance.sh >"$output" 2>&1; then
    echo "FAIL: $name should pass." >&2
    cat "$output" >&2
    rm -f "$output"
    return 1
  fi

  rm -f "$output"
  echo "PASS: $name"
}

run_failure() {
  local name="$1"
  local expected="$2"
  shift 2
  local output
  output="$(mktemp)"

  if env "$@" bash scripts/validate-governance.sh >"$output" 2>&1; then
    echo "FAIL: $name should fail." >&2
    rm -f "$output"
    return 1
  fi

  if ! grep -Fq "$expected" "$output"; then
    echo "FAIL: $name did not report the expected diagnostic: $expected" >&2
    cat "$output" >&2
    rm -f "$output"
    return 1
  fi

  rm -f "$output"
  echo "PASS: $name"
}

run_success \
  "handbook-compliant human metadata" \
  "OKAL_BRANCH_NAME=fix/test-governance-metadata" \
  "OKAL_PR_TITLE=fix: validate governance metadata" \
  "OKAL_PR_AUTHOR=0PeterAdel" \
  "OKAL_PR_BODY=$human_body" \
  "OKAL_REQUIRE_PR_BODY=1"

run_success \
  "authenticated Dependabot metadata" \
  "OKAL_BRANCH_NAME=dependabot/github_actions/actions/checkout-7.0.1" \
  "OKAL_PR_TITLE=build(deps): bump actions/checkout from 4.4.0 to 7.0.1" \
  "OKAL_PR_AUTHOR=dependabot[bot]" \
  "OKAL_PR_BODY=$dependabot_body" \
  "OKAL_REQUIRE_PR_BODY=1"

run_failure \
  "spoofed Dependabot branch" \
  "Branch 'dependabot/github_actions/actions/checkout-7.0.1'" \
  "OKAL_BRANCH_NAME=dependabot/github_actions/actions/checkout-7.0.1" \
  "OKAL_PR_TITLE=build(deps): bump actions/checkout from 4.4.0 to 7.0.1" \
  "OKAL_PR_AUTHOR=untrusted-user" \
  "OKAL_PR_BODY=$dependabot_body" \
  "OKAL_REQUIRE_PR_BODY=1"

run_failure \
  "malformed human metadata" \
  "Branch 'feature/BAD'" \
  "OKAL_BRANCH_NAME=feature/BAD" \
  "OKAL_PR_TITLE=fix(scope): malformed title" \
  "OKAL_PR_AUTHOR=0PeterAdel" \
  "OKAL_PR_BODY=Missing required headings." \
  "OKAL_REQUIRE_PR_BODY=1"

run_failure \
  "malformed authenticated Dependabot title" \
  "Trusted Dependabot PR title" \
  "OKAL_BRANCH_NAME=dependabot/github_actions/actions/checkout-7.0.1" \
  "OKAL_PR_TITLE=chore: update checkout" \
  "OKAL_PR_AUTHOR=dependabot[bot]" \
  "OKAL_PR_BODY=$dependabot_body" \
  "OKAL_REQUIRE_PR_BODY=1"

run_failure \
  "empty authenticated Dependabot body" \
  "Pull Request description is required." \
  "OKAL_BRANCH_NAME=dependabot/github_actions/actions/checkout-7.0.1" \
  "OKAL_PR_TITLE=build(deps): bump actions/checkout from 4.4.0 to 7.0.1" \
  "OKAL_PR_AUTHOR=dependabot[bot]" \
  "OKAL_PR_BODY=" \
  "OKAL_REQUIRE_PR_BODY=1"

echo "Governance metadata regression tests passed."
