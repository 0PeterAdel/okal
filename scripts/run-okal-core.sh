#!/usr/bin/env bash
set -euo pipefail

okal_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
okal_python="${OKAL_CORE_PYTHON:-$okal_root/.venv-okal-core/bin/python}"
if [[ ! -x "$okal_python" ]]; then
  echo 'Core environment missing. Follow docs/CORE-INBOX.md; do not run the voice installer.' >&2
  exit 1
fi
export PYTHONPATH="$okal_root/apps/core/src"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
exec "$okal_python" -m okal_core "$@"
