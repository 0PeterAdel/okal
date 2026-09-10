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

for command in python3 pw-record; do
  if ! command -v "$command" >/dev/null 2>&1; then
    printf 'ERROR: required command is missing: %s\n' "$command" >&2
    exit 1
  fi
done

python3 - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12 or newer is required")
PY

install -d -m 700 "$APP_DIR" "$BIN_DIR" "$UNIT_DIR" "$PLUGIN_DIR"
cp -R "$SOURCE/apps/voice/src/okal_voice" "$APP_DIR/"
cp "$SOURCE/apps/voice/plugin/okal.voice/manifest.json" "$PLUGIN_DIR/manifest.json"
cp "$SOURCE/apps/voice/plugin/okal.voice/VoiceOrb.qml" "$PLUGIN_DIR/VoiceOrb.qml"
install -m 644 "$SOURCE/apps/voice/share/okal-voice.service" "$UNIT_DIR/okal-voice.service"

launcher="$(mktemp)"
trap 'rm -f "$launcher"' EXIT
sed "s|@APP_DIR@|$APP_DIR|g" >"$launcher" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="@APP_DIR@${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m okal_voice.cli "$@"
LAUNCHER
install -m 755 "$launcher" "$BIN_DIR/okal"

if [[ -f "$BINDINGS" ]] && ! grep -Fq "$MARKER" "$BINDINGS"; then
  cp "$BINDINGS" "$BINDINGS.bak-okal-voice"
  printf '\n' >>"$BINDINGS"
  cat "$SOURCE/apps/voice/share/bindings.lua.snippet" >>"$BINDINGS"
elif [[ ! -f "$BINDINGS" ]]; then
  printf 'WARN: %s is missing; add apps/voice/share/bindings.lua.snippet manually.\n' "$BINDINGS"
fi

systemctl --user daemon-reload
systemctl --user enable --now okal-voice.service
if command -v omarchy >/dev/null 2>&1; then
  omarchy plugin enable okal.voice 2>/dev/null || true
fi
hyprctl reload >/dev/null 2>&1 || true

printf 'Installed Okal local voice. Run: okal voice doctor\n'
printf 'Default shortcut: SUPER + SHIFT + O\n'
