"""Linux directory-fd confinement, no-follow traversal and no-clobber writes."""

from contextlib import contextmanager
import ctypes
import hashlib
import os
from pathlib import Path
import stat

from .contracts import Denied

MAX_FILE = 8 * 1024 * 1024


class Files:
    def __init__(self, roots, state_directory):
        self.roots = roots
        self.state_directory = str(state_directory)

    def parts(self, path, write=False, internal=False):
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or len(path) > 1024
            or "\x00" in path
        ):
            raise Denied("absolute_scoped_path_required")
        parts = Path(path).parts
        if ".." in parts or any(
            p.startswith(".") for p in parts[1:] if p != "." and not internal
        ):
            raise Denied("hidden_or_parent_paths_denied")
        normalized = os.path.normpath(path)
        if normalized == self.state_directory or normalized.startswith(
            self.state_directory + "/"
        ):
            raise Denied("runtime_state_is_not_a_document_scope")
        candidates = [
            g
            for g in self.roots
            if (not write or g.write)
            and (
                normalized == g.root or normalized.startswith(g.root.rstrip("/") + "/")
            )
        ]
        if not candidates:
            raise Denied("path_outside_grant")
        return normalized, parts

    @contextmanager
    def parent(self, path, write=False, internal=False):
        normalized, parts = self.parts(path, write, internal)
        if normalized == "/":
            raise Denied("root_directory_denied")
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for component in parts[1:-1]:
                other = os.open(
                    component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
                os.close(fd)
                fd = other
            yield fd, parts[-1]
        finally:
            os.close(fd)

    @contextmanager
    def directory(self, path, write=False):
        with self.parent(path, write) as (parent, name):
            fd = os.open(
                name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
            )
            try:
                if os.fstat(fd).st_uid != os.getuid():
                    raise Denied("directory_not_owner_owned")
                yield fd
            finally:
                os.close(fd)

    def read(self, path):
        with self.parent(path) as (parent, name):
            fd = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
            )
            try:
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or info.st_nlink != 1
                ):
                    raise Denied("only_owner_regular_single_link_files")
                if info.st_size > MAX_FILE:
                    raise ValueError("file_size_limit_8mib")
                chunks = []
                size = 0
                while True:
                    chunk = os.read(fd, 65536)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_FILE:
                        raise ValueError("file_grew_beyond_limit")
                    chunks.append(chunk)
                if os.fstat(fd).st_mtime_ns != info.st_mtime_ns:
                    raise ValueError("file_changed_while_reading")
                return b"".join(chunks)
            finally:
                os.close(fd)

    def snapshot(self, path, write=False, internal=False):
        self.parts(path, write, internal)
        try:
            with self.parent(path, write, internal) as (parent, name):
                info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid():
                    raise Denied("symlink_or_foreign_file")
                if stat.S_ISDIR(info.st_mode):
                    return dict(
                        path=path,
                        kind="directory",
                        device=info.st_dev,
                        inode=info.st_ino,
                    )
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise Denied("special_or_linked_file")
                data = self.read_internal(path) if internal else self.read(path)
                return dict(
                    path=path,
                    kind="file",
                    size=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                    device=info.st_dev,
                    inode=info.st_ino,
                    mtime_ns=info.st_mtime_ns,
                )
        except FileNotFoundError:
            return dict(path=path, kind="missing")

    def read_internal(self, path):
        # Recovery files are private, but only the receipt-owned exact path is
        # passed here; ordinary model paths may never request hidden locations.
        with self.parent(path, internal=True) as (parent, name):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or info.st_nlink != 1
                    or info.st_size > MAX_FILE
                ):
                    raise Denied("invalid_recovery_file")
                return os.read(fd, MAX_FILE + 1)
            finally:
                os.close(fd)

    def check(self, snapshot):
        if self.snapshot(snapshot["path"]) != snapshot:
            raise ValueError("preview_resource_changed")

    def write(self, path, data):
        if len(data) > MAX_FILE:
            raise ValueError("file_size_limit_8mib")
        with self.parent(path, True) as (parent, name):
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.fsync(parent)
            except BaseException:
                # Retain partial files for reconciliation; never remove a path
                # whose ownership may have changed during an interrupted write.
                raise
        return self.snapshot(path)

    def mkdir(self, path):
        with self.parent(path, True) as (parent, name):
            os.mkdir(name, 0o700, dir_fd=parent)
            os.fsync(parent)
        return self.snapshot(path)

    def move(self, source, destination, internal=False):
        # renameat2 NOREPLACE is atomic and never overwrites a raced-in file.
        with (
            self.parent(source, True, internal) as (src, name),
            self.parent(destination, True, internal) as (dst, target),
        ):
            libc = ctypes.CDLL(None, use_errno=True)
            operation = getattr(libc, "renameat2", None)
            if operation is None:
                raise ValueError("atomic_noreplace_unavailable")
            if operation(src, os.fsencode(name), dst, os.fsencode(target), 1) != 0:
                code = ctypes.get_errno()
                raise OSError(code, os.strerror(code))
            os.fsync(src)
            os.fsync(dst)

    def entries(self, path, query="", recursive=False, check=lambda: None):
        rows = []
        limited = False
        visited = 0

        def walk(directory, depth=0):
            nonlocal limited, visited
            check()
            with self.directory(directory) as fd:
                for name in sorted(os.listdir(fd)):
                    check()
                    visited += 1
                    if visited > 1000 or len(rows) >= 200:
                        limited = True
                        return
                    if name.startswith("."):
                        continue
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if info.st_uid != os.getuid() or stat.S_ISLNK(info.st_mode):
                        continue
                    child = directory.rstrip("/") + "/" + name
                    kind = (
                        "directory"
                        if stat.S_ISDIR(info.st_mode)
                        else "file"
                        if stat.S_ISREG(info.st_mode)
                        else "unsupported"
                    )
                    if query.casefold() in name.casefold():
                        rows.append(
                            dict(
                                path=child,
                                kind=kind,
                                size=info.st_size,
                                modified_at=int(info.st_mtime),
                            )
                        )
                    if recursive and kind == "directory" and depth < 5:
                        walk(child, depth + 1)
                    if limited:
                        return

        walk(path)
        return rows, limited
