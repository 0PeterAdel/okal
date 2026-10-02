"""Exercise the installer without touching the real user session."""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class InstallLocalVoiceTests(unittest.TestCase):
    def test_installed_launcher_uses_voice_python_and_preserves_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout = root / "checkout"
            home = root / "home"
            bin_dir = root / "bin"
            python = checkout / ".venv-okal-voice/bin/python"
            python.parent.mkdir(parents=True)
            home.mkdir()
            bin_dir.mkdir()
            for relative in (
                "scripts/install-local-voice.sh",
                "apps/voice/share/okal-voice.service",
                "apps/voice/share/bindings.lua.snippet",
                "apps/voice/plugin/okal.voice/manifest.json",
                "apps/voice/plugin/okal.voice/VoiceOrb.qml",
            ):
                target = checkout / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            shutil.copytree(ROOT / "apps/voice/src/okal_voice", checkout / "apps/voice/src/okal_voice")
            python.write_text("#!/bin/sh\nif [ \"$1\" = -c ]; then echo /tmp/fake-site-packages; fi\n", encoding="utf-8")
            python.chmod(0o755)
            for command in ("pw-record", "systemctl", "hyprctl"):
                stub = bin_dir / command
                stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                stub.chmod(0o755)
            env = {**os.environ, "HOME": str(home), "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            script = checkout / "scripts/install-local-voice.sh"
            subprocess.run(["bash", str(script)], env=env, check=True, capture_output=True, text=True)
            settings = home / ".config/okal/voice.env"
            self.assertEqual(stat.S_IMODE(settings.stat().st_mode), 0o600)
            self.assertIn("OKAL_STT_LANGUAGE_MODE=dual", settings.read_text(encoding="utf-8"))
            launcher = (home / ".local/bin/okal").read_text(encoding="utf-8")
            self.assertIn(f'exec "{python}" -m okal_voice.cli', launcher)
            self.assertIn("libcublas.so.12", launcher)
            settings.write_text("OKAL_STT_DEVICE=cpu\n", encoding="utf-8")
            subprocess.run(["bash", str(script)], env=env, check=True, capture_output=True, text=True)
            self.assertEqual(settings.read_text(encoding="utf-8"), "OKAL_STT_DEVICE=cpu\n")


if __name__ == "__main__":
    unittest.main()
