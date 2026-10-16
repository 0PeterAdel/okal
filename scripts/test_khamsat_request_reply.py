"""Offline checks for response identity, fail-closed form and pending receipt."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch


spec = importlib.util.spec_from_file_location("khamsat_reply", Path(__file__).with_name("khamsat-request-reply.py"))
reply = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reply)


URL = "https://khamsat.com/community/requests/123456-python"
ITEM = {"url": URL, "title": "مطلوب Python", "visible_text": "مطلوب Python API"}
CFG = {"keywords": ["Python"], "exclude_terms": [], "reply_selector": "textarea[name=x]",
       "submit_selector": "button[name=y]", "portfolio_url": "https://example.com/portfolio"}
VALID = "يمكنني تطوير واجهة Python المطلوبة اعتمادًا على مشروعي السابق. تفاصيل عملي: https://example.com/portfolio"


class ReplyTests(unittest.TestCase):
    def test_missing_private_reply_settings_explains_control_page(self):
        with tempfile.TemporaryDirectory() as td, patch.object(reply, "SETTINGS", Path(td) / "missing.json"), \
             patch.object(reply.scout, "settings", return_value={}):
            with self.assertRaisesRegex(ValueError, "احفظ إعدادات الرد من صفحة التحكم"):
                reply.instructions(dry_run=True)

    def test_preview_needs_proof_but_not_form_selectors(self):
        with tempfile.TemporaryDirectory() as td:
            settings = Path(td) / "reply.json"
            reply.scout.save(settings, {"service": "Python", "proof": "مشروع موثق",
                                        "portfolio_url": "https://example.com/work"})
            with patch.object(reply, "SETTINGS", settings), patch.object(reply.scout, "settings", return_value={}):
                self.assertEqual(reply.instructions(dry_run=True)["service"], "Python")
                with self.assertRaisesRegex(ValueError, "reply_selector"):
                    reply.instructions(reviewed=True)

    def test_duplicate_request_cannot_be_sent(self):
        with self.assertRaisesRegex(ValueError, "already been attempted"):
            reply.submit_one(MagicMock(), ITEM, CFG, {"requests": {"123456": {"status": "pending"}}},
                             "2026-10-16", dry_run=False)

    def test_missing_visible_unique_form_does_not_create_receipt(self):
        page = MagicMock()
        page.locator.return_value.inner_text.return_value = ITEM["title"]
        page.locator.return_value.count.return_value = 0
        receipts = {"requests": {}}
        with patch.object(reply, "visit"), patch.object(reply, "compose", return_value=VALID), \
             patch.object(reply.scout, "save") as save:
            with self.assertRaisesRegex(RuntimeError, "not unambiguous"):
                reply.submit_one(page, ITEM, CFG, receipts, "2026-10-16", dry_run=False)
            save.assert_not_called()

    def test_receipt_is_pending_before_click_and_sent_after_verified_reload(self):
        page = MagicMock()
        page.locator.return_value.inner_text.return_value = ITEM["title"]
        page.locator.return_value.count.return_value = 1
        page.get_by_text.return_value.count.return_value = 1
        state = {"requests": {}}
        events = []
        with patch.object(reply, "visit"), patch.object(reply, "compose", return_value=VALID), \
             patch.object(reply.scout, "save", side_effect=lambda path, value: events.append(value["requests"]["123456"]["status"])):
            reply.submit_one(page, ITEM, CFG, state, "2026-10-16", dry_run=False)
        self.assertEqual(events, ["pending", "submitted"])
        page.locator.return_value.click.assert_called_once()

    def test_inspector_does_not_submit(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(reply.scout, "PROFILE", Path(td)), patch.object(reply, "browser_lock") as lock, \
                 patch.object(reply, "open_browser") as browser, patch.object(reply, "visit"), \
                 patch.object(reply, "controls", return_value=[{"tag": "textarea"}]):
                lock.return_value.__enter__.return_value = None
                browser.return_value = MagicMock(), MagicMock()
                self.assertEqual(reply.inspect(URL), [{"tag": "textarea"}])

    def test_invalid_manual_reply_cannot_click(self):
        page = MagicMock()
        page.locator.return_value.inner_text.return_value = ITEM["title"]
        with patch.object(reply, "visit"), patch.object(reply.scout, "save") as save:
            with self.assertRaisesRegex(ValueError, "failed validation"):
                reply.submit_one(page, ITEM, CFG, {"requests": {}}, "2026-10-16",
                                 dry_run=False, reply_override="ok")
            save.assert_not_called()
            page.locator.return_value.click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
