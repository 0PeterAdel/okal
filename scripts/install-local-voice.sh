#!/usr/bin/env bash
set -euo pipefail

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_HOME/okal/app"
BIN_DIR="$HOME/.local/bin"
UNIT_DIR="$HOME/.config/systemd/user"
PLUGIN_DIR="$HOME/.config/omarchy/plugins/okal.voice"
BINDINGS="$HOME/.config/hypr/bindings.lua"
MARKER="-- Okal local voice"
VOICE_PYTHON="$SOURCE/.venv-okal-voice/bin/python"
ENV_DIR="$HOME/.config/okal"
ENV_FILE="$ENV_DIR/voice.env"

if ! command -v pw-record >/dev/null 2>&1; then
  echo "ERROR: required command is missing: pw-record" >&2
  exit 1
fi

if [[ ! -x "$VOICE_PYTHON" ]]; then
  echo "ERROR: voice environment is missing. Run: bash scripts/setup-local-voice-stack.sh" >&2
  exit 1
fi

"$VOICE_PYTHON" - <<'PY'
import sys
if not (3, 12) <= sys.version_info[:2] <= (3, 13):
    raise SystemExit("Voice environment requires Python 3.12 or 3.13")
PY

install -d -m 700 "$APP_DIR" "$BIN_DIR" "$UNIT_DIR" "$PLUGIN_DIR" "$ENV_DIR"
if [[ ! -e "$ENV_FILE" ]]; then
  (
    umask 077
    printf 'OKAL_STT_BACKEND=faster-whisper\n'
    printf 'OKAL_STT_MODEL_DIR="%s"\n' "$DATA_HOME/okal/models/whisper/egyptian-code-switching-ct2"
    printf 'OKAL_STT_DEVICE=cuda\nOKAL_STT_COMPUTE_TYPE=int8_float16\n'
    printf 'OKAL_STT_LANGUAGE_MODE=dual\n'
  ) > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi
cp -R "$SOURCE/apps/voice/src/okal_voice" "$APP_DIR/"
cp "$SOURCE/apps/voice/plugin/okal.voice/manifest.json" "$PLUGIN_DIR/manifest.json"
cp "$SOURCE/apps/voice/plugin/okal.voice/VoiceOrb.qml" "$PLUGIN_DIR/VoiceOrb.qml"
install -m 644 "$SOURCE/apps/voice/share/okal-voice.service" "$UNIT_DIR/okal-voice.service"

launcher="$(mktemp)"
trap 'rm -f "$launcher"' EXIT
sed -e "s|@APP_DIR@|$APP_DIR|g" -e "s|@VOICE_PYTHON@|$VOICE_PYTHON|g" >"$launcher" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="@APP_DIR@${PYTHONPATH:+:$PYTHONPATH}"
site_packages="$("@VOICE_PYTHON@" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')"
cublas_dir="$site_packages/nvidia/cublas/lib"
cudnn_dir="$site_packages/nvidia/cudnn/lib"
if [[ -f "$cublas_dir/libcublas.so.12" && -f "$cudnn_dir/libcudnn.so.9" ]]; then
  export LD_LIBRARY_PATH="$cublas_dir:$cudnn_dir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
exec "@VOICE_PYTHON@" -m okal_voice.cli "$@"
LAUNCHER
install -m 755 "$launcher" "$BIN_DIR/okal"

if [[ -f "$BINDINGS" ]]; then
  # Earlier installs could append the same block repeatedly because grep
  # interpreted the Lua comment marker beginning with -- as an option.
  "$VOICE_PYTHON" - "$BINDINGS" "$SOURCE/apps/voice/share/bindings.lua.snippet" <<'PY'
import shutil
import sys
from pathlib import Path

bindings, snippet = map(Path, sys.argv[1:])
content = bindings.read_text(encoding="utf-8")
block = snippet.read_text(encoding="utf-8")
count = content.count(block)
if count > 1:
    backup = Path(str(bindings) + ".bak-okal-voice-dedup")
    if not backup.exists():
        shutil.copy2(bindings, backup)
    bindings.write_text(content.replace(block, "", count - 1), encoding="utf-8")
    print(f"Removed {count - 1} duplicate Okal binding(s); backup: {backup}")
PY
fi
if [[ -f "$BINDINGS" ]] && ! grep -Fq -- "$MARKER" "$BINDINGS"; then
  cp "$BINDINGS" "$BINDINGS.bak-okal-voice"
  printf '\n' >>"$BINDINGS"
  cat "$SOURCE/apps/voice/share/bindings.lua.snippet" >>"$BINDINGS"
elif [[ ! -f "$BINDINGS" ]]; then
  printf 'WARN: %s is missing; add apps/voice/share/bindings.lua.snippet manually.\n' "$BINDINGS"
fi

systemctl --user daemon-reload
systemctl --user enable okal-voice.service
systemctl --user restart okal-voice.service
if command -v omarchy >/dev/null 2>&1; then
  omarchy plugin enable okal.voice 2>/dev/null || true
fi
hyprctl reload >/dev/null 2>&1 || true

printf 'Installed Okal local voice. Run: okal voice doctor\n'
printf 'Service settings: %s (edit, then systemctl --user restart okal-voice.service)\n' "$ENV_FILE"
printf 'Default shortcut: SUPER + SHIFT + O\n'
