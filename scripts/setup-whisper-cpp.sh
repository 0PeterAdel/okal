#!/usr/bin/env bash
set -euo pipefail

WHISPER_COMMIT="371b5a7561823ab2bb32142d2751e35e7534727b"
MODEL_NAME="large-v3-turbo-q5_0"
MODEL_SHA1="e050f7970618a659205450ad97eb95a18d69c9ee"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
SOURCE_DIR="$DATA_HOME/okal/providers/whisper.cpp"
MODEL_DIR="$DATA_HOME/okal/models/whisper"
BIN_DIR="$HOME/.local/bin"

for command in git cmake sha1sum; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: required build command is missing: %s\n' "$command" >&2
    exit 1
  }
done

install -d -m 700 "$(dirname "$SOURCE_DIR")" "$MODEL_DIR" "$BIN_DIR"
if [[ ! -d "$SOURCE_DIR/.git" ]]; then
  git clone --filter=blob:none https://github.com/ggml-org/whisper.cpp.git "$SOURCE_DIR"
fi
git -C "$SOURCE_DIR" fetch --depth 1 origin "$WHISPER_COMMIT"
git -C "$SOURCE_DIR" checkout --detach "$WHISPER_COMMIT"

cmake -S "$SOURCE_DIR" -B "$SOURCE_DIR/build" -DGGML_CUDA=1 -DCMAKE_BUILD_TYPE=Release
cmake --build "$SOURCE_DIR/build" --config Release -j"$(nproc)" --target whisper-cli
"$SOURCE_DIR/models/download-ggml-model.sh" "$MODEL_NAME" "$MODEL_DIR"
printf '%s  %s\n' "$MODEL_SHA1" "$MODEL_DIR/ggml-$MODEL_NAME.bin" | sha1sum --check --strict
install -m 755 "$SOURCE_DIR/build/bin/whisper-cli" "$BIN_DIR/whisper-cli"

printf 'Installed pinned whisper.cpp %s and verified %s.\n' "$WHISPER_COMMIT" "$MODEL_NAME"
