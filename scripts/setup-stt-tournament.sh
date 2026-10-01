#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COHERE_ENV="$ROOT_DIR/.venv-okal-stt-cohere"
QWEN_ENV="$ROOT_DIR/.venv-okal-stt-qwencleo"

PYTHON_BIN="${OKAL_VOICE_PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3.13 python3.12 python3; do
    if ! command -v "$candidate" >/dev/null 2>&1; then
      continue
    fi
    if ! version="$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)"; then
      continue
    fi
    case "$version" in
      3.12|3.13) PYTHON_BIN="$candidate"; break ;;
    esac
  done
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python 3.12 or 3.13 is required for the STT candidate environments." >&2
  exit 1
fi

echo "Creating isolated Cohere environment..."
"$PYTHON_BIN" -m venv --upgrade-deps "$COHERE_ENV"
(
  cd "$ROOT_DIR"
  "$COHERE_ENV/bin/python" -m pip install -e ".[lab]"
  "$COHERE_ENV/bin/python" -m pip install     "torch>=2.5,<3"     "transformers>=5.4,<6"     "huggingface-hub>=0.34,<2"     "soundfile>=0.12,<1"     "librosa>=0.11,<1"     "sentencepiece>=0.2,<1"     "protobuf>=5,<7"     "accelerate>=1,<2"
)

echo "Creating isolated QwenCleo environment..."
"$PYTHON_BIN" -m venv --upgrade-deps "$QWEN_ENV"
(
  cd "$ROOT_DIR"
  "$QWEN_ENV/bin/python" -m pip install -e ".[lab]"
  "$QWEN_ENV/bin/python" -m pip install "torch>=2.5,<3" "torchaudio>=2.5,<3"
  "$QWEN_ENV/bin/python" -m pip install "qwen-asr==0.0.6"
)

cat <<EOF

Candidate environments are ready:
  Cohere:   $COHERE_ENV
  QwenCleo: $QWEN_ENV

Cohere's model repository requires accepting its Hugging Face access terms.
Authenticate with a NEW token after accepting them:
  $COHERE_ENV/bin/hf auth login

Do not paste the token into shell commands or commit it to this repository.

Then run:
  bash scripts/run-stt-tournament.sh voice-lab-holdout-audio holdout
EOF
