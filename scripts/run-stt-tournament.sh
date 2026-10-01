#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
AUDIO_DIR="${1:-voice-lab-holdout-audio}"
SUITE="${2:-holdout}"
OUT_DIR="${3:-voice-lab-tournament}"
COHERE_PY="$ROOT_DIR/.venv-okal-stt-cohere/bin/python"
QWEN_PY="$ROOT_DIR/.venv-okal-stt-qwencleo/bin/python"

cd "$ROOT_DIR" || exit 1

if [[ ! -d "$AUDIO_DIR" ]]; then
  echo "Recording directory not found: $AUDIO_DIR" >&2
  exit 2
fi
if [[ ! -x "$COHERE_PY" || ! -x "$QWEN_PY" ]]; then
  echo "Candidate environments are missing." >&2
  echo "Run: bash scripts/setup-stt-tournament.sh" >&2
  exit 2
fi

mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR"
status=0
BASELINE_PY="$ROOT_DIR/.venv-okal-voice/bin/python"

run_candidate() {
  local label="$1"
  shift
  echo
  echo "=== $label ==="
  if "$@"; then return 0; fi
  echo "Candidate failed: $label" >&2
  status=1
  return 0
}

if [[ -x "$BASELINE_PY" ]]; then
  run_candidate "Control / Seif medium code-switched" \
    env -u OKAL_STT_MODEL_DIR -u OKAL_STT_HOTWORDS \
        OKAL_STT_BACKEND=faster-whisper \
        OKAL_STT_MODEL=Seif-Eldeen-Sameh/whisper-medium-arabic-codeswitched-ct2 \
        OKAL_STT_LANGUAGE_MODE=dual OKAL_STT_DEVICE=cuda \
        OKAL_STT_COMPUTE_TYPE=int8_float16 \
        bash scripts/run-voice-lab.sh "$AUDIO_DIR" --suite "$SUITE" \
          --output "$OUT_DIR/control-seif-medium.json"
else
  echo "Skipping existing faster-whisper control: .venv-okal-voice is missing." >&2
fi

run_candidate "QwenCleo / automatic language"   env OKAL_VOICE_PYTHON="$QWEN_PY" OKAL_STT_BACKEND=qwencleo       OKAL_STT_MODEL=mohammedaly22/QwenCleo-ASR OKAL_STT_LANGUAGE=auto       OKAL_STT_TORCH_DTYPE=bfloat16       bash scripts/run-voice-lab.sh "$AUDIO_DIR" --suite "$SUITE"         --output "$OUT_DIR/qwencleo-auto.json"

run_candidate "QwenCleo / Arabic matrix language"   env OKAL_VOICE_PYTHON="$QWEN_PY" OKAL_STT_BACKEND=qwencleo       OKAL_STT_MODEL=mohammedaly22/QwenCleo-ASR OKAL_STT_LANGUAGE=ar       OKAL_STT_TORCH_DTYPE=bfloat16       bash scripts/run-voice-lab.sh "$AUDIO_DIR" --suite "$SUITE"         --output "$OUT_DIR/qwencleo-ar.json"

run_candidate "Cohere Arabic / Arabic matrix language"   env OKAL_VOICE_PYTHON="$COHERE_PY" OKAL_STT_BACKEND=cohere       OKAL_STT_MODEL=CohereLabs/cohere-transcribe-arabic-07-2026       OKAL_STT_LANGUAGE=ar OKAL_STT_TORCH_DTYPE=bfloat16       bash scripts/run-voice-lab.sh "$AUDIO_DIR" --suite "$SUITE"         --output "$OUT_DIR/cohere-ar.json"

run_candidate "Cohere Arabic / diagnostic language hints"   env OKAL_VOICE_PYTHON="$COHERE_PY" OKAL_STT_BACKEND=cohere       OKAL_STT_MODEL=CohereLabs/cohere-transcribe-arabic-07-2026       OKAL_STT_LANGUAGE=ar OKAL_STT_TORCH_DTYPE=bfloat16       bash scripts/run-voice-lab.sh "$AUDIO_DIR" --suite "$SUITE"         --language-hints --output "$OUT_DIR/cohere-hinted.json"

shopt -s nullglob
reports=("$OUT_DIR"/*.json)
if (( ${#reports[@]} > 0 )); then
  echo
  python3 scripts/compare-stt-results.py "${reports[@]}"
fi

exit "$status"
