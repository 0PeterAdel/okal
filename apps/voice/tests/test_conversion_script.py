import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/convert-egyptian-whisper-to-ct2.sh"


class ConversionScriptTests(unittest.TestCase):
    def test_empty_previous_output_is_reused_without_force_or_data_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "scripts" / SCRIPT.name
            script.parent.mkdir()
            shutil.copyfile(SCRIPT, script)
            bin_dir = root / ".venv-okal-voice" / "bin"
            bin_dir.mkdir(parents=True)
            python = bin_dir / "python"
            python.write_text('#!/bin/sh\necho \'{"feature_size": 128}\'\n', encoding="utf-8")
            converter = bin_dir / "ct2-transformers-converter"
            converter.write_text(
                "#!/bin/sh\n"
                "[ \"$HF_HUB_DISABLE_XET\" = 1 ] || exit 20\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = --output_dir ]; then output=$2; shift; fi\n"
                "  shift\n"
                "done\n"
                "[ ! -e \"$output\" ] || exit 19\n"
                "mkdir -p \"$output\"\n"
                "printf model > \"$output/model.bin\"\n"
                "printf tokenizer > \"$output/tokenizer.json\"\n",
                encoding="utf-8",
            )
            python.chmod(0o755)
            converter.chmod(0o755)
            output = root / "models" / "ct2"
            output.mkdir(parents=True)
            command = ["bash", str(script), "local-model", str(output)]

            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual((output / "preprocessor_config.json").read_text().strip(), '{"feature_size": 128}')

            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("already exists", second.stdout)

            (output / "preprocessor_config.json").unlink()
            third = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(third.returncode, 1)
            self.assertIn("Incomplete conversion directory", third.stderr)
            self.assertTrue((output / "model.bin").exists())


if __name__ == "__main__":
    unittest.main()
