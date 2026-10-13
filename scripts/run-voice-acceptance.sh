#!/usr/bin/env bash
# Offline, same-WAV comparison. Does not alter the installed voice service.
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
AUDIO_DIR="${1:-voice-lab-acceptance-audio}"
OUT_DIR="${2:-voice-lab-acceptance-results}"
SERVER="${OKAL_AUDIOCPP_SERVER:-${XDG_CACHE_HOME:-$HOME/.cache}/okal/audio.cpp-source/build-okal-cuda/bin/audiocpp_server}"
MODEL_DIR="${OKAL_ACCEPTANCE_WHISPER_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/okal/models/whisper/egyptian-code-switching-ct2}"

[[ -x "$SERVER" ]] || { echo "Locally built audio.cpp server missing: $SERVER" >&2; exit 2; }
[[ -f "$MODEL_DIR/model.bin" ]] || { echo "Converted Whisper model missing: $MODEL_DIR/model.bin" >&2; exit 2; }
[[ -d "$AUDIO_DIR" ]] || { echo "Record the acceptance suite first: bash scripts/record-voice-lab.sh '$AUDIO_DIR' acceptance" >&2; exit 2; }
for case_id in $(PYTHONPATH="$ROOT_DIR/apps/voice/src" python3 -m okal_voice.voice_lab --suite acceptance --list-cases | cut -f1); do
  [[ -s "$AUDIO_DIR/$case_id.wav" ]] || { echo "Missing recording: $AUDIO_DIR/$case_id.wav" >&2; exit 2; }
done
umask 077
mkdir -p "$OUT_DIR"
for review in "$OUT_DIR"/*-review.json; do
  [[ ! -e "$review" ]] || {
    echo "Existing human review preserved: $review" >&2
    echo "Use a new output directory for a fresh run, or score the existing review." >&2
    exit 2
  }
done
export HF_HUB_OFFLINE=1

# The existing lab server reuses the downloaded GGUF; context and auto are both
# live candidates. Its Arabic and hints reports are diagnostics only.
OKAL_AUDIOCPP_SERVER="$SERVER" \
  bash scripts/run-qwencleo-gguf-lab.sh "$AUDIO_DIR" acceptance "$OUT_DIR/qwencleo"

# Reuse the existing converted Whisper files. No model name can trigger a Hub fetch.
env -u OKAL_STT_HOTWORDS -u OKAL_AUDIOCPP_PROMPT \
  OKAL_STT_BACKEND=faster-whisper OKAL_STT_MODEL_DIR="$MODEL_DIR" \
  OKAL_STT_DEVICE=cuda OKAL_STT_COMPUTE_TYPE=int8_float16 OKAL_STT_LANGUAGE_MODE=dual \
  bash scripts/run-voice-lab.sh "$AUDIO_DIR" --suite acceptance \
    --output "$OUT_DIR/whisper-dual.json"

python3 scripts/review-voice-acceptance.py prepare "$OUT_DIR/qwencleo/qwencleo-auto.json" \
  --output "$OUT_DIR/qwencleo-auto-review.json"
python3 scripts/review-voice-acceptance.py prepare "$OUT_DIR/qwencleo/qwencleo-context.json" \
  --output "$OUT_DIR/qwencleo-context-review.json"
python3 scripts/review-voice-acceptance.py prepare "$OUT_DIR/whisper-dual.json" \
  --output "$OUT_DIR/whisper-dual-review.json"
echo "Private reports ready in $OUT_DIR. Fill four booleans per clip, then run:"
echo "python3 scripts/review-voice-acceptance.py score $OUT_DIR/*-review.json"
