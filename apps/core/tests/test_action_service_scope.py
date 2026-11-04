"""Security regression for broad owner scopes and immutable service code."""

import importlib.util
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest

from okal_core.computer.contracts import Denied, Grant
from okal_core.computer.files import Files
from okal_core.computer.registry import command_scope

spec = importlib.util.spec_from_file_location("scope_renderer", Path(__file__).parents[1] / "tools/render_action_service_scope.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class ScopeTests(unittest.TestCase):
    def test_code_write_denied_even_with_ancestor_grant(self):
        # Staged archives can live under .local; use a visible synthetic code
        # root to exercise this guard independently of hidden-path protection.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "code"
            files = Files([Grant(root=tmp, write=True)], "/unused-state")
            with patch("okal_core.computer.files.CODE_ROOT", root):
                files.parts(str(root / "AGENTS.md"))
                with self.assertRaisesRegex(Denied, "application_code_is_read_only"):
                    files.parts(str(root / "AGENTS.md"), write=True)

    def test_render_preserves_hardening_and_protects_hidden_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            checkout = home / "Projects/Okal"
            (checkout / "apps/core/src/okal_core").mkdir(parents=True)
            state = home / ".local/state/okal-core"
            state.mkdir(parents=True)
            (home / ".other-app-token").touch(mode=0o600)
            rendered = renderer.render(home, checkout, state)
            self.assertIn("ProtectSystem=strict", rendered)
            self.assertIn("ProtectHome=read-only", rendered)
            self.assertIn("NoNewPrivileges=true", rendered)
            self.assertIn("ReadWritePaths=" + renderer.quote(home), rendered)
            for p in (home / ".other-app-token", home / ".ssh", home / ".local", checkout):
                self.assertIn("ReadOnlyPaths=-" + renderer.quote(p), rendered)
            self.assertNotIn("ReadWritePaths=\n", rendered)
            self.assertNotIn("Environment=", rendered)
            alias = home / "alias"
            alias.symlink_to(checkout, target_is_directory=True)
            with self.assertRaises(ValueError):
                renderer.render(home, alias, state)
            with self.assertRaises(ValueError):
                renderer.render(Path("/"), checkout, state)

    def test_command_mount_never_exposes_broad_home_or_private_state(self):
        for root, state in ((Path.home(), Path.home() / ".local/state/core"),
                            (Path("/tmp/synthetic"), Path("/tmp/synthetic/state"))):
            ctx = SimpleNamespace(policy=SimpleNamespace(roots=[Grant(root=str(root))]),
                                  store=SimpleNamespace(directory=state))
            with self.assertRaisesRegex(Denied, "command_scope_includes_private_home_or_state"):
                command_scope(ctx)
        ctx = SimpleNamespace(policy=SimpleNamespace(roots=[Grant(root="/tmp/synthetic/documents")]),
                              store=SimpleNamespace(directory=Path("/tmp/synthetic/state")))
        command_scope(ctx)

    def test_unit_path_escaping(self):
        self.assertEqual(renderer.quote('/home/a%b/"quoted"'), '\"/home/a%%b/\\\"quoted\\\"\"')
        with self.assertRaises(ValueError):
            renderer.quote("/home/bad\nExecStart=/bin/false")
