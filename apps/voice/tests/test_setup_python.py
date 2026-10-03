import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/setup-local-voice-stack.sh"


class PythonSelectionTests(unittest.TestCase):
    def test_unconfigured_mise_shim_uses_isolated_python(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            binaries.mkdir()

            def executable(name: str, body: str) -> Path:
                path = binaries / name
                path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
                path.chmod(0o755)
                return path

            for name in ("python3.13", "python3.12", "python3"):
                executable(name, "exit 1\n")
            selected = executable(
                "selected-python",
                """if [[ "$1" == "-c" ]]; then
  printf '3.13\\n'
elif [[ "$1" == "-m" && "$2" == "venv" ]]; then
  mkdir -p .venv-okal-voice/bin
  printf '#!/usr/bin/env bash\\nexit 0\\n' > .venv-okal-voice/bin/python
  chmod +x .venv-okal-voice/bin/python
fi
""",
            )
            executable(
                "mise",
                """printf '%s\\n' "$*" >> "$MISE_LOG"
if [[ "$1" == "exec" ]]; then
  printf '%s\\n' "$MOCK_SELECTED_PYTHON"
fi
""",
            )
            log = root / "mise.log"
            env = dict(os.environ, PATH=f"{binaries}:{os.environ['PATH']}")
            env.pop("OKAL_VOICE_PYTHON", None)
            env.update(MISE_LOG=str(log), MOCK_SELECTED_PYTHON=str(selected), XDG_DATA_HOME=str(root / "data"))
            result = subprocess.run(
                ["bash", str(SCRIPT), "--stt-only"],
                cwd=root, env=env, text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Using Python:", result.stdout)
            self.assertEqual(log.read_text(encoding="utf-8").splitlines(), [
                "install python@3.13",
                "exec python@3.13 -- python -c import sys; print(sys.executable)",
            ])


if __name__ == "__main__":
    unittest.main()
