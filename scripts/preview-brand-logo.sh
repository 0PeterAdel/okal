#!/usr/bin/env bash
# Visual and functional preview for the committed approved logo; no Production changes.
set -Eeuo pipefail
umask 077

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"
expected="fix/brand-bundled-high-resolution-logo"
branch="$(git symbolic-ref --quiet --short HEAD || true)"
if [[ "$branch" != "$expected" ]]; then
  echo "STOP: Expected branch $expected (current: ${branch:-DETACHED})." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "STOP: Tracked changes in preview source. Review first." >&2
  exit 1
fi
for tool in git tar python3.14 ss node; do
  command -v "$tool" >/dev/null || { echo "STOP: Missing $tool" >&2; exit 1; }
done
if ss -H -lnt '( sport = :8767 )' | grep -q .; then
  echo "STOP: Port 8767 is occupied. Stop the old preview first." >&2
  exit 1
fi

mkdir -p "$HOME/.local/state"
scratch="$(mktemp -d "$HOME/.local/state/okal-brand-preview-XXXXXXXX")"
cleanup() {
  if [[ -n "${scratch:-}" && "$scratch" == "$HOME"/.local/state/okal-brand-preview-* && -d "$scratch" ]]; then
    rm -rf -- "$scratch"
  fi
}
trap cleanup EXIT
head="$(git rev-parse HEAD)"
mkdir -p "$scratch/source" "$scratch/state"
git archive "$head" | tar -xf - -C "$scratch/source"
cd "$scratch/source"

echo "=== Verify full-resolution committed asset ==="
python3.14 - <<'PY'
from pathlib import Path
p = Path("apps/core/src/okal_core/static/assets/okal-master-hq.webp")
raw = p.read_bytes()
assert len(raw) > 200_000, "Bundled image unexpectedly small"
assert raw[:4] == b"RIFF" and raw[8:16] == b"WEBPVP8X"
width = int.from_bytes(raw[24:27], "little") + 1
height = int.from_bytes(raw[27:30], "little") + 1
assert (width, height) == (1254, 1254), (width, height)
print(f"PASS: {width}x{height} WebP, {len(raw):,} bytes")
PY

echo "=== Install dependencies to temporary environment ==="
python3.14 -m venv "$scratch/venv"
python="$scratch/venv/bin/python"
if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$python" --require-hashes -r apps/core/requirements-mail.lock
elif "$python" -m pip --version >/dev/null 2>&1; then
  "$python" -m pip install --require-hashes -r apps/core/requirements-mail.lock
elif "$python" -m ensurepip --upgrade >/dev/null 2>&1; then
  "$python" -m pip install --require-hashes -r apps/core/requirements-mail.lock
else
  echo "STOP: No uv, pip, or ensurepip available. Production unchanged." >&2
  exit 1
fi

echo "=== Run logo regression tests ==="
PYTHONPATH=apps/core/src "$python" -m unittest discover \
  -s apps/core/tests -p test_brand_asset.py -v

echo
echo "OKAL BRAND HQ PREVIEW"
echo "Commit: $head"
echo "URL: http://127.0.0.1:8767/#chat-home"
echo "Production 8766: untouched."
echo "Gmail credentials/production database: not copied."
echo "Ctrl+C exits and cleans preview files."
echo

OKAL_CORE_PYTHON="$python" \
  bash scripts/run-okal-core.sh --state-dir "$scratch/state" serve --port 8767
