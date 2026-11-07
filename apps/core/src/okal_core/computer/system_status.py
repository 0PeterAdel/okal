"""Read-only, bounded inventory for owner-requested local device diagnostics.

Disk size is from Linux sysfs, mounted space from statvfs. These are two
different views (block devices vs filesystems), not a claim about SATA bays.
No shell, privileged operation, network request, or directory traversal.
"""
from pathlib import Path
import os
import re

BLOCK_NAMES = re.compile(r"^(?:sd[a-z]+|nvme[0-9]+n[0-9]+|mmcblk[0-9]+|vd[a-z]+|xvd[a-z]+)$")
MOUNT_PREFIXES = ("/mnt/", "/media/", "/run/media/")


def _integer(path):
    try:
        value = int(path.read_text(encoding="ascii").strip())
        return value if value >= 0 else None
    except (OSError, ValueError, OverflowError):
        return None


def disk_status(block_root=Path("/sys/class/block"), mounts_path=Path("/proc/self/mountinfo")):
    """Return exact bounded non-sensitive device and mounted-space evidence."""
    devices = []
    try:
        names = sorted(p.name for p in block_root.iterdir() if BLOCK_NAMES.fullmatch(p.name))
    except OSError:
        names = []
    for name in names[:32]:
        base = block_root / name
        if (base / "partition").exists():
            continue
        sectors = _integer(base / "size")
        removable = _integer(base / "removable")
        devices.append({
            "name": name,
            "size_bytes": sectors * 512 if sectors is not None else None,
            "removable": removable == 1 if removable is not None else None,
        })

    mounts = []
    seen = set()
    try:
        lines = mounts_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            before, after = line.split(" - ", 1)
            fields = before.split()
            fs = after.split()
            mountpoint = fields[4]
            # Never enumerate secrets/private systemd namespace bind mounts.
            if (mountpoint not in {"/", "/home"} and not
                    mountpoint.startswith(MOUNT_PREFIXES)):
                continue
            if mountpoint in seen or fs[0] in {"tmpfs", "overlay", "proc", "sysfs"}:
                continue
            # Restrict processing to normal block-backed mount sources.
            if len(fs) < 2 or not fs[1].startswith("/dev/"):
                continue
            stats = os.statvfs(mountpoint)
            total = stats.f_blocks * stats.f_frsize
            free = stats.f_bavail * stats.f_frsize
            mounts.append({"mountpoint": mountpoint, "total_bytes": total, "available_bytes": free})
            seen.add(mountpoint)
            if len(mounts) >= 16:
                break
        except (ValueError, IndexError, OSError):
            continue
    if "/" not in seen:
        try:
            stats = os.statvfs("/")
            mounts.insert(0, {
                "mountpoint": "/",
                "total_bytes": stats.f_blocks * stats.f_frsize,
                "available_bytes": stats.f_bavail * stats.f_frsize,
            })
        except OSError:
            pass
    return {
        "block_device_count": len(devices),
        "block_devices": devices,
        "mounted_space": mounts[:16],
        "inventory_limited": len(names) > 32,
        "note": "Block devices are not partitions; mounts report space visible to the running service.",
    }
