"""Owner-approved terminal argv inside an isolated no-network user namespace.

Unlike system.command's named profiles, this receives an exact owner-requested
argv, never a model-generated executable script. All runs are consequential,
require the current exact-plan approval, and cannot access the broad home tree
or the Core's private state even when file tools have a home-wide grant.
"""
import os
from pathlib import Path
import re
import shutil

from .contracts import Denied
from .process import run

BINARY = re.compile(r"^/usr/bin/[A-Za-z0-9_.+\-]{1,100}$")
BLOCKED = {"sudo", "su", "doas", "pkexec", "mount", "umount", "setcap", "chown", "chmod", "bwrap"}


def validate_argv(args):
    argv = args.argv
    if not (1 <= len(argv) <= 20):
        raise Denied("bounded_terminal_argv_required")
    if not BINARY.fullmatch(argv[0]) or Path(argv[0]).name in BLOCKED:
        raise Denied("unprivileged_usr_bin_executable_required")
    for token in argv:
        if (not isinstance(token, str) or not token or len(token) > 2000
                or any(ord(ch) < 32 and ch not in "\t\n" for ch in token)):
            raise Denied("invalid_terminal_argument")
    return argv


def permitted_roots(ctx):
    """Wide home/ancestor grants are NEVER command mounts."""
    roots = []
    home = Path.home()
    state = Path(ctx.store.directory)
    for grant in ctx.policy.roots:
        path = Path(grant.root)
        if home.is_relative_to(path) or state.is_relative_to(path):
            continue
        # A terminal mount must not expose hidden ancestors or private state.
        if any(part.startswith(".") for part in path.parts[1:]):
            continue
        roots.append(grant)
    return roots


def preview(ctx, args):
    argv = validate_argv(args)
    if not shutil.which("bwrap"):
        raise Denied("command_sandbox_unavailable")
    return {
        "resources": [],
        "argv": argv,
        "sandbox": "No network; unprivileged namespace; /usr,/sys and narrow owner-granted roots only.",
        "mounted_roots": [g.root for g in permitted_roots(ctx)],
        "owner_approval_required": True,
    }


def execute(ctx, args):
    from .registry import result

    details = preview(ctx, args)
    ctx.check()
    argv = [
        "/usr/bin/bwrap", "--unshare-all", "--die-with-parent",
        "--new-session",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/sys", "/sys",
        "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib", "/lib64",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--clearenv", "--setenv", "PATH", "/usr/bin:/bin",
        "--setenv", "HOME", "/tmp",
    ]
    for grant in permitted_roots(ctx):
        argv.extend(["--bind" if grant.write else "--ro-bind", grant.root, grant.root])
    argv.extend(["--chdir", "/tmp", "--", *details["argv"]])
    output = run(argv, ctx.check, timeout=20).decode("utf-8", errors="replace")[:10000]
    from ..intelligence import SECRET
    if SECRET.search(output):
        raise Denied("credential_like_output_rejected")
    return result(
        "Owner-approved command exited successfully in a no-network sandbox.",
        {"stdout": output, "argv": details["argv"], "sandbox": details["sandbox"]},
    )
