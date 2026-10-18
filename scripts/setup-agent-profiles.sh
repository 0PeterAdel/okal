#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: bash scripts/setup-agent-profiles.sh [--dry-run|--apply] [--refresh-main]" >&2
  exit 2
}

mode="${1:---dry-run}"
refresh="${2:-}"
[[ $# -le 2 && ( "$mode" == "--dry-run" || "$mode" == "--apply" ) &&
   ( -z "$refresh" || "$refresh" == "--refresh-main" ) ]] || usage
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$mode" == "--apply" ]] && ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes is not installed. Follow docs/USE-FIRST-AGENTS.md first." >&2
  exit 1
fi

for role in okal-research okal-code okal-social okal-main okal-jobs okal-freelance; do
  profile_dir="$HOME/.hermes/profiles/$role"
  target="$profile_dir/SOUL.md"
  source_file="$root/agents/profiles/$role/SOUL.md"
  if [[ -d "$profile_dir" && -e "$target" ]]; then
    if [[ "$role" == okal-main && "$refresh" == --refresh-main ]]; then
      if [[ "$mode" == --dry-run ]]; then
        echo "Would back up and refresh $target from $source_file"
      else
        backup="$profile_dir/SOUL.md.before-freelance-$(date -u +%Y%m%dT%H%M%SZ)"
        cp -p "$target" "$backup"
        install -m 600 "$source_file" "$target"
        echo "Refreshed $target; backup: $backup"
      fi
      continue
    fi
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

skill_source="$root/agents/skills/okal-career-cv/SKILL.md"
skill_target="$HOME/.hermes/profiles/okal-jobs/skills/okal-career-cv/SKILL.md"
if [[ "$mode" == "--dry-run" ]]; then
  echo "Would install career PDF skill at $skill_target if absent"
elif [[ -e "$skill_target" ]]; then
  echo "Keep existing career PDF skill: $skill_target"
else
  mkdir -p "$(dirname "$skill_target")"
  install -m 600 "$skill_source" "$skill_target"
  echo "Installed career PDF skill: $skill_target"
fi

echo "Next: select an existing local Ollama model for each profile with hermes -p <name> model"
