import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/run-voice-lab.sh"


class CudaVoiceLabTests(unittest.TestCase):
    def test_sets_isolated_cuda12_libraries_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "scripts" / SCRIPT.name
            script.parent.mkdir()
            shutil.copyfile(SCRIPT, script)
            bin_dir = root / ".venv-okal-voice" / "bin"
            bin_dir.mkdir(parents=True)
            site = root / "site"
            python = bin_dir / "python"
            python.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = '-c' ]; then printf '%s\\n' \"$FAKE_SITE\"; exit; fi\n"
                "printf '%s\\n' \"$LD_LIBRARY_PATH\" > \"$LAB_LOG\"\n"
                "printf '%s\\n' \"$PYTHONPATH\" >> \"$LAB_LOG\"\n"
                "printf '%s\\n' \"$*\" >> \"$LAB_LOG\"\n",
                encoding="utf-8",
            )
            python.chmod(0o755)
            env = dict(os.environ, FAKE_SITE=str(site), LAB_LOG=str(root / "lab.log"),
                       LD_LIBRARY_PATH="/existing", PYTHONPATH="/previous", OKAL_STT_DEVICE="cuda")
            command = ["bash", str(script), "voice-lab-audio", "--language-hints", "--output", "results.json"]

            missing = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(missing.returncode, 1)
            self.assertIn("CUDA 12 cuBLAS and cuDNN 9", missing.stderr)
            self.assertFalse((root / "lab.log").exists())

            cublas = site / "nvidia" / "cublas" / "lib"
            cudnn = site / "nvidia" / "cudnn" / "lib"
            cublas.mkdir(parents=True)
            cudnn.mkdir(parents=True)
            (cublas / "libcublas.so.12").touch()
            (cudnn / "libcudnn.so.9").touch()
            success = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(success.returncode, 0, success.stderr)
            self.assertEqual((root / "lab.log").read_text().splitlines(), [
                f"{cublas}:{cudnn}:/existing",
                f"{root}/apps/voice/src:/previous",
                "-m okal_voice.voice_lab voice-lab-audio --language-hints --output results.json",
            ])


if __name__ == "__main__":
    unittest.main()
