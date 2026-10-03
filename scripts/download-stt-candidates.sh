#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COHERE_PY="$ROOT_DIR/.venv-okal-stt-cohere/bin/python"
QWEN_PY="$ROOT_DIR/.venv-okal-stt-qwencleo/bin/python"
DOWNLOAD_TIMEOUT="${HF_HUB_DOWNLOAD_TIMEOUT:-600}"
MAX_WORKERS="${OKAL_HF_MAX_WORKERS:-8}"

if [[ ! -x "$COHERE_PY" || ! -x "$QWEN_PY" ]]; then
  echo "Candidate environments are missing." >&2
  echo "Run: bash scripts/setup-stt-tournament.sh" >&2
  exit 2
fi

download_model() {
  local python_bin="$1"
  local repo_id="$2"
  local required_file="$3"

  echo
  echo "=== Downloading $repo_id (HTTP fallback, Xet disabled) ==="
  HF_HUB_DISABLE_XET=1 \
  HF_HUB_DOWNLOAD_TIMEOUT="$DOWNLOAD_TIMEOUT" \
  OKAL_HF_REPO="$repo_id" \
  OKAL_HF_REQUIRED_FILE="$required_file" \
  OKAL_HF_MAX_WORKERS="$MAX_WORKERS" \
  "$python_bin" - <<'PY'
import os
from pathlib import Path
from huggingface_hub import snapshot_download

repo_id = os.environ["OKAL_HF_REPO"]
required_file = os.environ["OKAL_HF_REQUIRED_FILE"]
max_workers = int(os.environ["OKAL_HF_MAX_WORKERS"])

path = Path(snapshot_download(repo_id=repo_id, max_workers=max_workers))
required = path / required_file
if not required.is_file() or required.stat().st_size == 0:
    raise SystemExit(f"Incomplete snapshot: missing {required_file} in {path}")
print(f"Ready: {repo_id}")
print(f"Snapshot: {path}")
print(f"{required_file}: {required.stat().st_size / (1024**3):.2f} GiB")
PY
}

download_model "$QWEN_PY" "mohammedaly22/QwenCleo-ASR" "model.safetensors"
download_model "$COHERE_PY" "CohereLabs/cohere-transcribe-arabic-07-2026" "model.safetensors"

cat <<'EOF'

Both candidate snapshots are ready in the Hugging Face cache.

Run the benchmark with Xet disabled as a guard:
  HF_HUB_DISABLE_XET=1 bash scripts/run-stt-tournament.sh voice-lab-holdout-audio holdout
EOF
