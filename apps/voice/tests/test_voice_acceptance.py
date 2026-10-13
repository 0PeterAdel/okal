import json
import tempfile
import unittest
from pathlib import Path

from okal_voice.acceptance_cases import CASES, PROMPTS
from okal_voice.voice_lab import CASES as BASELINE, HOLDOUT_CASES, SUITES, VOCABULARY_CASES

ROOT = Path(__file__).resolve().parents[3]


class AcceptanceTests(unittest.TestCase):
    def test_new_suite_has_forty_unique_phrases_and_expected_groups(self):
        self.assertEqual(SUITES["acceptance"], PROMPTS)
        self.assertEqual([sum(case_id.startswith(prefix + "_") for case_id, *_ in CASES)
                          for prefix in ("ar", "en", "mix")], [15, 10, 15])
        phrases = [phrase for _, phrase, *_ in CASES]
        self.assertEqual(len(phrases), len(set(phrases)))
        previous = {phrase for _, phrase in BASELINE + HOLDOUT_CASES + VOCABULARY_CASES}
        self.assertFalse(set(phrases) & previous)

    def test_scoring_requires_every_semantic_field_and_each_group_threshold(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("acceptance_review", ROOT / "scripts/review-voice-acceptance.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            report = folder / "lab.json"
            report.write_text(json.dumps({
                "suite": "acceptance", "model": "cached", "backend": "audiocpp",
                "cases": [{"id": case_id, "reference": phrase, "ok": True, "transcript": phrase}
                          for case_id, phrase, *_ in CASES],
            }, ensure_ascii=False), encoding="utf-8")
            review = folder / "review.json"
            module.prepare(report, review)
            self.assertEqual(review.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(FileExistsError, "overwrite"):
                module.prepare(report, review)
            with self.assertRaisesRegex(ValueError, "incomplete"):
                module.score(review)
            data = json.loads(review.read_text(encoding="utf-8"))
            for row in data["cases"]:
                row.update(intent_ok=True, target_ok=True, details_ok=True, unsafe_action=False)
            # Intent failure in the mixed group is not concealed by perfect Arabic/English.
            for row in data["cases"]:
                if row["id"].startswith("mix_") and int(row["id"].split("_")[1]) <= 5:
                    row["intent_ok"] = False
            review.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            groups, accepted = module.score(review)
            self.assertFalse(accepted)
            self.assertEqual(groups["mix"]["passed"], 10)
            self.assertEqual(groups["mix"]["required"], 11)
            data["cases"][25]["intent_ok"] = True
            review.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self.assertTrue(module.score(review)[1])
            data["cases"][25]["recognition_ok"] = False
            review.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self.assertFalse(module.score(review)[1])
            data["cases"][25]["recognition_ok"] = True
            data["cases"][0]["unsafe_action"] = True
            review.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self.assertFalse(module.score(review)[1])


if __name__ == "__main__":
    unittest.main()
