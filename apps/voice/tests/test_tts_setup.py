"""The isolated TTS installer must request a matching CUDA wheel pair."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/run-tts-voice-lab.sh"


class TtsSetupTests(unittest.TestCase):
    def test_setup_uses_matching_python_compatible_cuda_wheels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "scripts/run-tts-voice-lab.sh"
            script.parent.mkdir()
            shutil.copy2(SCRIPT, script)
            python = root / ".venv-okal-voice/bin/python"
            python.parent.mkdir(parents=True)
            python.write_text(
                '#!/bin/sh\n'
                'if [ "$1" = -m ] && [ "$2" = venv ]; then\n'
                '  mkdir -p "$3/bin"; cp "$0" "$3/bin/python"; exit 0\n'
                'fi\n'
                'printf "%s\\n" "$*" >> "$OKAL_TEST_LOG"\n',
                encoding="utf-8",
            )
            python.chmod(0o755)
            log = root / "pip.log"
            env = {**os.environ, "OKAL_TEST_LOG": str(log)}
            subprocess.run(["bash", str(script), "--setup"], check=True, env=env, capture_output=True, text=True)
            commands = log.read_text(encoding="utf-8")
            self.assertIn("torch==2.9.1+cu126 torchaudio==2.9.1+cu126", commands)
            self.assertIn("https://download.pytorch.org/whl/cu126", commands)
            self.assertNotIn("cu121", commands)


if __name__ == "__main__":
    unittest.main()
