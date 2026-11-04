#!/usr/bin/env bash
# Install the owner's approved original PNG as a private local OKAL brand asset.
# Does not modify a checkout, main, or running services.
set -euo pipefail
umask 077
if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: bash scripts/install-okal-master.sh ORIGINAL.png [STATE_DIR]" >&2
  exit 2
fi
src="$1"
state="$HOME/.local/state/okal-core"
if [[ $# -eq 2 ]]; then state="$2"; fi
python3 - "$src" "$state" <<'PY'
import os
import stat
import struct
import sys
from pathlib import Path
import tempfile

source = Path(sys.argv[1]).expanduser().absolute()
state = Path(sys.argv[2]).expanduser().absolute()
if source.is_symlink() or not source.is_file():
    raise SystemExit("STOP: logo must be a real local PNG file")
with source.open("rb") as inp:
    header = inp.read(24)
if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
    raise SystemExit("STOP: approved master must be a PNG")
width, height = struct.unpack(">II", header[16:24])
size = source.stat().st_size
if min(width, height) < 750 or size < 10_000 or size > 8_000_000:
    raise SystemExit("STOP: original master must be high-resolution (>=750px), under 8MB")
if state.is_symlink() or not state.is_dir():
    raise SystemExit("STOP: expected existing private OKAL state directory")
info = state.stat()
if info.st_uid != os.getuid() or info.st_mode & 0o077:
    raise SystemExit("STOP: OKAL state directory must be owner-only")
brand = state / "brand"
brand.mkdir(mode=0o700, exist_ok=True)
info = brand.lstat()
if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
    raise SystemExit("STOP: brand directory must be owner-only")
dest = brand / "okal-approved-master.png"
if dest.is_symlink():
    raise SystemExit("STOP: destination must not be a symlink")
fd, temp = tempfile.mkstemp(prefix=".okal-master-", suffix=".png", dir=brand)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as output, source.open("rb") as inp:
        while chunk := inp.read(1024 * 1024):
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temp, dest)
finally:
    if os.path.exists(temp):
        os.unlink(temp)
print(f"Installed original OKAL master ({width}x{height}) into private state.")
print("Browser will load same-origin /assets/okal-identity; no repository changes.")
PY
