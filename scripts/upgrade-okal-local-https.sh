#!/usr/bin/env bash
# Owner-controlled migration: plain localhost http://okal -> trusted local HTTPS.
# Requires the old, repo-managed Caddy proxy or an absent configuration.
set -euo pipefail
umask 077
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"
command -v caddy >/dev/null || { echo "STOP: caddy not installed" >&2; exit 1; }
command -v ss >/dev/null || { echo "STOP: ss missing" >&2; exit 1; }
command -v curl >/dev/null || { echo "STOP: curl missing" >&2; exit 1; }
test -f deploy/okal-local.Caddyfile
test -f deploy/okal-local-proxy.service

# Can't safely overwrite a manually customized system proxy. Compare against
# the previously merged v1 templates, fetched from the LOCAL git history only.
old_commit="a41889be2964e5bc383d74eed19a7dcb3236bef1"
work="$(mktemp -d "$HOME/okal-https-upgrade-XXXXXXXX")"
trap 'rm -rf "$work"' EXIT
git show "$old_commit:deploy/okal-local.Caddyfile" > "$work/old.Caddyfile"
git show "$old_commit:deploy/okal-local-proxy.service" > "$work/old.service"
for entry in \
  "deploy/okal-local.Caddyfile:/etc/okal/Caddyfile:$work/old.Caddyfile" \
  "deploy/okal-local-proxy.service:/etc/systemd/system/okal-local-proxy.service:$work/old.service"; do
  target="${entry#*:}"
  target="${target%%:*}"
  old="${entry##*:}"
  new="${entry%%:*}"
  if sudo test -e "$target" && \
     ! sudo cmp -s "$target" "$old" && \
     ! sudo cmp -s "$target" "$new"; then
    echo "STOP: Existing manually changed config at $target" >&2
    echo "Please review it first; nothing will be overwritten." >&2
    exit 1
  fi
done

caddy validate --config deploy/okal-local.Caddyfile --adapter caddyfile
if [[ -n "$(ss -H -lnt '( sport = :443 )')" ]] && \
   ! systemctl is-active --quiet okal-local-proxy.service; then
  echo "STOP: HTTPS port 443 is already in use" >&2
  exit 1
fi
curl --noproxy '*' -fsS --max-time 4 \
  -H "Host: okal" -H "Origin: https://okal" \
  http://127.0.0.1:8766/api/v1/health >/dev/null || {
  echo "STOP: Deploy latest OKAL backend before enabling HTTPS" >&2
  exit 1
}

# Refuse other port-80 listeners for a clean new installation.
if ! systemctl is-active --quiet okal-local-proxy.service && \
   [[ -n "$(ss -H -lnt '( sport = :80 )')" ]]; then
  echo "STOP: Port 80 already used" >&2
  exit 1
fi

sudo -v
# Only support exact local mapping; do not override other /etc/hosts entries.
if awk '$1 !~ /^#/ {for(i=2;i<=NF;i++) if($i=="okal" && $1!="127.0.0.1") bad=1} END{exit !bad}' /etc/hosts; then
  echo "STOP: Existing okal alias points outside loopback" >&2
  exit 1
fi
if ! awk '$1=="127.0.0.1" {for(i=2;i<=NF;i++) if($i=="okal") ok=1} END{exit !ok}' /etc/hosts; then
  hosts_backup="/etc/hosts.okal-pre-https-$(date +%Y%m%d-%H%M%S)"
  sudo cp -p /etc/hosts "$hosts_backup"
  printf '\n127.0.0.1 okal\n' | sudo tee -a /etc/hosts >/dev/null
  echo "Backed up hosts: $hosts_backup"
fi

backup="$(sudo mktemp -d /etc/okal-https-backup-XXXXXXXX)"
echo "System configuration backup: $backup"
if sudo test -f /etc/okal/Caddyfile; then
  sudo cp -p /etc/okal/Caddyfile "$backup/Caddyfile"
fi
if sudo test -f /etc/systemd/system/okal-local-proxy.service; then
  sudo cp -p /etc/systemd/system/okal-local-proxy.service "$backup/okal-local-proxy.service"
fi

sudo install -D -m 0644 deploy/okal-local.Caddyfile /etc/okal/Caddyfile
sudo install -D -m 0644 deploy/okal-local-proxy.service \
  /etc/systemd/system/okal-local-proxy.service
sudo systemctl daemon-reload
sudo systemctl enable --now okal-local-proxy.service
sudo systemctl restart okal-local-proxy.service

# Do NOT use curl -k or bypass verification. Export only the PUBLIC root
# certificate (never a root or intermediate private key).
cert="/var/lib/okal-local-proxy/caddy/pki/authorities/local/root.crt"
for attempt in {1..12}; do
  if sudo test -s "$cert"; then break; fi
  sleep 1
done
if ! sudo test -s "$cert"; then
  echo "STOP: Certificate root wasn't issued. Inspect service status." >&2
  echo "To rollback, restore saved config from $backup." >&2
  exit 1
fi

mkdir -p "$HOME/.local/share/okal-certs"
out="$HOME/.local/share/okal-certs/okal-local-ca.crt"
if [[ -e "$out" ]]; then
  if ! sudo cmp -s "$cert" "$out"; then
    echo "STOP: Different local CA exists at $out; do not overwrite" >&2
    exit 1
  fi
else
  sudo cat "$cert" > "$out"
  chmod 0600 "$out"
fi
curl --noproxy '*' --cacert "$out" -fsS --max-time 5 \
  https://okal/api/v1/health >/dev/null || {
  echo "STOP: HTTPS certificate failed identity/chain verification" >&2
  exit 1
}
echo "VERIFIED HTTPS: https://okal/"
echo "Public CA root: $out"
echo "Install this PUBLIC CA root into Firefox Authorities to remove its warning."
echo "Firefox: Settings > Privacy & Security > Certificates > View Certificates > Authorities > Import."
echo "Never use 'Accept Risk' or disable certificate verification."
echo "No tunnel or public port was opened. Port 443 must bind 127.0.0.1 only."
