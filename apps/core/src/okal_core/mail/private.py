"""Local private config and credentials. Never return these through HTTP."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat
import tempfile

from ..store import private_directory
from .contracts import Config, MailError


def read_private(path: Path) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        info = os.fstat(f.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise MailError("unsafe_private_file")
        text = f.read(65537)
        if len(text) > 65536:
            raise MailError("private_file_too_large")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise MailError("invalid_private_file")
        return data


def write_private(path: Path, data: dict):
    private_directory(path.parent)
    if path.exists() or path.is_symlink():
        read_private(path)
    fd, name = tempfile.mkstemp(prefix=".mail-write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)  # Only this invocation's exact temporary file.


def root(store) -> Path:
    return private_directory(store.directory / "mail")


def config(store) -> Config:
    return Config.model_validate(read_private(root(store) / "config.json"))


@contextmanager
def locked(store):
    path = root(store) / "operation.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        info = os.fstat(f.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise MailError("unsafe_lock_file")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise MailError("mail_operation_already_running") from None
        yield
