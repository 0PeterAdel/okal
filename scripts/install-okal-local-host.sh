#!/usr/bin/env bash
# The supported single entrypoint installs or upgrades private HTTPS.
set -euo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$repo/scripts/upgrade-okal-local-https.sh" "$@"
