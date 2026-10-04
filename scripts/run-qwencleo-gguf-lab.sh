#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
AUDIO_DIR="${1:-voice-lab-holdout-audio}"
SUITE="${2:-holdout}"
OUT_DIR="${3:-voice-lab-qwencleo-gguf}"
PYTHON_BIN="$ROOT_DIR/.venv-okal-voice/bin/python"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
RUNTIME_DIR="$DATA_HOME/okal/tools/audiocpp-v0.9.0-cuda"
SERVER="$(find "$RUNTIME_DIR" -type f -name audiocpp_server -print -quit 2>/dev/null || true)"
[[ -x "$SERVER" ]] || { echo "Runtime missing; run bash scripts/prepare-qwencleo-gguf.sh --download-runtime" >&2; exit 2; }
[[ -d "$AUDIO_DIR" ]] || { echo "Audio directory missing: $AUDIO_DIR" >&2; exit 2; }
MODEL="$(bash scripts/prepare-qwencleo-gguf.sh --model-path)" || {
  echo "Model missing; run bash scripts/prepare-qwencleo-gguf.sh --download-model" >&2
  exit 2
}
[[ -f "$MODEL" ]] || { echo "Model missing; run bash scripts/prepare-qwencleo-gguf.sh --download-model" >&2; exit 2; }
if "$PYTHON_BIN" - <<'PY'
import socket
with socket.socket() as sock:
    raise SystemExit(0 if sock.connect_ex(("127.0.0.1", 18080)) == 0 else 1)
PY
then
  echo "Port 18080 is in use; stop that process before this isolated lab run." >&2
  exit 2
fi
install -d -m 700 "$OUT_DIR"
TEMP_DIR="$(mktemp -d)"
chmod 700 "$TEMP_DIR"
SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf -- "$TEMP_DIR"
}
trap cleanup EXIT INT TERM

"$PYTHON_BIN" - "$TEMP_DIR/server.json" "$MODEL" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps({
    "host": "127.0.0.1", "port": 18080, "backend": "cuda", "device": 0,
    "threads": 1, "lazy_load": True, "max_loaded_models": 1,
    "models": [{"id": "qwencleo", "family": "qwen3_asr", "path": sys.argv[2],
                "task": "asr", "mode": "offline"}],
}), encoding="utf-8")
PY
"$SERVER" --config "$TEMP_DIR/server.json" >"$TEMP_DIR/server.log" 2>&1 &
SERVER_PID=$!
for (( i=0; i<120; i++ )); do
  if curl -fsS --max-time 1 http://127.0.0.1:18080/health >/dev/null 2>&1; then break; fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    cat "$TEMP_DIR/server.log" >&2
    echo "audio.cpp server exited; current service/model are unchanged." >&2
    exit 2
  fi
  sleep 1
done
curl -fsS --max-time 2 http://127.0.0.1:18080/health >/dev/null || { echo "audio.cpp server did not become ready" >&2; exit 2; }

export OKAL_STT_BACKEND=audiocpp
export OKAL_STT_MODEL=mohammedaly22/QwenCleo-ASR-GGUF
export OKAL_STT_LANGUAGE=ar
export OKAL_AUDIOCPP_ENDPOINT=http://127.0.0.1:18080
unset OKAL_STT_MODEL_DIR OKAL_STT_HOTWORDS

echo "Running QwenCleo Q8 with Arabic selected for Arabic and mixed commands."
bash scripts/run-voice-lab.sh "$AUDIO_DIR" --suite "$SUITE" --output "$OUT_DIR/qwencleo-ar.json"
echo "Running diagnostic labels for English clips; these labels are not available to a live assistant."
bash scripts/run-voice-lab.sh "$AUDIO_DIR" --suite "$SUITE" --language-hints --output "$OUT_DIR/qwencleo-hints.json"
"$PYTHON_BIN" - "$OUT_DIR/qwencleo-ar.json" "$OUT_DIR/qwencleo-hints.json" <<'PY'
import json
import sys
from pathlib import Path

for filename in sys.argv[1:]:
    data = json.loads(Path(filename).read_text(encoding="utf-8"))
    print(filename)
    for case in data["cases"]:
        label = case["id"]
        if case.get("ok"):
            print(f'  {label}: norm WER={case["normalized_wer"]:.3f}, critical={case["critical_term_recall"]}, {case["transcript"]}')
        else:
            print(f'  {label}: FAILED: {case.get("error", "unknown error")}')
PY
