"""Checks for the offline boundary of the Khamsat scout."""

import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch


spec = importlib.util.spec_from_file_location(
    "khamsat_scout", Path(__file__).with_name("khamsat-request-scout.py")
)
scout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scout)


class KhamsatScoutTests(unittest.TestCase):
    def test_load_more_twice_before_extraction(self):
        page, button, rows = MagicMock(), MagicMock(), MagicMock()
        button.count.return_value = 1
        button.is_visible.return_value = True
        button.is_enabled.return_value = True
        rows.count.side_effect = [12, 24]
        page.locator.side_effect = lambda selector: button if selector == "#community_loadmore_btn" else rows
        scout.load_listing(page, 2)
        self.assertEqual(button.click.call_count, 2)
        self.assertEqual(page.wait_for_function.call_count, 2)
        page.wait_for_timeout.assert_called_once_with(1000)

    def test_listing_rows_extracts_only_real_requests(self):
        page = MagicMock()
        page.locator.return_value.evaluate_all.return_value = [
            {"url": "https://khamsat.com/community/requests/12-python", "title": "Python automation",
             "publisher": "اسم ناشر", "time": "منذ ساعة"},
            {"url": "https://external.example/requests/13", "title": "غير موثوق"},
        ]
        rows = scout.listing_rows(page)
        self.assertEqual(rows[0]["id"], "12")
        self.assertEqual(rows[0]["publisher"], "اسم ناشر")
        self.assertEqual(len(rows), 1)
        self.assertIn("#forums_table tr.forum_post", page.locator.call_args.args[0])

    def test_model_shortlist_rejects_unlisted_ids_and_excluded_terms(self):
        rows = [{"id": "12", "title": "Python automation"},
                {"id": "13", "title": "casino Python"}]
        response = {"response": json.dumps({"matches": [
            {"id": "999", "reason": "مخترع"}, {"id": "13", "reason": "مستبعد"},
            {"id": "12", "reason": "خبرة Python موثقة"}]})}
        config = scout.DEFAULT_CONFIG | {"keywords": ["Python"], "exclude_terms": ["casino"]}
        with patch.object(scout, "urlopen", return_value=BytesIO(json.dumps(response).encode())):
            result = scout.model_shortlist(rows, config, ["Python automation project"], 10)
        self.assertEqual([x["id"] for x in result], ["12"])
        self.assertEqual(result[0]["selection_terms"], ["Python"])
        self.assertTrue(scout.eligible(result[0] | {"description": "Build an API"}, config))
        self.assertFalse(scout.eligible(result[0] | {"description": "casino integration"}, config))

    def test_request_details_comments_are_opt_in_and_bounded(self):
        item = {"id": "12", "url": "https://khamsat.com/community/requests/12-python", "title": "Python"}
        page = MagicMock()
        page.url = item["url"]
        container = page.locator.return_value
        container.count.return_value = 1
        container.evaluate.return_value = [{"author": "شخص", "text": "سأنفذ خطوة واحدة"}]
        config = scout.DEFAULT_CONFIG | {"read_comments": True, "comments_limit": 3}
        with patch.object(scout, "detail_text", side_effect=["عنوان الطلب", "وصف الطلب", "3 تعليقات"]):
            result = scout.request_details(page, item, config)
        self.assertEqual(result["description"], "وصف الطلب")
        self.assertEqual(result["comments"][0]["text"], "سأنفذ خطوة واحدة")
        self.assertEqual(container.evaluate.call_args.args[1], 3)
        with patch.object(scout, "detail_text", side_effect=["عنوان الطلب", "وصف الطلب", "3 تعليقات"]):
            result = scout.request_details(page, item, config | {"read_comments": False})
        self.assertEqual(result["comments"], [])
        self.assertEqual(container.evaluate.call_count, 1)

    def test_request_details_accepts_canonical_slug_but_stops_on_login(self):
        item = {"id": "12", "url": "https://khamsat.com/community/requests/12-old-title", "title": "Old"}
        page = MagicMock()
        page.url = "https://khamsat.com/community/requests/12-new-title"
        with patch.object(scout, "detail_text", side_effect=["عنوان", "وصف", "تعليق"]):
            self.assertEqual(scout.request_details(page, item, scout.DEFAULT_CONFIG)["description"], "وصف")
        page.url = "https://khamsat.com/login"
        with patch.object(scout, "detail_text") as details, \
             self.assertRaises(scout.ManualInspectionRequired):
            scout.request_details(page, item, scout.DEFAULT_CONFIG)
        details.assert_not_called()

    def test_visible_captcha_requires_manual_inspection(self):
        page = MagicMock()
        page.url = scout.LISTING
        page.locator.return_value.all.return_value = [MagicMock(is_visible=lambda: True)]
        with self.assertRaisesRegex(scout.ManualInspectionRequired, "CAPTCHA"):
            scout.require_access(page, scout.LISTING)

    def test_scan_expands_ranks_reads_details_then_rechecks_fit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            profile = root / "browser"
            profile.mkdir()
            item = {"id": "12", "url": "https://khamsat.com/community/requests/12-python", "title": "Python"}
            detail = item | {"description": "Python automation work", "visible_text": "Python automation work",
                             "found_at": "2026-10-17T00:00:00+00:00", "selection_terms": ["Python"]}
            page = MagicMock()
            page.url = scout.LISTING
            context = MagicMock()
            context.pages = [page]
            play = MagicMock()
            play.chromium.launch_persistent_context.return_value = context
            manager = MagicMock()
            manager.__enter__.return_value = play
            api = types.ModuleType("playwright.sync_api")
            api.Error = type("PlaywrightError", (Exception,), {})
            api.sync_playwright = lambda: manager
            config = scout.DEFAULT_CONFIG | {"keywords": ["Python"]}
            with patch.dict(sys.modules, {"playwright": types.ModuleType("playwright"),
                                          "playwright.sync_api": api}), \
                 patch.object(scout, "verified_work_facts", return_value=["Python work"]), \
                 patch.object(scout, "browser_executable", return_value="/mock/chromium"), \
                 patch.object(scout, "load_listing") as more, \
                 patch.object(scout, "listing_rows", return_value=[item]), \
                 patch.object(scout, "model_shortlist", side_effect=[[item], [detail]]) as model, \
                 patch.object(scout, "request_details", return_value=detail) as details:
                summary = scout.scan(root / "state", profile, config, 10)
            more.assert_called_once_with(page, 2)
            details.assert_called_once()
            self.assertEqual(model.call_count, 2)
            self.assertEqual(summary["qualified"], 1)
            saved = scout.load(root / "state" / "queue.json")
            self.assertEqual(saved["requests"][0]["description"], "Python automation work")
            self.assertEqual(saved["last_scan"]["listing_rows"], 1)

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

    def test_reuses_system_browser_when_playwright_revision_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "chromium"
            binary.write_text("browser")
            binary.chmod(0o755)
            with patch.dict(scout.os.environ, {"OKAL_FREELANCE_CHROMIUM": ""}), \
                 patch.object(scout.shutil, "which", side_effect=lambda name: str(binary) if name == "chromium" else None):
                self.assertEqual(scout.browser_executable(str(Path(tmp) / "missing")), str(binary))

    def test_missing_browser_reports_one_install_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(scout.os.environ, {"OKAL_FREELANCE_CHROMIUM": ""}), \
                 patch.object(scout.shutil, "which", return_value=None), \
                 patch.object(scout.Path, "home", return_value=Path(tmp)):
                with self.assertRaisesRegex(RuntimeError, "playwright install chromium"):
                    scout.browser_executable(str(Path(tmp) / "missing"))


if __name__ == "__main__":
    unittest.main()
