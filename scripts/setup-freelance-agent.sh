#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
profile_dir="$HOME/.hermes/profiles/okal-freelance"
target="$profile_dir/SOUL.md"

if [[ "${1:---dry-run}" == "--dry-run" && $# -le 1 ]]; then
  echo "Would create the isolated okal-freelance Hermes profile and install $target if absent."
  echo "Local proposal data stays at $HOME/.local/share/okal/freelance."
  exit 0
fi
if [[ "${1:-}" != "--apply" || $# -ne 1 ]]; then
  echo "Usage: bash scripts/setup-freelance-agent.sh [--dry-run|--apply]" >&2
  exit 2
fi
command -v hermes >/dev/null || { echo "Install Hermes first; see docs/USE-FIRST-AGENTS.md" >&2; exit 1; }
if [[ -e "$target" ]]; then
  echo "Keeping existing profile: $target"
  exit 0
fi
if [[ ! -d "$profile_dir" ]]; then
  hermes profile create okal-freelance
fi
if [[ -e "$target" ]]; then
  cp -p "$target" "$target.before-okal"
fi
install -m 600 "$root/agents/profiles/okal-freelance/SOUL.md" "$target"
echo "Installed $target. Select the already cached local model with: hermes -p okal-freelance model"
