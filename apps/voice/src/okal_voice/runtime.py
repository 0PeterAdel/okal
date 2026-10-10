"""Private runtime state shared by the daemon, CLI, and Omarchy orb."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

from .contracts import VoicePhase, VoiceSnapshot


def runtime_dir() -> Path:
    configured = os.environ.get("XDG_RUNTIME_DIR")
    if not configured:
        raise RuntimeError("XDG_RUNTIME_DIR is required; refusing an unsafe /tmp socket")
    return Path(configured) / "okal/voice"


def ensure_private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    current = path.stat()
    if current.st_uid != os.getuid() or not stat.S_ISDIR(current.st_mode):
        raise PermissionError(f"unsafe runtime directory owner: {path}")
    if current.st_mode & 0o077:
        raise PermissionError(f"runtime directory must be owner-only: {path}")
    return path


class StateStore:
    def __init__(self, root: Path | None = None):
        self.root = ensure_private_dir(root or runtime_dir())
        self.state_path = self.root / "state.json"
        self.level_path = self.root / "level"
        self.route_path = self.root / "routes.jsonl"
        self.socket_path = self.root / "control.sock"

    def publish(self, snapshot: VoiceSnapshot) -> None:
        self._atomic_write(self.state_path, json.dumps(snapshot.as_dict(), ensure_ascii=False))

    def read(self) -> VoiceSnapshot:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            return VoiceSnapshot.from_dict(payload)
        except FileNotFoundError:
            return VoiceSnapshot.new(VoicePhase.IDLE)

    def write_level(self, value: float) -> None:
        self._atomic_write(self.level_path, f"{max(0.0, min(1.0, value)):.4f}\n")

    def append_route(self, payload: dict) -> None:
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        descriptor = os.open(self.route_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(descriptor, line.encode("utf-8"))
        finally:
            os.close(descriptor)
        self.route_path.chmod(0o600)

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            path.chmod(0o600)
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            Path(temporary).unlink(missing_ok=True)
            raise
