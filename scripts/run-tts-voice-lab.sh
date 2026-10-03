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
  # CUDA 12.1 has a CPython 3.13 torch wheel but no matching torchaudio wheel.
  # Pin the pair to a CUDA 12.6 build published for Python 3.12 and 3.13.
  "$LAB_PYTHON" -m pip install 'torch==2.9.1+cu126' 'torchaudio==2.9.1+cu126' --index-url https://download.pytorch.org/whl/cu126
  "$LAB_PYTHON" -c 'import torch, torchaudio; print("PyTorch", torch.__version__, "Torchaudio", torchaudio.__version__, "CUDA", torch.cuda.is_available()); assert torch.cuda.is_available(), "CUDA is unavailable in the VoiceTut environment"'
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
