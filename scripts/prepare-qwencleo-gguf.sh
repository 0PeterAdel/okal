#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv-okal-voice/bin/python"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
RUNTIME_DIR="$DATA_HOME/okal/tools/audiocpp-v0.9.0-cuda"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/okal/downloads"
ARCHIVE="$CACHE_DIR/audio-v0.9.0-bin-ubuntu-x64-cuda12.8-colab.tar.gz"
RUNTIME_URL="https://github.com/0xShug0/audio.cpp/releases/download/v0.9.0/audio-v0.9.0-bin-ubuntu-x64-cuda12.8-colab.tar.gz"
RUNTIME_SHA="c9ed906f918246669c324f0d31f1b7dd80cbe003c35cf8a54932f333b57ca3f6"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing .venv-okal-voice; run the existing STT setup first." >&2
  exit 2
fi

model_path() {
  OKAL_DOWNLOAD_MODEL="${1:-0}" HF_HUB_DISABLE_XET=1 HF_HUB_DOWNLOAD_TIMEOUT=600 \
    "$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path
from huggingface_hub import hf_hub_download

repo = "mohammedaly22/QwenCleo-ASR-GGUF"
revision = "6884dc2054684a2bb5e70ac8074e43f9c9fcd78a"
name = "qwencleo-asr-q8_0.gguf"
download = os.environ["OKAL_DOWNLOAD_MODEL"] == "1"
try:
    path = Path(hf_hub_download(repo, name, revision=revision, local_files_only=not download))
except Exception as exc:
    if download:
        raise SystemExit(f"Download paused: {exc}\nRetry the same command; the Hub cache preserves completed bytes.")
    raise SystemExit("Model is not complete in cache. No download started.")
if path.stat().st_size < 2_000_000_000:
    raise SystemExit("Incomplete QwenCleo Q8 model in cache")
print(path)
PY
}

case "${1:---cache-status}" in
  --cache-status)
    if find "$RUNTIME_DIR" -type f -name audiocpp_server -print -quit 2>/dev/null | grep -q .; then
      echo "audio.cpp runtime ready in $RUNTIME_DIR"
    else
      echo "audio.cpp runtime missing. No download started."
    fi
    model_path 0 || true
    ;;
  --model-path)
    model_path 0
    ;;
  --download-model)
    model_path 1
    ;;
  --download-runtime)
    if find "$RUNTIME_DIR" -type f -name audiocpp_server -print -quit 2>/dev/null | grep -q .; then
      echo "audio.cpp runtime already present: $RUNTIME_DIR"
      exit 0
    fi
    command -v curl >/dev/null || { echo "curl is required" >&2; exit 2; }
    install -d -m 700 "$CACHE_DIR" "$RUNTIME_DIR"
    if ! echo "$RUNTIME_SHA  $ARCHIVE" | sha256sum -c --status 2>/dev/null; then
      echo "Fetching 214 MB audio.cpp runtime. Retry this command after an interruption."
      curl -fL -C - --retry 8 --retry-all-errors --retry-delay 3 -o "$ARCHIVE" "$RUNTIME_URL"
    fi
    echo "$RUNTIME_SHA  $ARCHIVE" | sha256sum -c
    tar -xzf "$ARCHIVE" -C "$RUNTIME_DIR"
    server="$(find "$RUNTIME_DIR" -type f -name audiocpp_server -print -quit)"
    [[ -n "$server" ]] || { echo "Archive lacks audiocpp_server" >&2; exit 2; }
    chmod u+x "$server"
    echo "Runtime ready: $server"
    ;;
  *)
    echo "Usage: $0 [--cache-status|--model-path|--download-model|--download-runtime]" >&2
    exit 2
    ;;
esac
