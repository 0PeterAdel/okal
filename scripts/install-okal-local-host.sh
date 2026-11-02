#!/usr/bin/env bash
# Explicit OWNER installation only. Private loopback-only name http://okal.
set -euo pipefail
umask 077

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
caddyfile="$repo/deploy/okal-local.Caddyfile"
servicefile="$repo/deploy/okal-local-proxy.service"

command -v caddy >/dev/null || {
  echo "STOP: Install Caddy first: sudo pacman -S --needed caddy" >&2
  exit 1
}
command -v curl >/dev/null || { echo "curl missing" >&2; exit 1; }
command -v ss >/dev/null || { echo "ss missing" >&2; exit 1; }

echo "=== Verify current OKAL is running and permits the explicit alias ==="
curl --noproxy "*" -fsS --max-time 4 \
  -H "Host: okal" http://127.0.0.1:8766/api/v1/health >/dev/null || {
  echo "STOP: Update/restart OKAL Production with the hostname-enabled commit first." >&2
  exit 1
}

echo "=== Validate local-only Caddyfile before privileged install ==="
caddy validate --config "$caddyfile" --adapter caddyfile

echo "=== Check existing /etc/hosts aliases and port 80 ==="
if grep -E '^[[:space:]]*[^#[:space:]]+[[:space:]].*' /etc/hosts \
    | sed 's/#.*//' \
    | awk '{for (i=2;i<=NF;i++) if ($i=="okal" && $1!="127.0.0.1") bad=1} END{exit !bad}'; then
  echo "STOP: Existing 'okal' hostname resolves to a different address." >&2
  exit 1
fi
if ! systemctl is-active --quiet okal-local-proxy.service; then
  if ss -H -lnt '( sport = :80 )' | grep -q .; then
    echo "STOP: Port 80 already used. Inspect: sudo ss -lntp '( sport = :80 )'" >&2
    exit 1
  fi
fi

echo "=== Authorize exact privileged changes ==="
sudo -v
for pair in \
  "$caddyfile:/etc/okal/Caddyfile" \
  "$servicefile:/etc/systemd/system/okal-local-proxy.service"; do
  sourcefile="${pair%%:*}"
  destination="${pair#*:}"
  if sudo test -e "$destination" && ! sudo cmp -s "$sourcefile" "$destination"; then
    echo "STOP: Existing config differs: $destination. Won't overwrite." >&2
    exit 1
  fi
done

sudo install -D -m 0644 "$caddyfile" /etc/okal/Caddyfile
sudo install -D -m 0644 "$servicefile" /etc/systemd/system/okal-local-proxy.service

if ! grep -E '^[[:space:]]*127\.0\.0\.1[[:space:]].*' /etc/hosts \
    | sed 's/#.*//' \
    | awk '{for (i=2;i<=NF;i++) if ($i=="okal") found=1} END{exit !found}'; then
  backup="/etc/hosts.okal-backup-$(date +%Y%m%d-%H%M%S)"
  sudo cp -p /etc/hosts "$backup"
  printf '\n127.0.0.1 okal\n' | sudo tee -a /etc/hosts >/dev/null
  echo "Original /etc/hosts backed up: $backup"
fi

sudo systemctl daemon-reload
sudo systemctl enable --now okal-local-proxy.service
echo "=== Verify both local endpoints ==="
curl --noproxy "*" -fsS --max-time 5 \
  http://127.0.0.1:8766/api/v1/health >/dev/null
curl --noproxy "*" -fsS --max-time 5 \
  http://okal/api/v1/health >/dev/null
echo "OK: http://okal/"
echo "Proxy bound to 127.0.0.1:80 only; no LAN/public access."
