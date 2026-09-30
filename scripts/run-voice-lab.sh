#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv-okal-voice/bin/python"
LAB_BIN="$ROOT_DIR/.venv-okal-voice/bin/okal-voice-lab"

if [[ ! -x "$PYTHON_BIN" || ! -x "$LAB_BIN" ]]; then
  echo "Voice Lab is missing. Run: bash scripts/setup-local-voice-stack.sh --stt-only" >&2
  exit 1
fi

if [[ "${OKAL_STT_DEVICE:-cuda}" == "cuda" && "${OKAL_STT_BACKEND:-faster-whisper}" == "faster-whisper" ]]; then
  site_packages="$("$PYTHON_BIN" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')"
  cublas_dir="$site_packages/nvidia/cublas/lib"
  cudnn_dir="$site_packages/nvidia/cudnn/lib"
  if [[ ! -f "$cublas_dir/libcublas.so.12" || ! -f "$cudnn_dir/libcudnn.so.9" ]]; then
    echo "CUDA 12 cuBLAS and cuDNN 9 are missing from the voice environment." >&2
    echo "Run: .venv-okal-voice/bin/python -m pip install '.[cuda]'" >&2
    exit 1
  fi
  export LD_LIBRARY_PATH="$cublas_dir:$cudnn_dir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

exec "$LAB_BIN" "$@"
