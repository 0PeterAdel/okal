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


def form_page():
    page, field, form, button, checkbox = (MagicMock() for _ in range(5))
    page.url = URL
    missing = MagicMock()
    missing.count.return_value = 0
    missing.all.return_value = []
    for element in (field, form, button, checkbox):
        element.count.return_value = 1
        element.is_visible.return_value = True
        element.is_enabled.return_value = True
    field.all.return_value = [field]
    page.locator.side_effect = lambda selector: (field if selector == CFG["reply_selector"] else
                                                 page.locator_body if selector == "body" else missing)
    page.locator_body.inner_text.return_value = ITEM["title"]
    field.locator.return_value = form
    form.locator.side_effect = lambda selector: (button if selector == CFG["submit_selector"] else checkbox)
    page.get_by_text.return_value.count.return_value = 1
    checkbox.is_checked.return_value = True
    field.input_value.return_value = VALID
    return page, field, form, button, checkbox


class ReplyTests(unittest.TestCase):
    def test_missing_reply_settings_use_review_defaults(self):
        with tempfile.TemporaryDirectory() as td, patch.object(reply, "SETTINGS", Path(td) / "missing.json"), \
             patch.object(reply.scout, "settings", return_value={}):
            cfg = reply.instructions(dry_run=True)
            self.assertEqual(cfg["authorization"], "review")
            self.assertFalse(cfg["enabled"])
            self.assertEqual(cfg["portfolio_url"], "")

    def test_old_auto_settings_cannot_send_without_review(self):
        with tempfile.TemporaryDirectory() as td:
            settings = Path(td) / "reply.json"
            reply.scout.save(settings, {"authorization": "auto", "enabled": True})
            with patch.object(reply, "SETTINGS", settings), patch.object(reply.scout, "settings", return_value={}):
                cfg = reply.instructions(dry_run=True)
                self.assertEqual(cfg["authorization"], "review")
                self.assertFalse(cfg["enabled"])
                with self.assertRaisesRegex(ValueError, "Autonomous submission is disabled"):
                    reply.instructions()

    def test_preview_needs_no_service_proof_link_or_form_selectors(self):
        with tempfile.TemporaryDirectory() as td:
            settings = Path(td) / "reply.json"
            reply.scout.save(settings, {"authorization": "review"})
            with patch.object(reply, "SETTINGS", settings), patch.object(reply.scout, "settings", return_value={}):
                self.assertEqual(reply.instructions(dry_run=True)["portfolio_url"], "")
                cfg = reply.instructions(reviewed=True)
                self.assertEqual(cfg["reply_selector"], "textarea[name='content'].c-form__control")
                self.assertEqual(cfg["submit_selector"], "button#commentable_submit[type='submit']")

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

    def test_reply_length_matches_live_khamsat_textarea(self):
        for length in (2, 1291, 2000):
            reply.valid_reply("ا" * length, {"portfolio_url": ""})
        with self.assertRaisesRegex(ValueError, "الحد الأقصى.*2000"):
            reply.valid_reply("ا" * 2001, {"portfolio_url": ""})
        with self.assertRaisesRegex(ValueError, "الرد فارغ"):
            reply.valid_reply("  ", {"portfolio_url": ""})

    def test_prompt_uses_verified_profile_without_static_service_or_link(self):
        response = "أقدر أساعدك في أتمتة الخطوات باستخدام Python. نبدأ بتحديد المدخلات والمخرجات المطلوبة ونختبر أول مسار قبل التوسع."
        captured = []
        def fake_urlopen(request, timeout):
            captured.append(json.loads(request.data))
            return BytesIO(json.dumps({"response": response}).encode())
        with patch.object(reply, "profile_facts", return_value=["بنيت أداة أتمتة Python"]), \
             patch.object(reply, "style_examples", return_value=[{
                 "request_id": "99", "before": "مسودة قديمة", "after": "صياغة ودودة مختصرة"}]), \
             patch.object(reply, "urlopen", side_effect=fake_urlopen):
            self.assertEqual(reply.compose(ITEM | {
                "description": "أحتاج أتمتة عمليات البيانات", "comments": [{"text": "نقدر نبدأ بخطة عامة"}]},
                {"portfolio_url": "", "service": "غير موثق", "proof": "غير موثق",
                 "proposal_instructions": "اكتب من غير مبالغة وبشكل مباشر"}), response)
        self.assertIn("بنيت أداة أتمتة Python", captured[0]["prompt"])
        self.assertNotIn("غير موثق", captured[0]["prompt"])
        self.assertIn("صياغة ودودة مختصرة", captured[0]["prompt"])
        self.assertIn("الأسلوب والبناء فقط", captured[0]["system"])
        self.assertIn("اكتب من غير مبالغة", captured[0]["system"])
        self.assertIn("أحتاج أتمتة عمليات البيانات", captured[0]["prompt"])
        self.assertIn("نقدر نبدأ بخطة عامة", captured[0]["prompt"])
        self.assertNotIn("نقدر نبدأ بخطة عامة", captured[0]["system"])
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
        with patch.object(reply, "generate", return_value="ا" * 2001):
            with self.assertRaisesRegex(ValueError, "الحد الأقصى"):
                reply.compose(ITEM, {"portfolio_url": ""})

    def test_learning_keeps_last_five_private_edits_and_skips_identical_text(self):
        with tempfile.TemporaryDirectory() as td, patch.object(reply, "STYLE_MEMORY", Path(td) / "style.json"):
            self.assertFalse(reply.remember_edit("1", "same", "same"))
            self.assertFalse(reply.STYLE_MEMORY.exists())
            for rid in range(1, 7):
                self.assertTrue(reply.remember_edit(str(rid), "قبل", f"بعد {rid}"))
            self.assertEqual([row["request_id"] for row in reply.style_examples()],
                             ["2", "3", "4", "5", "6"])
            self.assertEqual(reply.STYLE_MEMORY.stat().st_mode & 0o777, 0o600)

    def test_duplicate_request_cannot_be_sent(self):
        with self.assertRaisesRegex(ValueError, "already been attempted"):
            reply.submit_one(MagicMock(), ITEM, CFG, {"requests": {"123456": {"status": "pending"}}},
                             "2026-10-16", dry_run=False)

    def test_missing_visible_unique_form_does_not_create_receipt(self):
        page, field, _, _, _ = form_page()
        field.count.return_value = 0
        receipts = {"requests": {}}
        with patch.object(reply, "visit"), patch.object(reply, "compose", return_value=VALID), \
             patch.object(reply.scout, "save") as save:
            with self.assertRaisesRegex(RuntimeError, "تعذر تحديد نموذج تعليق خمسات"):
                reply.submit_one(page, ITEM, CFG, receipts, "2026-10-16", dry_run=False)
            save.assert_not_called()

    def test_name_fallback_when_saved_selector_is_stale(self):
        page, field, _, button, _ = form_page()
        default = page.locator.side_effect
        stale = MagicMock()
        stale.count.return_value = 0
        stale.all.return_value = []
        fallback = MagicMock()
        fallback.count.return_value = 1
        fallback.all.return_value = [field]
        page.locator.side_effect = lambda selector: (
            stale if selector == CFG["reply_selector"] else
            fallback if selector == "textarea[name='content']" else default(selector))
        with patch.object(reply, "visit"), patch.object(reply, "compose", return_value=VALID), \
             patch.object(reply, "visible_site_errors", return_value=""), \
             patch.object(reply.scout, "save"):
            reply.submit_one(page, ITEM, CFG, {"requests": {}}, "2026-10-16", dry_run=False)
        button.click.assert_called_once()
        page.locator("form textarea:visible").first.wait_for.assert_called_once_with(
            state="visible", timeout=12000)

    def test_waits_for_delayed_comment_field(self):
        page, field, _, button, _ = form_page()
        field.count.return_value = 0
        page.locator("form textarea:visible").first.wait_for.side_effect = lambda **kw: (
            field.count.configure_mock(return_value=1))
        with patch.object(reply, "visit"), patch.object(reply, "compose", return_value=VALID), \
             patch.object(reply, "visible_site_errors", return_value=""), \
             patch.object(reply.scout, "save"):
            reply.submit_one(page, ITEM, CFG, {"requests": {}}, "2026-10-16", dry_run=False)
        button.click.assert_called_once()

    def test_inspected_xpath_fallback_requires_same_form_controls(self):
        page, field, _, button, _ = form_page()
        default = page.locator.side_effect
        missing = MagicMock()
        missing.count.return_value = 0
        missing.all.return_value = []
        xpath = ("xpath=/html/body/div[3]/div/div[3]/div/div[2]/div[2]/div[4]/"
                 "div[2]/form/div[1]/textarea")
        page.locator.side_effect = lambda selector: (
            missing if selector == CFG["reply_selector"] else
            field if selector == xpath else default(selector))
        with patch.object(reply, "visit"), patch.object(reply, "compose", return_value=VALID), \
             patch.object(reply, "visible_site_errors", return_value=""), \
             patch.object(reply.scout, "save"):
            reply.submit_one(page, ITEM, CFG, {"requests": {}}, "2026-10-16", dry_run=False)
        button.click.assert_called_once()

    def test_ambiguous_comment_forms_never_click(self):
        page, field, _, button, _ = form_page()
        other = MagicMock()
        other.is_visible.return_value = True
        other.is_enabled.return_value = True
        other.locator.return_value = field.locator.return_value
        field.count.return_value = 2
        field.all.return_value = [field, other]
        with patch.object(reply, "visit"), patch.object(reply, "compose", return_value=VALID), \
             patch.object(reply.scout, "save") as save:
            with self.assertRaisesRegex(RuntimeError, "أكثر من نموذج"):
                reply.submit_one(page, ITEM, CFG, {"requests": {}}, "2026-10-16", dry_run=False)
        button.click.assert_not_called()
        save.assert_not_called()

    def test_redirect_during_form_wait_does_not_record_or_click(self):
        page, _, _, button, _ = form_page()
        page.locator("form textarea:visible").first.wait_for.side_effect = lambda **kw: setattr(
            page, "url", "https://khamsat.com/login")
        with patch.object(reply, "visit"), patch.object(reply, "compose", return_value=VALID), \
             patch.object(reply.scout, "save") as save:
            with self.assertRaisesRegex(RuntimeError, "الصفحة انتقلت"):
                reply.submit_one(page, ITEM, CFG, {"requests": {}}, "2026-10-16", dry_run=False)
        button.click.assert_not_called()
        save.assert_not_called()

    def test_diagnostics_redact_query_and_never_submit(self):
        page, field, _, button, checkbox = form_page()
        page.url = URL + "?private_token=should-not-print"
        page.locator.side_effect = lambda selector: field if selector in (
            "form", "textarea", "textarea:visible", "textarea[name='content']",
            "input#confirm", "#commentable_submit") else MagicMock()
        page.locator.return_value.all.return_value = []
        result = reply.page_diagnostics(page, URL)
        self.assertEqual(result["page"], URL)
        self.assertNotIn("private_token", str(result))
        self.assertTrue(result["same_request"])
        button.click.assert_not_called()
        checkbox.check.assert_not_called()

    def test_diagnose_opens_saved_profile_without_posting(self):
        page, _, _, button, _ = form_page()
        context, play = MagicMock(), MagicMock()
        context.pages = [page]
        with tempfile.TemporaryDirectory() as td, patch.object(reply.scout, "PROFILE", Path(td)), \
             patch.object(reply, "browser_lock"), \
             patch.object(reply, "open_browser", return_value=(play, context)) as browser, \
             patch.object(reply, "page_diagnostics", return_value={"content_textareas": 0}), \
             patch.object(reply.sys, "stdin") as stdin, patch("builtins.print"):
            stdin.isatty.return_value = False
            reply.diagnose(URL)
        browser.assert_called_once_with(Path(td))
        page.goto.assert_called_once_with(URL, wait_until="domcontentloaded", timeout=30000)
        button.click.assert_not_called()
        context.close.assert_called_once()
        play.stop.assert_called_once()

    def test_receipt_is_pending_before_click_and_sent_after_verified_reload(self):
        page, field, _, button, checkbox = form_page()
        page.locator_body.inner_text.return_value = "عنوان مختلف في الصفحة"
        state = {"requests": {}}
        events = []
        with patch.object(reply, "visit"), patch.object(reply, "compose", return_value=VALID), \
             patch.object(reply, "visible_site_errors", return_value=""), \
             patch.object(reply.scout, "save", side_effect=lambda path, value: events.append(value["requests"]["123456"]["status"])):
            reply.submit_one(page, ITEM, CFG, state, "2026-10-16", dry_run=False)
        self.assertEqual(events, ["pending", "submitted"])
        field.fill.assert_called_once_with(VALID)
        field.dispatch_event.assert_called_once_with("change")
        checkbox.check.assert_called_once()
        page.wait_for_timeout.assert_called_once_with(500)
        button.click.assert_called_once()

    def test_incomplete_form_state_never_clicks_or_records_attempt(self):
        page, field, _, button, _ = form_page()
        field.input_value.return_value = "different text"
        with patch.object(reply, "visit"), patch.object(reply, "compose", return_value=VALID), \
             patch.object(reply.scout, "save") as save:
            with self.assertRaisesRegex(RuntimeError, "غير جاهز"):
                reply.submit_one(page, ITEM, CFG, {"requests": {}}, "2026-10-16", dry_run=False)
        button.click.assert_not_called()
        save.assert_not_called()

    def test_visit_rejects_different_request_id_but_allows_changed_slug(self):
        page = MagicMock()
        page.locator.return_value.count.return_value = 0
        page.url = "https://khamsat.com/community/requests/123456-updated-title"
        reply.visit(page, URL)
        page.url = "https://khamsat.com/community/requests/654321-other-title"
        with self.assertRaisesRegex(RuntimeError, "redirected"):
            reply.visit(page, URL)

    def test_terms_checkbox_required_before_receipt_or_click(self):
        page, _, _, button, checkbox = form_page()
        checkbox.count.return_value = 0
        with patch.object(reply, "visit"), patch.object(reply, "compose", return_value=VALID), \
             patch.object(reply.scout, "save") as save:
            with self.assertRaisesRegex(RuntimeError, "خانة الشروط=0"):
                reply.submit_one(page, ITEM, CFG, {"requests": {}}, "2026-10-16", dry_run=False)
        save.assert_not_called()
        button.click.assert_not_called()

    def test_visible_site_error_is_reported_and_receipt_stays_pending(self):
        page, _, _, button, checkbox = form_page()
        events = []
        state = {"requests": {}}
        with patch.object(reply, "visit"), patch.object(reply, "compose", return_value=VALID), \
             patch.object(reply, "visible_site_errors", return_value="نص التعليق مطلوب"), \
             patch.object(reply.scout, "save", side_effect=lambda path, value: events.append(value["requests"]["123456"]["status"])):
            with self.assertRaisesRegex(RuntimeError, "خمسات رفض الرد: نص التعليق مطلوب"):
                reply.submit_one(page, ITEM, CFG, state, "2026-10-16", dry_run=False)
        checkbox.check.assert_called_once()
        button.click.assert_called_once()
        self.assertEqual(events, ["pending"])
        page.reload.assert_not_called()

    def test_visible_site_errors_ignores_hidden_messages(self):
        page = MagicMock()
        shown, hidden = MagicMock(), MagicMock()
        shown.is_visible.return_value = True
        shown.inner_text.return_value = "لا يمكن إرسال التعليق الآن"
        hidden.is_visible.return_value = False
        hidden.inner_text.return_value = "رسالة قديمة"
        page.locator.return_value.all.return_value = [shown, hidden]
        self.assertEqual(reply.visible_site_errors(page), "لا يمكن إرسال التعليق الآن")
        hidden.inner_text.assert_not_called()

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
            with self.assertRaisesRegex(ValueError, "الرد فارغ"):
                reply.submit_one(page, ITEM, CFG, {"requests": {}}, "2026-10-16",
                                 dry_run=False, reply_override="  ")
            save.assert_not_called()
            page.locator.return_value.click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
