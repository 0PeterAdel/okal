"""Render (never install) the explicitly authorized owner-home systemd carve-out.

Keep the base unit's strict system/home protections. Protect existing hidden
home entries and deployment code with deeper read-only mounts. The pre-existing
private StateDirectory remains writable through its deeper ReadWritePaths.
"""

import argparse
import os
from pathlib import Path


def quote(path):
    value = str(path)
    if any(ord(c) < 32 for c in value):
        raise ValueError("control_character_in_path")
    return '"' + value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(home, checkout, state):
    home, checkout, state = map(Path, (home, checkout, state))
    for path in (home, checkout, state):
        if not path.is_absolute() or path.resolve() != path or path.stat().st_uid != os.getuid():
            raise ValueError("absolute_owned_non_symlink_path_required")
    if home == Path("/") or home == checkout or home == state:
        raise ValueError("specific_home_required")
    if not checkout.is_relative_to(home) or not state.is_relative_to(home / ".local/state"):
        raise ValueError("deployment_and_private_state_must_be_inside_home")
    if not (checkout / "apps/core/src/okal_core").is_dir():
        raise ValueError("core_checkout_required")
    protected = {home / name for name in (
        ".config", ".ssh", ".gnupg", ".local", ".cache", ".pki", ".mozilla",
        ".codex", ".agents", ".aws", ".kube", ".docker", ".password-store",
    )}
    # Existing hidden files/directories include credentials for other local apps.
    protected.update(p for p in home.iterdir() if p.name.startswith("."))
    # Never use a broad action grant to modify the running application itself.
    protected.add(checkout)
    lines = [
        "# Owner-authorized Stage 3 scope. Does not grant tools or approvals.",
        "# Keep the installed unit's other directives and existing state carve-out.",
        "[Service]", "ProtectSystem=strict", "ProtectHome=read-only",
        "NoNewPrivileges=true", "ReadWritePaths=" + quote(home),
    ]
    lines += ["ReadOnlyPaths=-" + quote(p) for p in sorted(protected)]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-authorized-wide-home", action="store_true", required=True)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    print(render(args.home, args.checkout, args.state), end="")


if __name__ == "__main__":
    main()
