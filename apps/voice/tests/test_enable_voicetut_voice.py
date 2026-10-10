"""Opt-in setup must persist one voice choice without a model download."""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/enable-voicetut-voice.sh"


class EnableVoiceTutTests(unittest.TestCase):
    def test_repeated_enable_keeps_other_settings_and_one_asmaa_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout, home, bin_dir = (root / name for name in ("checkout", "home", "bin"))
            home.mkdir()
            bin_dir.mkdir()
            script = checkout / "scripts/enable-voicetut-voice.sh"
            script.parent.mkdir(parents=True)
            shutil.copy2(SCRIPT, script)
            for venv in (".venv-okal-voice", ".venv-okal-tts-lab"):
                python = checkout / venv / "bin/python"
                python.parent.mkdir(parents=True)
                python.symlink_to(sys.executable)
            preflight = script.parent / "run-tts-voice-lab.sh"
            preflight.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            install = script.parent / "install-local-voice.sh"
            install.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            for command in ("systemctl",):
                stub = bin_dir / command
                stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                stub.chmod(0o755)
            okal = home / ".local/bin/okal"
            okal.parent.mkdir(parents=True)
            okal.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            okal.chmod(0o755)
            settings = home / ".config/okal/voice.env"
            settings.parent.mkdir(parents=True)
            settings.write_text("OKAL_STT_DEVICE=cpu\nOKAL_VOICETUT_ENABLED=0\n", encoding="utf-8")
            env = {**os.environ, "HOME": str(home), "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            for _ in range(2):
                subprocess.run(["bash", str(script)], env=env, check=True, capture_output=True, text=True)
            content = settings.read_text(encoding="utf-8")
            self.assertIn("OKAL_STT_DEVICE=cpu", content)
            self.assertEqual(content.count("OKAL_VOICETUT_ENABLED="), 1)
            self.assertIn("OKAL_VOICETUT_ENABLED=1", content)
            self.assertIn(f"OKAL_VOICETUT_PYTHON={checkout}/.venv-okal-tts-lab/bin/python", content)
            self.assertEqual(stat.S_IMODE(settings.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
