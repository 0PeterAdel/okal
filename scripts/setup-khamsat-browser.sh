#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="$root/.venv-okal-freelance"

if [[ "${1:---check}" != "--check" && "${1:-}" != "--apply" ]] || (( $# > 1 )); then
  echo "Usage: bash scripts/setup-khamsat-browser.sh [--check|--apply]" >&2
  exit 2
fi

if [[ -x "$target/bin/python" ]]; then
  if "$target/bin/python" -c 'import playwright.sync_api' 2>/dev/null; then
    echo "Playwright ready: $target/bin/python"
    exit 0
  fi
  echo "Environment exists but Playwright is missing: $target" >&2
  if [[ "${1:---check}" == "--check" ]]; then exit 1; fi
fi

existing=""
if [[ -d "$HOME/Projects" ]]; then
  while IFS= read -r candidate; do
    [[ "$candidate" == "$target/bin/python" ]] && continue
    if "$candidate" -c 'import playwright.sync_api' 2>/dev/null; then
      existing="${candidate%/bin/python}"
      break
    fi
  done < <(find "$HOME/Projects" -maxdepth 5 -path '*/.venv-okal-freelance/bin/python' -print 2>/dev/null)
fi

if [[ -n "$existing" ]]; then
  if [[ "${1:---check}" == "--check" ]]; then
    echo "Reusable Playwright environment: $existing"
    echo "Run: bash scripts/setup-khamsat-browser.sh --apply"
  elif [[ ! -e "$target" && ! -L "$target" ]]; then
    ln -s "$existing" "$target"
    echo "Linked existing environment (no download): $target -> $existing"
  else
    echo "Cannot link: $target already exists. Inspect it before replacing anything." >&2
    exit 1
  fi
  exit 0
fi

if [[ "${1:---check}" == "--check" ]]; then
  echo "No reusable Playwright environment found. --apply creates a Python environment and installs Playwright."
  echo "A browser download is never started by this script."
  exit 1
fi

if [[ ! -x "$target/bin/python" ]]; then
  python3 -m venv "$target"
fi
"$target/bin/python" -m pip install playwright
echo "Playwright installed: $target/bin/python"
echo "Browser binaries were not downloaded. Try the control page; if Chromium is missing, run:"
echo "  $target/bin/python -m playwright install chromium"
