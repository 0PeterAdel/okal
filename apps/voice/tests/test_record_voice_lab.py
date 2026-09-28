import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/record-voice-lab.sh"


class RecorderTests(unittest.TestCase):
    def test_prompts_use_terminal_input_instead_of_case_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            binaries.mkdir()
            for name, body in {
                "python3": "printf 'ar_01\\tاختبار التسجيل\\n'\n",
                "pw-record": "printf 'WAV' > \"${@: -1}\"\n",
                "ffprobe": "printf '1.0\\n'\n",
            }.items():
                path = binaries / name
                path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
                path.chmod(0o755)

            audio = root / "recordings/ar_01.wav"
            env = dict(os.environ, PATH=f"{binaries}:{os.environ['PATH']}")
            process = subprocess.Popen(
                ["bash", str(SCRIPT), str(audio.parent)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            try:
                assert process.stdin is not None
                process.stdin.write("\n")
                process.stdin.flush()
                deadline = time.monotonic() + 3
                while not audio.is_file() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(audio.is_file(), "recorder did not wait for the first Enter")
                output, errors = process.communicate(input="\n", timeout=5)
                self.assertEqual(process.returncode, 0, errors)
                self.assertIn("Saved ar_01.wav", output)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()


if __name__ == "__main__":
    unittest.main()
