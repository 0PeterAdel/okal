#!/usr/bin/env bash
# Exact-branch OKAL Chat preview. Never changes systemd or Production (8766).
set -Eeuo pipefail
umask 077
repo="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$repo"

expected="feat/chat-first-natural-conversation"
branch="$(git symbolic-ref --quiet --short HEAD || true)"
if [[ "$branch" != "$expected" ]]; then
  echo "STOP: Preview must run from the PR #113 feature branch, not $branch" >&2
  exit 1
fi
snapshot_sha="$(git rev-parse --short HEAD)"
for name in node python3.14 ss git tar; do
  command -v "$name" >/dev/null || { echo "Missing: $name" >&2; exit 1; }
done
if [[ -n "$(ss -H -lnt '( sport = :8767 )')" ]]; then
  echo "STOP: Port 8767 is already occupied; do not stop Production." >&2
  exit 1
fi

# Never install into the checkout's .venv: this checkout may back a
# running Production service, even if the preview listens on another port.
# Export the exact committed HEAD into a disposable source snapshot.
scratch="$(mktemp -d "$HOME/.local/state/okal-chat-pr113-XXXXXXXX")"
state="$scratch/state"
mkdir -m 700 "$state"
cleanup() {
  # Only our newly-created preview tree is eligible for removal.
  if [[ -n "${scratch:-}" && "$scratch" == "$HOME"/.local/state/okal-chat-pr113-* && -d "$scratch" ]]; then
    rm -rf -- "$scratch"
  fi
  echo "Isolated preview has stopped; Production is unchanged."
}
trap cleanup EXIT

source_tree="$scratch/source"
mkdir -m 700 "$source_tree"
git archive HEAD | tar -xf - -C "$source_tree"
cd "$source_tree"

echo "=== Creating fresh isolated preview environment ==="
python="$scratch/venv/bin/python"
python3.14 -m venv "$scratch/venv"
if "$python" -m pip --version >/dev/null 2>&1; then
  "$python" -m pip install --require-hashes -r apps/core/requirements-mail.lock
elif command -v uv >/dev/null 2>&1; then
  echo "pip is unavailable in this venv; using uv without modifying system Python."
  uv pip install --python "$python" --require-hashes -r apps/core/requirements-mail.lock
elif "$python" -m ensurepip --upgrade >/dev/null 2>&1; then
  "$python" -m pip install --require-hashes -r apps/core/requirements-mail.lock
else
  echo "STOP: neither pip, uv nor ensurepip is available for this preview Python." >&2
  echo "Install uv using your normal Omarchy/mise package manager, then rerun." >&2
  exit 1
fi

echo "=== Validate current PR source and offline Markdown ==="
node --check apps/core/src/okal_core/static/chat-markdown.js
node --check apps/core/src/okal_core/static/chat-ui.js
node --test apps/core/tests/test_chat_markdown.cjs apps/core/tests/test_chat_ui.cjs apps/core/tests/test_inbox_status.cjs
PYTHONPATH=apps/core/src "$python" -m unittest discover \
  -s apps/core/tests -p 'test_chat.py' -v
PYTHONPATH=apps/core/src "$python" -m unittest discover \
  -s apps/core/tests -p 'test_brand_asset.py' -v
PYTHONPATH=apps/core/src "$python" -m unittest discover \
  -s apps/core/tests -p 'test_dashboard_ui_contract.py' -v

echo "=== Snapshot locally saved SQLite (no OAuth secrets) ==="
"$python" - "$state" <<'PY'
import json
import os
from pathlib import Path
import sqlite3
import sys

destination = Path(sys.argv[1])
old = Path.home() / ".local/state/okal-core"
db = old / "core.sqlite3"
if db.is_file():
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as source:
        with sqlite3.connect(destination / "core.sqlite3") as target:
            source.backup(target)
    (destination / "core.sqlite3").chmod(0o600)
    print("Saved-data snapshot copied into temporary preview state.")

config = old / "mail" / "config.json"
if config.is_file() and not config.is_symlink():
    raw = json.loads(config.read_text())
    keys = ("account", "owner_name", "model", "model_digest",
            "local_only_confirmed", "timezone")
    safe = {key: raw[key] for key in keys if key in raw}
    if {"account", "model", "model_digest"} <= set(safe):
        path = destination / "mail"
        path.mkdir(mode=0o700)
        out = path / "config.json"
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(safe, stream)
        print("Pinned local AI model metadata copied; no Gmail credentials.")
PY

logo=""
if [[ $# -gt 0 ]]; then logo="$1"; fi
if [[ -z "$logo" ]]; then
  for candidate in \
    "$HOME"/Downloads/OKAL_APPROVED_ORIGINAL_UNEDITED*.png \
    "$HOME"/Downloads/OKAL\ Egyptian\ AI\ Emblem*.png \
    "$HOME"/Downloads/OKAL\ Personal\ AI\ Assistant\ Emblem*.png
  do
    if [[ -f "$candidate" ]]; then logo="$candidate"; break; fi
  done
fi
if [[ -n "$logo" ]]; then
  echo "=== Install original high-resolution logo only to preview state ==="
  bash scripts/install-okal-master.sh "$logo" "$state"
else
  echo "NOTICE: No original PNG supplied. Bundled low-resolution WebP fallback will display."
  echo "To fix: bash scripts/preview-chat-pr113.sh '/home/okal/Downloads/Your master.png'"
fi

echo
echo "=== OKAL Chat preview is ready ==="
echo "Branch: $branch"
echo "Commit: $snapshot_sha"
echo "Open: http://127.0.0.1:8767/#chat-home"
echo "Production: 127.0.0.1:8766 — unchanged."
echo "All test appointments are isolated in temporary SQLite."
echo "Press Ctrl+C to stop and remove temporary state."
echo
OKAL_CORE_PYTHON="$python" bash scripts/run-okal-core.sh --state-dir "$state" serve --port 8767
