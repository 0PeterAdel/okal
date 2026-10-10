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
SERVER="${OKAL_AUDIOCPP_SERVER:-$(find "$RUNTIME_DIR" -type f -name audiocpp_server -print -quit 2>/dev/null || true)}"
[[ -x "$SERVER" ]] || { echo "audio.cpp server missing or not executable: $SERVER" >&2; exit 2; }
[[ -x "$PYTHON_BIN" ]] || { echo "Voice Lab Python is missing; run bash scripts/setup-local-voice-stack.sh --stt-only" >&2; exit 2; }
# Reuse the CUDA libraries already installed for faster-whisper in this venv.
# The audio.cpp executable runs outside Python, so it needs these paths explicitly.
site_packages="$("$PYTHON_BIN" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')"
cublas_dir="$site_packages/nvidia/cublas/lib"
[[ -f "$cublas_dir/libcublas.so.12" ]] || {
  echo "CUDA 12 cuBLAS is missing from the voice environment; run .venv-okal-voice/bin/python -m pip install '.[cuda]'" >&2
  exit 2
}
cuda_lib_dirs=("$(dirname "$SERVER")")
for lib_dir in "$site_packages"/nvidia/{cublas,cudnn,cuda_runtime,cuda_nvrtc,cufft,nccl}/lib; do
  [[ -d "$lib_dir" ]] && cuda_lib_dirs+=("$lib_dir")
done
# The working VoiceTut CUDA environment can supply runtime, cuFFT and NCCL
# without fetching another copy into the STT virtual environment.
tts_python="$ROOT_DIR/.venv-okal-tts-lab/bin/python"
if [[ -x "$tts_python" ]]; then
  tts_site_packages="$("$tts_python" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')"
  for lib_dir in "$tts_site_packages"/nvidia/{cuda_runtime,cufft,nccl,cublas,cudnn,cuda_nvrtc}/lib; do
    [[ -d "$lib_dir" ]] && cuda_lib_dirs+=("$lib_dir")
  done
fi
cuda_paths="$(IFS=:; echo "${cuda_lib_dirs[*]}")"
export LD_LIBRARY_PATH="$cuda_paths${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
if command -v ldd >/dev/null; then
  missing="$(ldd "$SERVER" 2>&1 | awk '/not found/ {print $1}')"
  if [[ -n "$missing" ]]; then
    echo "audio.cpp still needs shared libraries: $missing" >&2
    echo "The downloaded model and runtime are cached; no re-download is needed." >&2
    exit 2
  fi
fi
[[ -d "$AUDIO_DIR" ]] || { echo "Audio directory missing: $AUDIO_DIR" >&2; exit 2; }
MODEL="$(bash scripts/prepare-qwencleo-gguf.sh --model-path)" || {
  echo "Model missing; run bash scripts/prepare-qwencleo-gguf.sh --download-model" >&2
  exit 2
}
[[ -f "$MODEL" ]] || { echo "Model missing; run bash scripts/prepare-qwencleo-gguf.sh --download-model" >&2; exit 2; }
# Hugging Face's snapshot file is a symlink to an extensionless blob. audio.cpp
# resolves symlinks before selecting the GGUF tensor loader, so expose the same
# inode under a .gguf filename. A hard link uses no additional model storage.
MODEL="$("$PYTHON_BIN" - "$MODEL" <<'PY'
import os
import sys
from pathlib import Path

source = Path(sys.argv[1]).resolve(strict=True)
if source.suffix.lower() == ".gguf":
    print(source)
else:
    target = source.with_name(source.name + ".gguf")
    if target.exists():
        if not target.samefile(source):
            raise SystemExit(f"GGUF hard link points to different data: {target}")
    else:
        try:
            os.link(source, target)
        except OSError as exc:
            raise SystemExit(f"Could not make local GGUF hard link: {exc}") from exc
    print(target)
PY
)"
if "$PYTHON_BIN" - <<'PY'
import socket
with socket.socket() as sock:
    raise SystemExit(0 if sock.connect_ex(("127.0.0.1", 18080)) == 0 else 1)
PY
then
  echo "Port 18080 is in use; stop that process before this isolated lab run." >&2
  exit 2
fi
umask 077
install -d -m 700 "$OUT_DIR"
SERVER_LOG="$OUT_DIR/audiocpp-server.log"
TEMP_DIR="$(mktemp -d)"
chmod 700 "$TEMP_DIR"
SERVER_PID=""
cleanup() {
  status=$?
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  if (( status != 0 )) && [[ -s "$SERVER_LOG" ]]; then
    echo "audio.cpp log: $SERVER_LOG" >&2
    tail -n 80 "$SERVER_LOG" >&2
  fi
  rm -rf -- "$TEMP_DIR"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

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
"$SERVER" --config "$TEMP_DIR/server.json" >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
for (( i=0; i<120; i++ )); do
  if curl -fsS --max-time 1 http://127.0.0.1:18080/health >/dev/null 2>&1; then break; fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "audio.cpp server exited; current service/model are unchanged." >&2
    exit 2
  fi
  sleep 1
done
curl -fsS --max-time 2 http://127.0.0.1:18080/health >/dev/null || { echo "audio.cpp server did not become ready" >&2; exit 2; }

export OKAL_STT_BACKEND=audiocpp
export OKAL_STT_MODEL=mohammedaly22/QwenCleo-ASR-GGUF
export OKAL_STT_LANGUAGE=auto
export OKAL_AUDIOCPP_ENDPOINT=http://127.0.0.1:18080
unset OKAL_STT_MODEL_DIR OKAL_STT_HOTWORDS OKAL_AUDIOCPP_PROMPT

echo "Running QwenCleo Q8 with automatic language selection (live-assistant candidate)."
bash scripts/run-voice-lab.sh "$AUDIO_DIR" --suite "$SUITE" --output "$OUT_DIR/qwencleo-auto.json"
export OKAL_AUDIOCPP_PROMPT='The speaker may use these software terms: README, GitHub, git status, VS Code, terminal, commits, pull request, Wi-Fi, issue.'
echo "Running QwenCleo Q8 auto with a fixed software-terms context."
bash scripts/run-voice-lab.sh "$AUDIO_DIR" --suite "$SUITE" --output "$OUT_DIR/qwencleo-context.json"
unset OKAL_AUDIOCPP_PROMPT
export OKAL_STT_LANGUAGE=ar
echo "Running QwenCleo Q8 with Arabic selected for Arabic and mixed commands."
bash scripts/run-voice-lab.sh "$AUDIO_DIR" --suite "$SUITE" --output "$OUT_DIR/qwencleo-ar.json"
echo "Running diagnostic labels for English clips; these labels are not available to a live assistant."
bash scripts/run-voice-lab.sh "$AUDIO_DIR" --suite "$SUITE" --language-hints --output "$OUT_DIR/qwencleo-hints.json"
"$PYTHON_BIN" - "$OUT_DIR/qwencleo-auto.json" "$OUT_DIR/qwencleo-context.json" "$OUT_DIR/qwencleo-ar.json" "$OUT_DIR/qwencleo-hints.json" <<'PY'
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
baseline = {case["id"]: case for case in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["cases"]}
context = {case["id"]: case for case in json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))["cases"]}
print("Context changes versus automatic language selection:")
for case_id, before in baseline.items():
    after = context[case_id]
    if before.get("transcript") == after.get("transcript"):
        continue
    print(f'  {case_id}: {before.get("transcript", before.get("error"))}')
    print(f'       -> {after.get("transcript", after.get("error"))}')
PY
