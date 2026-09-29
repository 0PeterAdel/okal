import contextlib
import io
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from okal_voice import voice_lab


class VoiceLabTests(unittest.TestCase):
    def test_incomplete_run_fails_and_keeps_private_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "results.json"
            with patch("sys.argv", ["okal-voice-lab", str(root), "--output", str(report)]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    status = voice_lab.main()

            self.assertEqual(status, 2)
            self.assertEqual(stat.S_IMODE(report.stat().st_mode), 0o600)
            summary = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(len(summary["cases"]), 12)
            self.assertEqual(summary["groups"]["mix"]["completed"], 0)
            self.assertEqual(summary["groups"]["mix"]["total"], 4)
            self.assertIn("failed (12 cases): missing recording", output.getvalue())

    def test_recorder_prompts_come_from_benchmark_cases(self):
        with patch("sys.argv", ["okal-voice-lab", "--list-cases"]):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(voice_lab.main(), 0)
        self.assertEqual(output.getvalue().splitlines(), [
            f"{case_id}\t{phrase}" for case_id, phrase in voice_lab.CASES
        ])


if __name__ == "__main__":
    unittest.main()
