#!/usr/bin/env bash

set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

broken=0

while IFS= read -r -d '' file; do
  fence_count="$(grep -c '^```' "$file" || true)"
  if ((fence_count % 2 != 0)); then
    echo "Unbalanced fenced code block: ${file#./}" >&2
    broken=1
  fi

  while IFS= read -r match; do
    target="${match#](}"
    target="${target%)}"

    case "$target" in
      ''|'#'*|http://*|https://*|mailto:*|artifact:*|sandbox:*)
        continue
        ;;
    esac

    target="${target%%#*}"
    target="${target%%\?*}"
    target="${target#<}"
    target="${target%>}"

    if [[ "$target" == /* ]]; then
      candidate=".${target}"
    else
      candidate="$(dirname "$file")/${target}"
    fi

    if [[ -e "$candidate" || -e "${candidate}.md" ]]; then
      continue
    fi

    echo "Broken local Markdown link in ${file#./}: $target" >&2
    broken=1
  done < <(grep -oE '\]\([^)]*\)' "$file" || true)
done < <(find . -type f -name '*.md' -not -path './.git/*' -print0)

exit "$broken"
