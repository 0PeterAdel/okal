import importlib.util
import fcntl
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


spec = importlib.util.spec_from_file_location("pilot", Path(__file__).with_name("freelance-mostaql.py"))
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class FreelancerPilotTests(unittest.TestCase):
    def test_only_project_urls_on_mostaql(self):
        self.assertEqual(pilot.project_id("https://mostaql.com/project/12345-a-job?ref=x"), "12345")
        for url in ("http://mostaql.com/project/123", "https://mostaql.com.evil.org/project/123",
                    "https://mostaql.com/login", "https://mostaql.com/projects/123",
                    "https://mostaql.com/project/../../login", "https://mostaql.com/project/123/.."):
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

    def test_browser_profile_rejects_concurrent_process(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / ".browser.lock"
            with lock_path.open("w") as locked:
                fcntl.flock(locked, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(RuntimeError, "already open"):
                    pilot.browser_context(Path(directory))

    def test_browser_uses_real_resizable_window(self):
        with patch.dict(pilot.os.environ, {"OKAL_FREELANCE_CHROMIUM": "/usr/bin/chromium"}):
            options = pilot.browser_window_options(Path("/tmp/okal-test"))
        self.assertTrue(options["no_viewport"])
        self.assertIn("--start-maximized", options["args"])
        self.assertEqual(options["executable_path"], "/usr/bin/chromium")

    def test_accounts_opens_only_requested_site(self):
        page = MagicMock()
        page.url = "https://khamsat.com"
        context = MagicMock()
        context.pages = [page]
        playwright = MagicMock()
        lock = MagicMock()
        with patch.object(pilot, "browser_context", return_value=(playwright, context, lock)), \
             patch("builtins.input", return_value=""):
            pilot.cmd_accounts(SimpleNamespace(site="khamsat"), Path("/tmp/okal-test"))
        page.goto.assert_called_once_with("https://khamsat.com", wait_until="domcontentloaded", timeout=30000)
        context.new_page.assert_not_called()
        context.close.assert_called_once()

    def test_form_field_waits_for_dynamic_visibility(self):
        field = MagicMock()
        field.count.return_value = 1
        self.assertIs(pilot.one(field, "proposal"), field)
        field.first.wait_for.assert_called_once_with(state="visible", timeout=10000)
        field.count.return_value = 2
        with self.assertRaisesRegex(RuntimeError, "unique proposal"):
            pilot.one(field, "proposal")


if __name__ == "__main__":
    unittest.main()
