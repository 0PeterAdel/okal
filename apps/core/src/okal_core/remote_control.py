"""Owner-only local UI bridge to existing opt-in Cloudflare Tunnel CLI.

Never accepts hostnames, shell commands, tunnel tokens, or arbitrary arguments
from the browser. Requires a separate short-lived owner control key issued in
a local terminal; a normal OKAL browser/read session cannot activate remote.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time

CONFIG_DIR = Path.home() / ".config" / "okal"
CONTROL_FILE = CONFIG_DIR / "remote-ui-key.json"
ROOT = Path(__file__).resolve().parents[4]
REMOTE_CLI = ROOT / "scripts" / "okal-remote.py"
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")


def issue_control_key():
    """Return a 24-hour control key ONCE to the local operator terminal."""
    CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = CONFIG_DIR.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077 or CONFIG_DIR.is_symlink()):
        raise ValueError("remote_control_unsafe_directory")
    if CONTROL_FILE.is_symlink():
        raise ValueError("remote_control_unsafe_key_file")
    secret = secrets.token_urlsafe(32)
    record = json.dumps({
        "verifier": hashlib.sha256(secret.encode("ascii")).hexdigest(),
        "expires_at": int(time.time()) + 24 * 3600,
    }, separators=(",", ":"))
    tmp = CONTROL_FILE.with_name(CONTROL_FILE.name + ".new")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(record)
        os.replace(tmp, CONTROL_FILE)
        os.chmod(CONTROL_FILE, 0o600)
    finally:
        if tmp.exists():
            tmp.unlink()
    return secret


def key_issued():
    try:
        if CONTROL_FILE.is_symlink():
            return False
        info = CONTROL_FILE.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077):
            return False
        payload = json.loads(CONTROL_FILE.read_text(encoding="utf-8"))
        return (int(payload.get("expires_at", 0)) > int(time.time())
                and isinstance(payload.get("verifier"), str)
                and bool(re.fullmatch(r"[0-9a-f]{64}", payload["verifier"])))
    except (OSError, ValueError, TypeError, KeyError):
        return False


def authorize_control_key(value):
    if not isinstance(value, str) or not TOKEN_PATTERN.fullmatch(value):
        return False
    if not key_issued():
        return False
    try:
        expected = json.loads(CONTROL_FILE.read_text(encoding="utf-8"))["verifier"]
    except (OSError, ValueError, KeyError):
        return False
    return secrets.compare_digest(
        hashlib.sha256(value.encode("ascii")).hexdigest(), expected
    )


def status():
    """Read owner-safe values from existing CLI; do not claim public reachability."""
    try:
        proc = subprocess.run(
            [sys.executable, str(REMOTE_CLI), "status"],
            capture_output=True, text=True, check=False, timeout=7,
        )
        if proc.returncode:
            raise ValueError("remote_status_unavailable")
        data = json.loads(proc.stdout)
        return {
            "configured": data["configured"] is True,
            "tunnel_running": data["tunnel_running"] is True,
            "external_url_if_configured": (
                data.get("external_url_if_configured")
                if isinstance(data.get("external_url_if_configured"), str) else None
            ),
            "public_reachability_verified": False,
            "remote_auto_start": False,
            "owner_control_key_issued": key_issued(),
        }
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        raise ValueError("remote_status_unavailable") from None


def switch(action, control_key, confirm_access_policy):
    """Launch owner-approved on/off in a separate transient user systemd unit."""
    if action not in ("on", "off") or type(confirm_access_policy) is not bool:
        raise ValueError("invalid_remote_action")
    if not authorize_control_key(control_key):
        raise PermissionError("remote_owner_control_key_required")
    if action == "on" and confirm_access_policy is not True:
        raise ValueError("cloudflare_access_policy_confirmation_required")
    current = status()
    if action == "on" and not current["configured"]:
        raise ValueError("remote_not_configured")
    # systemd-run puts the controller in a separate cgroup so restarting the
    # OKAL Core service cannot kill its own remote on/off transition.
    unit = "okal-remote-ui-" + secrets.token_hex(6)
    args = ["systemd-run", "--user", "--collect", "--quiet",
            "--unit", unit, sys.executable, str(REMOTE_CLI), action]
    if action == "on":
        args.append("--confirm-access-policy")
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, check=False, timeout=8
        )
        if result.returncode:
            raise ValueError("remote_action_launch_failed")
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("remote_action_launch_failed") from None
    return {"state": "accepted_not_confirmed", "action": action,
            "public_reachability_verified": False}
