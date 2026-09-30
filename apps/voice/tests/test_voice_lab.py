import contextlib
import io
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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

    def test_language_hints_only_apply_to_known_language_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "hints.json"
            for case_id in ("ar_01", "en_02", "mix_01"):
                (root / f"{case_id}.wav").touch()
            stt = Mock()
            stt.transcribe.return_value = ("words", "en")
            with patch("okal_voice.voice_lab.build_stt", return_value=stt), patch(
                "sys.argv", ["okal-voice-lab", str(root), "--language-hints", "--output", str(report)]
            ), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(voice_lab.main(), 2)  # Only three cases have recordings.

            self.assertEqual([call.kwargs for call in stt.transcribe.call_args_list], [
                {"language_hint": "ar"}, {"language_hint": "en"}, {},
            ])
            summary = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(summary["language_hints"])
            rows = {case["id"]: case for case in summary["cases"]}
            self.assertEqual(rows["ar_01"]["language_hint"], "ar")
            self.assertEqual(rows["en_02"]["language_hint"], "en")
            self.assertNotIn("language_hint", rows["mix_01"])


if __name__ == "__main__":
    unittest.main()
