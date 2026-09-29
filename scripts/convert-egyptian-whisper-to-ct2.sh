#!/usr/bin/env bash
set -euo pipefail

SOURCE_MODEL="${1:-mohammedaly22/whisper-large-v3-turbo-egyptian-code-switching}"
OUTPUT_DIR="${2:-${XDG_DATA_HOME:-$HOME/.local/share}/okal/models/whisper/egyptian-code-switching-ct2}"
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv-okal-voice/bin/python"
CONVERTER_BIN="$ROOT_DIR/.venv-okal-voice/bin/ct2-transformers-converter"

if [[ ! -x "$PYTHON_BIN" || ! -x "$CONVERTER_BIN" ]]; then
  echo "Voice conversion tools are missing. Run: bash scripts/setup-local-voice-stack.sh --stt-only" >&2
  exit 1
fi

if [[ -e "$OUTPUT_DIR" || -L "$OUTPUT_DIR" ]]; then
  if [[ -s "$OUTPUT_DIR/model.bin" && -s "$OUTPUT_DIR/tokenizer.json" && -s "$OUTPUT_DIR/preprocessor_config.json" ]]; then
    echo "Converted CTranslate2 model already exists: $OUTPUT_DIR"
    exit 0
  fi
  if [[ ! -d "$OUTPUT_DIR" || -L "$OUTPUT_DIR" ]] || ! rmdir -- "$OUTPUT_DIR" 2>/dev/null; then
    echo "Incomplete conversion directory is not empty: $OUTPUT_DIR" >&2
    echo "Inspect it and move it aside before retrying; existing files were not removed." >&2
    exit 1
  fi
fi

preprocessor_json="$("$PYTHON_BIN" -m okal_voice.model_conversion "$SOURCE_MODEL")"
mkdir -p "$(dirname -- "$OUTPUT_DIR")"
"$CONVERTER_BIN" \
  --model "$SOURCE_MODEL" \
  --output_dir "$OUTPUT_DIR" \
  --copy_files tokenizer.json \
  --quantization int8_float16

if [[ ! -s "$OUTPUT_DIR/model.bin" || ! -s "$OUTPUT_DIR/tokenizer.json" ]]; then
  echo "Conversion did not produce model.bin and tokenizer.json in $OUTPUT_DIR" >&2
  exit 1
fi
printf '%s\n' "$preprocessor_json" > "$OUTPUT_DIR/preprocessor_config.json"

echo "Converted CTranslate2 model: $OUTPUT_DIR"
echo "Use: export OKAL_STT_MODEL_DIR=$OUTPUT_DIR"
