#!/usr/bin/env bash
# Preview the Git-tracked OKAL design logo without modifying Production.
set -Eeuo pipefail
umask 077

repo="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$repo"
branch="feat/okal-design-system"
if [[ "$(git symbolic-ref --quiet --short HEAD || true)" != "$branch" ]]; then
  echo "STOP: Expected $branch feature worktree." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "STOP: Tracked changes are not committed. Commit before preview." >&2
  exit 1
fi
for cmd in git tar ss python3.14; do
  command -v "$cmd" >/dev/null || {
    echo "STOP: Missing $cmd" >&2
    exit 1
  }
done
if ss -H -lnt '( sport = :8767 )' | grep -q .; then
  echo "STOP: Port 8767 is occupied. Production port 8766 will not be touched." >&2
  exit 1
fi
asset="apps/core/src/okal_core/static/assets/okal-master-hq.webp"
git ls-files --error-unmatch "$asset" >/dev/null || {
  echo "STOP: Logo is not committed to Git. Copy, add and commit it first." >&2
  exit 1
}
commit_sha="$(git rev-parse --short HEAD)"
mkdir -p "$HOME/.local/state"
scratch="$(mktemp -d "$HOME/.local/state/okal-design-preview-XXXXXXXX")"
cleanup() {
  if [[ -n "$scratch" && -d "$scratch" && "$scratch" == "$HOME"/.local/state/okal-design-preview-* ]]; then
    rm -rf -- "$scratch"
  fi
  echo "Preview stopped; Production unchanged."
}
trap cleanup EXIT
mkdir -m 700 "$scratch/source" "$scratch/state"
git archive HEAD | tar -xf - -C "$scratch/source"
cd "$scratch/source"

python3.14 - <<'PY'
from pathlib import Path
data = Path("apps/core/src/okal_core/static/assets/okal-master-hq.webp").read_bytes()
assert data[:4] == b"RIFF" and data[8:16] == b"WEBPVP8X"
assert len(data) >= 200_000, "Image too small: use the approved HQ master"
w = int.from_bytes(data[24:27], "little") + 1
h = int.from_bytes(data[27:30], "little") + 1
assert (w, h) == (1254, 1254), (w, h)
print(f"PASS: git-committed OKAL logo {w}x{h}, {len(data):,} bytes")
PY

python3.14 -m venv "$scratch/venv"
python="$scratch/venv/bin/python"
if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$python" --require-hashes \
    -r apps/core/requirements-mail.lock
elif "$python" -m pip --version >/dev/null 2>&1; then
  "$python" -m pip install --require-hashes -r apps/core/requirements-mail.lock
elif "$python" -m ensurepip --upgrade >/dev/null 2>&1; then
  "$python" -m pip install --require-hashes -r apps/core/requirements-mail.lock
else
  echo "STOP: Need uv or pip; Production unchanged." >&2
  exit 1
fi

echo "=== Verify repo logo and UI contract ==="
PYTHONPATH=apps/core/src "$python" -m unittest discover \
  -s apps/core/tests -p test_brand_asset.py -v
PYTHONPATH=apps/core/src "$python" -m unittest discover \
  -s apps/core/tests -p test_dashboard_ui_contract.py -v

echo
echo "Commit: $commit_sha"
echo "OKAL design preview: http://127.0.0.1:8767/#chat-home"
echo "Production on 8766 unchanged. Ctrl+C stops preview."
echo
OKAL_CORE_PYTHON="$python" bash scripts/run-okal-core.sh \
  --state-dir "$scratch/state" serve --port 8767
