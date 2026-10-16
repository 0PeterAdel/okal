"""Checks for the offline boundary of the Khamsat scout."""

import importlib.util
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    "khamsat_scout", Path(__file__).with_name("khamsat-request-scout.py")
)
scout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scout)


class KhamsatScoutTests(unittest.TestCase):
    def test_only_khamsat_request_links(self):
        self.assertEqual(
            scout.request_url("https://www.khamsat.com/community/requests/123-طلب?ref=list"),
            "https://khamsat.com/community/requests/123-طلب",
        )
        for url in ("http://khamsat.com/community/requests/123",
                    "https://khamsat.com.evil.test/community/requests/123",
                    "https://khamsat.com/community/requests",
                    "https://khamsat.com/community/general/123",
                    "https://u:p@khamsat.com/community/requests/123",
                    "https://khamsat.com/community/requests/123#fragment"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                scout.request_url(url)

    def test_private_settings_and_relevance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            scout.save(path, scout.DEFAULT_CONFIG)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            data = scout.settings(path)
            self.assertTrue(scout.matches("تحليل بيانات ببايثون", data))
            self.assertFalse(scout.matches("مطلوب سبام ببايثون", data))
            self.assertFalse(scout.matches("تصميم شعار", data))

    def test_keep_existing_candidates_and_dedupe(self):
        old = [{"id": "1", "title": "keep"}, {"id": "2", "title": "old"}]
        new = [{"id": "2", "title": "updated"}, {"id": "3", "title": "new"}]
        self.assertEqual(scout.merge_queue(old, new), [old[0], new[0], new[1]])


if __name__ == "__main__":
    unittest.main()
