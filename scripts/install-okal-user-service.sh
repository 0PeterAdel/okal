#!/usr/bin/env bash
# Install a user systemd unit without starting or enabling OKAL.
# Does not touch application state, Ollama, OAuth, models or existing services.
set -euo pipefail
umask 077

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
template="$repo/deploy/okal-core.service"
launcher="$repo/scripts/run-okal-core.sh"
python="$repo/.venv-okal-core/bin/python"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
unit="$unit_dir/okal-core.service"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  printf 'Usage: bash scripts/install-okal-user-service.sh\n'
  printf 'Installs only. Enable/start yourself with systemctl --user enable --now okal-core.service.\n'
  exit 0
fi
if (( $# != 0 )); then
  echo "Unsupported option. Use --help." >&2
  exit 2
fi

# Avoid emitting unescaped systemd unit tokens; other paths can still run
# OKAL in the foreground. In particular '%' expands systemd specifiers.
if [[ ! "$repo" =~ ^/[A-Za-z0-9_./-]+$ ]]; then
  echo "Service installer needs a checkout path containing only letters, digits, '/', '.', '_' or '-'." >&2
  echo "Use a simple folder path for the service, or start OKAL in the foreground." >&2
  exit 1
fi
if [[ ! -f "$template" || ! -f "$launcher" || ! -x "$python" ]]; then
  echo "Missing Core installation. Create .venv-okal-core, install the lock and retry." >&2
  exit 1
fi
command -v systemctl >/dev/null || { echo "systemctl is required." >&2; exit 1; }

# A pre-existing unit may belong to another checkout. Never replace it.
# Only this exact generated content can be treated as idempotent.
generated="$(sed -e 's|^Description=.*|Description=OKAL local personal AI assistant|' \
  -e "s|^WorkingDirectory=.*|WorkingDirectory=$repo|" \
  -e "s|^ExecStart=.*|ExecStart=/bin/bash $launcher serve|" "$template")"
if [[ -L "$unit_dir" || -L "$unit" ]]; then
  echo "Refusing symlinked systemd target; inspect it manually." >&2
  exit 1
fi
# umask 077 secures directories created here without altering an existing user unit tree.\nmkdir -p -- "$unit_dir"
if [[ -e "$unit" ]]; then
  if [[ ! -f "$unit" ]] || ! cmp -s "$unit" <(printf '%s\n' "$generated"); then
    echo "Existing okal-core.service differs; refusing to overwrite it." >&2
    exit 1
  fi
  echo "Already installed: $unit (unchanged)"
else
  # Refuse a pre-existing systemd unit managed elsewhere, including vendor
  # units. Do not overwrite or change its running state.
  if systemctl --user cat okal-core.service >/dev/null 2>&1; then
    echo "Another okal-core.service is already registered; inspect it first." >&2
    exit 1
  fi
  printf '%s\n' "$generated" > "$unit"
  chmod 0644 "$unit"
  echo "Installed: $unit"
fi

echo "No service was enabled, started or restarted by this installer."
echo "To opt in, run: systemctl --user daemon-reload"
echo "Then start only when ready: systemctl --user enable --now okal-core.service"
echo "To stop and disable: systemctl --user disable --now okal-core.service"
