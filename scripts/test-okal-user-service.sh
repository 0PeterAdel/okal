#!/usr/bin/env bash
# Synthetic portable unit install smoke: never contact the real user manager.
set -euo pipefail
umask 077

root="$(mktemp -d)"
trap 'rm -rf -- "$root"' EXIT
repo="$root/fresh-okal"
home="$root/new-user"
mkdir -p "$repo/scripts" "$repo/deploy" "$repo/.venv-okal-core/bin" "$home" "$root/bin"
cp scripts/install-okal-user-service.sh "$repo/scripts/"
cp deploy/okal-core.service "$repo/deploy/"
printf '#!/bin/sh\nexit 0\n' > "$repo/.venv-okal-core/bin/python"
printf '#!/bin/sh\nexit 0\n' > "$repo/scripts/run-okal-core.sh"
chmod +x "$repo/.venv-okal-core/bin/python" "$repo/scripts/run-okal-core.sh"

# Pretend the user manager is absent. The script may inspect, never start it.
cat > "$root/bin/systemctl" <<'FAKE_SYSTEMCTL'
#!/bin/sh
printf "%s\n" "$*" >> "$HOME/systemctl.calls"
exit 1
FAKE_SYSTEMCTL
chmod +x "$root/bin/systemctl"

run_installer(){
  env -u XDG_CONFIG_HOME HOME="$home" PATH="$root/bin:$PATH" \
    bash "$repo/scripts/install-okal-user-service.sh"
}
unit="$home/.config/systemd/user/okal-core.service"
run_installer
test -f "$unit"
grep -Fx "WorkingDirectory=$repo" "$unit"
grep -Fx "ExecStart=/bin/bash $repo/scripts/run-okal-core.sh serve" "$unit"
grep -Fx 'ProtectSystem=strict' "$unit"
grep -Fx 'ProtectHome=read-only' "$unit"
grep -Fx 'NoNewPrivileges=true' "$unit"
test "$(stat -c '%a' "$unit")" = "644"
test -f "$home/systemctl.calls"
test "$(wc -l < "$home/systemctl.calls")" -eq 1
grep -Fx -- '--user cat okal-core.service' "$home/systemctl.calls"

first="$(sha256sum "$unit")"
run_installer
test "$first" = "$(sha256sum "$unit")"
test "$(wc -l < "$home/systemctl.calls")" -eq 1

# A changed user-owned unit must NEVER be modified, enabled or replaced.
printf '\n# custom user content\n' >> "$unit"
current="$(sha256sum "$unit")"
if run_installer >/dev/null 2>&1; then
  echo "FAIL: overwrote custom unit" >&2
  exit 1
fi
test "$current" = "$(sha256sum "$unit")"

# Symlinked units are refused.
rm -- "$unit"
ln -s "$repo/deploy/okal-core.service" "$unit"
if run_installer >/dev/null 2>&1; then
  echo "FAIL: accepted symlinked unit" >&2
  exit 1
fi
test -L "$unit"

# A path needing systemd escaping must fail safely with zero changes.
mv "$repo" "$root/fresh okal"
if env -u XDG_CONFIG_HOME HOME="$home" PATH="$root/bin:$PATH" \
     bash "$root/fresh okal/scripts/install-okal-user-service.sh" >/dev/null 2>&1; then
  echo "FAIL: accepted unsupported path characters" >&2
  exit 1
fi

echo 'PASS: portable unit installation is opt-in, idempotent and non-destructive'
