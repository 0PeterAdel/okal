import importlib.util
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location("pilot", Path(__file__).with_name("freelance-mostaql.py"))
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class FreelancerPilotTests(unittest.TestCase):
    def test_only_project_urls_on_mostaql(self):
        self.assertEqual(pilot.project_id("https://mostaql.com/projects/12345/a-job?ref=x"), "12345")
        for url in ("http://mostaql.com/projects/123", "https://mostaql.com.evil.org/projects/123",
                    "https://mostaql.com/login", "https://mostaql.com/projects/../../login",
                    "https://mostaql.com/projects/123/.."):
            with self.assertRaises(ValueError):
                pilot.project_url(url)

    def test_private_profile_and_candidate_filter(self):
        profile = {"services": ["بايثون"], "proof": ["https://example.com/my-work"],
                   "style_examples": ["مرحبًا"], "min_price_usd": 40, "delivery_days": 5,
                   "exclude_terms": ["مراهنات"]}
        pilot.profile_check(profile)
        self.assertTrue(pilot.match_project(profile, "مشروع بايثون", "تطبيق"))
        self.assertFalse(pilot.match_project(profile, "مشروع بايثون", "مراهنات"))
        profile["proof"] = ["TODO: portfolio"]
        with self.assertRaises(ValueError):
            pilot.profile_check(profile)

    def test_saved_private_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data" / "draft.json"
            pilot.save(path, {"proposal": "نص خاص"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(pilot.load(path)["proposal"], "نص خاص")


if __name__ == "__main__":
    unittest.main()
