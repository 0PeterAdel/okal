#!/usr/bin/env bash
set -euo pipefail

# Installs only local components. No API key or hosted inference is required.
# Run from the repository root on Omarchy/Arch Linux.
# SILMA's current NeMo/Pynini dependency chain does not provide a compatible
# Pynini 2.1.6.post1 wheel for Python 3.14, so the voice environment is pinned
# to CPython 3.12 or 3.13 until that dependency chain moves forward.

PYTHON_BIN="${OKAL_VOICE_PYTHON:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  for candidate in python3.13 python3.12 python3; do
    if ! command -v "${candidate}" >/dev/null 2>&1; then
      continue
    fi
    version="$("${candidate}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    case "${version}" in
      3.12|3.13)
        PYTHON_BIN="${candidate}"
        break
        ;;
    esac
  done
fi

if [[ -z "${PYTHON_BIN}" ]] && command -v mise >/dev/null 2>&1; then
  PYTHON_BIN="$(mise exec python@3.13 -- python -c 'import sys; print(sys.executable)')"
fi

if [[ -z "${PYTHON_BIN}" ]]; then
  cat >&2 <<'EOF'
No supported Python interpreter found for the local voice stack.

SILMA currently pulls NeMo text processing, which pins Pynini 2.1.6.post1.
That Pynini release has wheels through Python 3.13, but not Python 3.14.
Install Python 3.13 (recommended) or 3.12, then rerun this script.

On mise-managed Omarchy systems:
  mise exec python@3.13 -- python --version
  bash scripts/setup-local-voice-stack.sh
EOF
  exit 1
fi

version="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "${version}" in
  3.12|3.13) ;;
  *)
    echo "Unsupported Python ${version}; use CPython 3.12 or 3.13." >&2
    exit 1
    ;;
esac

"${PYTHON_BIN}" -m venv --upgrade-deps .venv-okal-voice
source .venv-okal-voice/bin/activate
python -m pip install -e '.[stt,tts,lab]'

mkdir -p "${XDG_DATA_HOME:-$HOME/.local/share}/okal/models/whisper"

cat <<EOF

Using Python: ${PYTHON_BIN} (${version})

Next steps:
  1. Install ffmpeg if missing: sudo pacman -S --needed ffmpeg
  2. Keep Ollama local: ollama pull qwen3:0.6b
  3. Set CUDA STT defaults:
       export OKAL_STT_BACKEND=faster-whisper
       export OKAL_STT_DEVICE=cuda
       export OKAL_STT_COMPUTE_TYPE=float16
  4. For the Egyptian/code-switching model, either let faster-whisper download it
     from its configured Hugging Face source or provide a converted CTranslate2
     directory with OKAL_STT_MODEL_DIR.
  5. For SILMA, install the package above and provide an authorized 5-10 second
     reference recording plus transcript:
       export OKAL_SILMA_REF_AUDIO=\$HOME/.local/share/okal/voice/ref.wav
       export OKAL_SILMA_REF_TEXT='...exact words spoken in ref.wav...'

No cloud endpoint is configured by this script.
EOF
