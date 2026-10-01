import contextlib
import io
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from okal_voice import voice_lab
from okal_voice.providers import ProviderError


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

    def test_holdout_prompts_are_distinct_and_report_is_labeled(self):
        self.assertEqual(len(voice_lab.HOLDOUT_CASES), 12)
        self.assertFalse({phrase for _, phrase in voice_lab.CASES} &
                         {phrase for _, phrase in voice_lab.HOLDOUT_CASES})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "holdout.json"
            with patch("sys.argv", ["okal-voice-lab", str(root), "--suite", "holdout",
                                    "--output", str(report)]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(voice_lab.main(), 2)
            summary = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(summary["suite"], "holdout")
            self.assertEqual(summary["cases"][0]["reference"], voice_lab.HOLDOUT_CASES[0][1])

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

    def test_probes_compare_both_candidates_without_using_case_label(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "en_02.wav").touch()
            report = root / "probes.json"
            stt = Mock()
            stt.transcribe_with_metadata.side_effect = [
                ("automatic", "ar", {"language_probability": 0.6,
                                     "language_probabilities": {"ar": 0.6, "en": 0.4}, "mean_logprob": -0.5}),
                ("arabic", "ar", {"mean_logprob": -0.6}),
                ("english", "en", {"mean_logprob": -0.3}),
            ]
            with patch("okal_voice.voice_lab.build_stt", return_value=stt), patch(
                "okal_voice.voice_lab._wer", return_value=0.25
            ), patch("sys.argv", ["okal-voice-lab", str(root), "--language-probes", "--output", str(report)]), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(voice_lab.main(), 2)  # Eleven cases have no WAV.

            self.assertEqual([call.kwargs for call in stt.transcribe_with_metadata.call_args_list], [
                {}, {"language_hint": "ar"}, {"language_hint": "en"},
            ])
            row = next(case for case in json.loads(report.read_text(encoding="utf-8"))["cases"]
                       if case["id"] == "en_02")
            self.assertEqual(row["transcript"], "automatic")
            self.assertEqual(row["auto_metadata"]["language_probabilities"], {"ar": 0.6, "en": 0.4})
            self.assertEqual(row["probes"]["ar"]["transcript"], "arabic")
            self.assertEqual(row["probes"]["en"]["mean_logprob"], -0.3)
            self.assertEqual(stat.S_IMODE(report.stat().st_mode), 0o600)

    def test_model_load_failure_is_attempted_once_for_the_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for case_id, _ in voice_lab.CASES:
                (root / f"{case_id}.wav").touch()
            report = root / "failed.json"
            stt = Mock()
            stt.prepare.side_effect = ProviderError("model download timed out")
            with patch("okal_voice.voice_lab.build_stt", return_value=stt), patch(
                "sys.argv", ["okal-voice-lab", str(root), "--output", str(report)]
            ), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(voice_lab.main(), 2)

            stt.prepare.assert_called_once_with()
            stt.transcribe.assert_not_called()
            summary = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual({case["error"] for case in summary["cases"]}, {"model download timed out"})
            self.assertIn("failed (12 cases): model download timed out", output.getvalue())


if __name__ == "__main__":
    unittest.main()
