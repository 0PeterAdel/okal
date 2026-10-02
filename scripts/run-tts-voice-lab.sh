#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LAB_PYTHON="$ROOT_DIR/.venv-okal-tts-lab/bin/python"

if [[ "${1:-}" == "--setup" ]]; then
  source_python="$ROOT_DIR/.venv-okal-voice/bin/python"
  if [[ ! -x "$source_python" ]]; then
    echo "Voice Python missing. Run: bash scripts/setup-local-voice-stack.sh --stt-only" >&2
    exit 1
  fi
  "$source_python" -m venv "$ROOT_DIR/.venv-okal-tts-lab"
  "$LAB_PYTHON" -m pip install --upgrade pip
  "$LAB_PYTHON" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
  "$LAB_PYTHON" -m pip install 'git+https://github.com/k2-fsa/OmniVoice.git' 'voicetut-tts>=0.1,<1'
  echo "VoiceTut lab ready. Run: bash scripts/run-tts-voice-lab.sh"
  exit 0
fi

if [[ ! -x "$LAB_PYTHON" ]]; then
  echo "VoiceTut lab missing. Run: bash scripts/run-tts-voice-lab.sh --setup" >&2
  exit 1
fi

umask 077
export PYTHONPATH="$ROOT_DIR/apps/voice/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$LAB_PYTHON" -m okal_voice.tts_lab "$@"
