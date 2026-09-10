#!/usr/bin/env bash
set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BINDINGS="$HOME/.config/hypr/bindings.lua"

systemctl --user disable --now okal-voice.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/okal-voice.service" "$HOME/.local/bin/okal"
rm -rf "$DATA_HOME/okal/app" "$HOME/.config/omarchy/plugins/okal.voice"
systemctl --user daemon-reload

if [[ -f "$BINDINGS.bak-okal-voice" ]]; then
  cp "$BINDINGS.bak-okal-voice" "$BINDINGS"
  printf 'Restored keybindings from %s\n' "$BINDINGS.bak-okal-voice"
else
  printf 'No keybinding backup found; remove the Okal local voice block manually if present.\n'
fi
hyprctl reload >/dev/null 2>&1 || true
printf 'Removed the Okal voice app, service, and Omarchy plugin. Models were preserved.\n'
