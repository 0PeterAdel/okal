#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: bash scripts/setup-agent-profiles.sh [--dry-run|--apply]" >&2
  exit 2
}

mode="${1:---dry-run}"
[[ $# -le 1 && ( "$mode" == "--dry-run" || "$mode" == "--apply" ) ]] || usage
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$mode" == "--apply" ]] && ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes is not installed. Follow docs/USE-FIRST-AGENTS.md first." >&2
  exit 1
fi

for role in okal-research okal-code okal-social; do
  profile_dir="$HOME/.hermes/profiles/$role"
  target="$profile_dir/SOUL.md"
  source_file="$root/agents/profiles/$role/SOUL.md"
  if [[ -d "$profile_dir" && -e "$target" ]]; then
    echo "Keep existing profile identity: $target"
    continue
  fi
  if [[ "$mode" == "--dry-run" ]]; then
    echo "Would create Hermes profile $role if absent, then copy $source_file to $target"
    continue
  fi
  # Hermes owns profile creation and its metadata. Never clone credentials or memory.
  fresh=0
  if [[ ! -d "$profile_dir" ]]; then
    hermes profile create "$role"
    fresh=1
  fi
  if [[ "$fresh" == 1 && -e "$target" ]]; then
    cp -p "$target" "$profile_dir/SOUL.md.before-okal"
  fi
  install -m 600 "$source_file" "$target"
  echo "Installed $target"
done

echo "Next: select an existing local Ollama model for each profile with hermes -p <name> model"
