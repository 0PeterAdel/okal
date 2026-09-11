#!/usr/bin/env bash
set -euo pipefail

SOURCE_MODEL="${1:-mohammedaly22/whisper-large-v3-turbo-egyptian-code-switching}"
OUTPUT_DIR="${2:-${XDG_DATA_HOME:-$HOME/.local/share}/okal/models/whisper/egyptian-code-switching-ct2}"

command -v ct2-transformers-converter >/dev/null || {
  echo "ct2-transformers-converter is missing. Install faster-whisper/ctranslate2 first." >&2
  exit 1
}

mkdir -p "$OUTPUT_DIR"
ct2-transformers-converter \
  --model "$SOURCE_MODEL" \
  --output_dir "$OUTPUT_DIR" \
  --copy_files tokenizer.json preprocessor_config.json \
  --quantization int8_float16

echo "Converted CTranslate2 model: $OUTPUT_DIR"
echo "Use: export OKAL_STT_MODEL_DIR=$OUTPUT_DIR"
