"""Offline checks for response identity, fail-closed form and pending receipt."""

import importlib.util
from io import BytesIO
import json
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
    def test_missing_reply_settings_use_review_defaults(self):
        with tempfile.TemporaryDirectory() as td, patch.object(reply, "SETTINGS", Path(td) / "missing.json"), \
             patch.object(reply.scout, "settings", return_value={}):
            cfg = reply.instructions(dry_run=True)
            self.assertEqual(cfg["authorization"], "review")
            self.assertFalse(cfg["enabled"])
            self.assertEqual(cfg["portfolio_url"], "")

    def test_preview_needs_no_service_proof_link_or_form_selectors(self):
        with tempfile.TemporaryDirectory() as td:
            settings = Path(td) / "reply.json"
            reply.scout.save(settings, {"authorization": "review"})
            with patch.object(reply, "SETTINGS", settings), patch.object(reply.scout, "settings", return_value={}):
                self.assertEqual(reply.instructions(dry_run=True)["portfolio_url"], "")
                with self.assertRaisesRegex(ValueError, "reply_selector"):
                    reply.instructions(reviewed=True)

    def test_only_verified_sourced_owner_facts_are_used(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "owner.json"
            reply.scout.save(path, {"facts": [
                {"text": "بنيت أداة أتمتة Python", "verified": True, "source": "CV"},
                {"text": "أدير حملات تسويق عالمية", "verified": False, "source": "note"},
                {"text": "خبرة غير موثقة", "verified": True, "source": ""},
            ]})
            with patch.object(reply, "OWNER_PROFILE", path):
                self.assertEqual(reply.profile_facts(), ["بنيت أداة أتمتة Python"])

    def test_reply_without_portfolio_is_valid_but_unapproved_link_fails(self):
        text = "أقدر أساعدك في تصميم أداة Python للأتمتة، ونبدأ بتحديد المدخلات والمخرجات المطلوبة قبل التنفيذ."
        reply.valid_reply(text, {"portfolio_url": ""})
        with self.assertRaisesRegex(ValueError, "رابطًا غير"):
            reply.valid_reply(text + " https://example.com/unapproved", {"portfolio_url": ""})

    def test_prompt_uses_verified_profile_without_static_service_or_link(self):
        response = "أقدر أساعدك في أتمتة الخطوات باستخدام Python. نبدأ بتحديد المدخلات والمخرجات المطلوبة ونختبر أول مسار قبل التوسع."
        captured = []
        def fake_urlopen(request, timeout):
            captured.append(json.loads(request.data))
            return BytesIO(json.dumps({"response": response}).encode())
        with patch.object(reply, "profile_facts", return_value=["بنيت أداة أتمتة Python"]), \
             patch.object(reply, "urlopen", side_effect=fake_urlopen):
            self.assertEqual(reply.compose(ITEM, {"portfolio_url": "", "service": "غير موثق",
                                                   "proof": "غير موثق"}), response)
        self.assertIn("بنيت أداة أتمتة Python", captured[0]["prompt"])
        self.assertNotIn("غير موثق", captured[0]["prompt"])
        self.assertIs(captured[0]["think"], False)
        self.assertGreaterEqual(captured[0]["options"]["num_predict"], 700)

    def test_thinking_only_response_has_specific_error(self):
        with patch.object(reply, "profile_facts", return_value=["Python project"]), \
             patch.object(reply, "urlopen", return_value=BytesIO(json.dumps({
                 "response": "", "thinking": "internal reasoning", "done_reason": "length"
             }).encode())):
            with self.assertRaisesRegex(ValueError, "استهلك الرد في التفكير"):
                reply.generate(ITEM, {"portfolio_url": ""})

    def test_auto_generation_still_rejects_invalid_reply(self):
        with patch.object(reply, "generate", return_value="رد قصير"):
            with self.assertRaisesRegex(ValueError, "طول الرد"):
                reply.compose(ITEM, {"portfolio_url": ""})

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
            with self.assertRaisesRegex(ValueError, "طول الرد"):
                reply.submit_one(page, ITEM, CFG, {"requests": {}}, "2026-10-16",
                                 dry_run=False, reply_override="ok")
            save.assert_not_called()
            page.locator.return_value.click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
