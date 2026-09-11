#!/usr/bin/env bash
set -euo pipefail

# Installs only local components. No API key or hosted inference is required.
# Run from the repository root on Omarchy/Arch Linux.

python3 -m venv --upgrade-deps .venv-okal-voice
source .venv-okal-voice/bin/activate
python -m pip install -e '.[stt,tts,lab]'

mkdir -p "${XDG_DATA_HOME:-$HOME/.local/share}/okal/models/whisper"

cat <<'EOF'

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
       export OKAL_SILMA_REF_AUDIO=$HOME/.local/share/okal/voice/ref.wav
       export OKAL_SILMA_REF_TEXT='...exact words spoken in ref.wav...'

No cloud endpoint is configured by this script.
EOF
