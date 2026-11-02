#!/usr/bin/env bash
# Explicit owner-operated, one-time MIT FullCalendar Standard 6.1.22 install.
# Runtime browser remains 100% localhost, with zero CDN requests.
set -euo pipefail
umask 077

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
version="6.1.22"
destination="$repo/apps/core/src/okal_core/static/vendor/fullcalendar/index.global.min.js"
license="$repo/apps/core/src/okal_core/static/vendor/fullcalendar.LICENSE.md"
test -f "$license" || { echo "Missing MIT license notice" >&2; exit 1; }
command -v npm >/dev/null || { echo "npm required for one-time vendor install" >&2; exit 1; }
command -v tar >/dev/null || { echo "tar required" >&2; exit 1; }
work="$(mktemp -d "$HOME/okal-fullcalendar-install-XXXXXXXX")"
trap 'rm -rf "$work"' EXIT
echo "Fetching pinned MIT FullCalendar Standard $version via npm pack"
npm pack --ignore-scripts --pack-destination "$work" "fullcalendar@$version" >/dev/null
package="$work/fullcalendar-$version.tgz"
test -f "$package" || { echo "Pinned package not found" >&2; exit 1; }
if ! tar -tzf "$package" | grep -Fxq "package/index.global.min.js"; then
  echo "Expected official global bundle missing: do not install" >&2
  exit 1
fi
mkdir -p "$(dirname "$destination")"
tar -xOf "$package" package/index.global.min.js > "$work/bundle.js"
test "$(wc -c < "$work/bundle.js")" -gt 30000 || {
  echo "Unexpected tiny bundle" >&2; exit 1;
}
install -m 0644 "$work/bundle.js" "$destination"
printf 'FullCalendar Standard %s installed locally: ' "$version"
sha256sum "$destination"
echo "No runtime CDN dependencies. License: $license"
