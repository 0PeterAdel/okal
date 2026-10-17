"""Authorization, refresh and duplicate gates for the local Khamsat page."""

import importlib.util
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode


spec = importlib.util.spec_from_file_location("khamsat_control", Path(__file__).with_name("khamsat-control.py"))
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.form = {
            "authorization": "review", "keywords": "Python\nتحليل بيانات",
            "exclude_terms": "casino", "scan_interval_minutes": "30", "max_per_day": "2",
            "proposal_instructions": "اكتب بلغة واضحة ومن عملي الحقيقي.",
            "service": "Python", "proof": "مشروع موثق", "portfolio_url": "https://example.com/work",
            "reply_selector": "textarea[name=reply]", "submit_selector": "button[name=submit]",
        }

    def test_review_is_only_mode_even_with_old_auto_confirmation(self):
        watch, config = control.validate_settings(self.form | {
            "load_more_clicks": "2", "candidate_limit": "10",
            "read_comments": "yes", "comments_limit": "3"})
        self.assertFalse(config["enabled"])
        self.assertEqual(config["authorization"], "review")
        self.assertEqual(watch["load_more_clicks"], 2)
        self.assertEqual(watch["candidate_limit"], 10)
        self.assertTrue(watch["read_comments"])
        self.assertEqual(watch["comments_limit"], 3)
        with self.assertRaisesRegex(ValueError, "الإرسال التلقائي متوقف"):
            control.validate_settings(self.form | {"authorization": "auto"})
        with self.assertRaisesRegex(ValueError, "الإرسال التلقائي متوقف"):
            control.validate_settings(self.form | {"authorization": "auto", "confirm_auto": "yes"})

    def test_page_uses_owner_profile_for_preview_without_reply_settings(self):
        with tempfile.TemporaryDirectory() as td, \
             patch.object(control.scout, "CONFIG", Path(td) / "watch.json"), \
             patch.object(control.reply, "SETTINGS", Path(td) / "reply.json"), \
             patch.object(control.reply, "OWNER_PROFILE", Path(td) / "owner.json"), \
             patch.object(control, "DRAFTS", Path(td) / "drafts.json"), \
             patch.object(control, "candidates", return_value=(
                 [{"url": "https://khamsat.com/community/requests/123-python", "title": "Python"}], {})):
            page = control.render("token")
            self.assertIn("ملفك المحلي", page)
            self.assertNotIn('action="/preview"', page)
            control.scout.save(Path(td) / "owner.json", {"facts": []})
            page = control.render("token")
            self.assertIn('action="/preview"', page)
            self.assertIn("رابط معرض الأعمال HTTPS (اختياري)", page)
            self.assertNotIn("الخدمة التي تقدمها فعلًا", page)
            self.assertLess(page.index('name="load_more_clicks"'), page.index('</form>'))

    def test_batch_progress_does_not_reload_edited_draft(self):
        with tempfile.TemporaryDirectory() as td, \
             patch.object(control, "BATCH_STATUS", Path(td) / "batch.json"), \
             patch.object(control, "candidates", return_value=([], {})):
            control.scout.save(control.BATCH_STATUS, {
                "pid": control.os.getpid(), "running": True, "total": 2, "completed": 1, "errors": [],
            })
            page = control.render("token")
        self.assertNotIn('http-equiv=refresh', page)
        self.assertIn('href="/">حدّث التقدم', page)

    def test_failed_shortlist_is_visible_without_draft_button(self):
        with tempfile.TemporaryDirectory() as td, \
             patch.object(control.scout, "STATE", Path(td)), \
             patch.object(control, "candidates", return_value=([], {})):
            control.scout.save(Path(td) / "queue.json", {"last_scan": {
                "errors": ["12: وصف مفقود"], "failed": [{
                    "url": "https://khamsat.com/community/requests/12-python",
                    "title": "مشروع Python", "reason": "وصف مفقود"}],
            }})
            page = control.render("token")
        self.assertIn("مشروع Python", page)
        self.assertIn('href="https://khamsat.com/community/requests/12-python"', page)
        self.assertNotIn('action="/preview"', page)

    def test_old_length_warning_is_rechecked_against_current_rules(self):
        item = {"id": "123", "url": "https://khamsat.com/community/requests/123-python",
                "title": "Python", "visible_text": "Need Python"}
        with tempfile.TemporaryDirectory() as td, \
             patch.object(control.scout, "CONFIG", Path(td) / "watch.json"), \
             patch.object(control.reply, "SETTINGS", Path(td) / "reply.json"), \
             patch.object(control.reply, "OWNER_PROFILE", Path(td) / "owner.json"), \
             patch.object(control, "DRAFTS", Path(td) / "drafts.json"), \
             patch.object(control, "candidates", return_value=([item], {})):
            control.scout.save(control.reply.OWNER_PROFILE, {"facts": []})
            control.scout.save(control.DRAFTS, {"requests": {"123": {
                "url": item["url"], "text": "ا" * 1283,
                "validation_error": "طول الرد 1283 حرفًا؛ المطلوب من 80 إلى 1000 حرف",
            }}})
            page = control.render("token")
            self.assertIn("ا" * 1283, page)
            self.assertNotIn("المطلوب من 80 إلى 1000", page)
            self.assertNotIn("المسودة تحتاج تعديل", page)

    def test_same_page_origin_variants_and_cross_site_rejection(self):
        for headers in (
            {"Origin": "http://127.0.0.1:8788", "Sec-Fetch-Site": "same-origin"},
            {"Origin": "null", "Sec-Fetch-Site": "same-origin"},
            {"Sec-Fetch-Site": "same-origin"},
        ):
            self.assertTrue(control.same_page_request(headers))
        for headers in (
            {"Origin": "https://example.com"},
            {"Sec-Fetch-Site": "cross-site"},
            {"Origin": "null", "Referer": "https://example.com/form"},
        ):
            self.assertFalse(control.same_page_request(headers))

    def test_limits_and_optional_portfolio_are_validated(self):
        with self.assertRaisesRegex(ValueError, "Daily limit"):
            control.validate_settings(self.form | {"max_per_day": "6"})
        _, configured = control.validate_settings(self.form | {"reply_selector": "", "submit_selector": ""})
        self.assertEqual(configured["reply_selector"], control.reply.DEFAULT_REPLY["reply_selector"])
        self.assertEqual(configured["submit_selector"], control.reply.DEFAULT_REPLY["submit_selector"])
        _, cfg = control.validate_settings(self.form | {"service": "", "proof": "", "portfolio_url": ""})
        self.assertEqual(cfg["portfolio_url"], "")
        with self.assertRaisesRegex(ValueError, "Portfolio"):
            control.validate_settings(self.form | {"portfolio_url": "http://example.com"})

    def test_pending_receipt_blocks_preview_and_duplicate_post(self):
        item = {"id": "123", "url": "https://khamsat.com/community/requests/123-python",
                "title": "Python", "visible_text": "Need Python"}
        with patch.object(control, "candidates", return_value=([item], {"123": {"status": "pending"}})), \
             patch.object(control.reply, "compose") as compose:
            with self.assertRaisesRegex(ValueError, "Already attempted"):
                control.preview("123")
            compose.assert_not_called()

    def test_batch_prepares_selected_drafts_without_submission(self):
        with tempfile.TemporaryDirectory() as td, \
             patch.object(control, "BATCH_STATUS", Path(td) / "batch.json"), \
             patch.object(control.reply, "instructions", return_value={"authorization": "review"}), \
             patch.object(control, "candidate", return_value={"id": "123"}), \
             patch.object(control, "preview", return_value="") as preview, \
             patch.object(control.reply, "run") as submit:
            control.start_batch_preview(["123", "124"])
            control.BATCH_THREAD.join(timeout=2)
            self.assertFalse(control.BATCH_THREAD.is_alive())
            self.assertEqual(control.scout.load(control.BATCH_STATUS)["completed"], 2)
            self.assertEqual([call.args[0] for call in preview.call_args_list], ["123", "124"])
            submit.assert_not_called()
            with self.assertRaisesRegex(ValueError, "10"):
                control.start_batch_preview(["123"] * 11)

    def test_overlong_model_reply_is_saved_for_edit_but_cannot_be_sent(self):
        item = {"id": "123", "url": "https://khamsat.com/community/requests/123-python",
                "title": "Python", "visible_text": "Need Python"}
        with tempfile.TemporaryDirectory() as td, patch.object(control, "DRAFTS", Path(td) / "drafts.json"), \
             patch.object(control, "candidate", return_value=item), \
             patch.object(control, "candidates", return_value=([item], {})), \
             patch.object(control.reply, "instructions", return_value={"portfolio_url": "", "keywords": ["Python"], "exclude_terms": []}), \
             patch.object(control.reply, "generate", return_value="ا" * 2001), \
             patch.object(control.scout, "matches", return_value=True), \
             patch.object(control.reply, "run") as run:
            warning = control.preview("123")
            self.assertIn("الحد الأقصى", warning)
            self.assertEqual(control.scout.load(control.DRAFTS)["requests"]["123"]["text"], "ا" * 2001)
            with self.assertRaisesRegex(ValueError, "الحد الأقصى"):
                control.submit_reviewed("123", "ا" * 2001)
            run.assert_not_called()

    def test_review_submission_requires_prior_preview_and_mode(self):
        item = {"id": "123", "url": "https://khamsat.com/community/requests/123-python"}
        with patch.object(control, "candidate", return_value=item), \
             patch.object(control, "private_json", return_value={"requests": {}}), \
             patch.object(control.reply, "instructions", return_value={"portfolio_url": "https://example.com/work"}), \
             patch.object(control.reply, "run") as run:
            with self.assertRaisesRegex(ValueError, "Preview this request"):
                control.submit_reviewed("123", "Some text")
            run.assert_not_called()

    def test_learning_only_after_confirmed_review_submission(self):
        item = {"id": "123", "url": "https://khamsat.com/community/requests/123-python"}
        valid = "أقدر أساعدك في بناء أداة Python المطلوبة. نبدأ بتحديد المدخلات والمخرجات ثم ننفذ نسخة أولية قابلة للتجربة."
        with tempfile.TemporaryDirectory() as td, patch.object(control, "DRAFTS", Path(td) / "drafts.json"), \
             patch.object(control, "candidate", return_value=item), \
             patch.object(control.reply, "instructions", return_value={"portfolio_url": ""}), \
             patch.object(control.reply, "remember_edit") as learn, \
             patch.object(control.reply, "run") as run:
            control.scout.save(control.DRAFTS, {"requests": {"123": {
                "url": item["url"], "text": "مسودة أولى",
                "created_at": control.datetime.now(control.timezone.utc).isoformat(),
            }}})
            run.return_value = []
            self.assertEqual(control.submit_reviewed("123", valid), [])
            learn.assert_not_called()
            run.return_value = [f'Submitted: {item["url"]}']
            learn.return_value = True
            result = control.submit_reviewed("123", valid)
            self.assertIn("حُفظ تعديلك", result[1])
            learn.assert_called_once_with("123", "مسودة أولى", valid)

    def test_tick_respects_interval_and_does_not_post_with_old_auto_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            watch = root / "watch.json"
            config = root / "reply.json"
            queue = root / "queue.json"
            control.scout.save(watch, {"keywords": ["Python"], "exclude_terms": []})
            control.scout.save(config, {"authorization": "auto", "enabled": True,
                                        "scan_interval_minutes": 30})
            with patch.object(control.scout, "CONFIG", watch), patch.object(control.reply, "SETTINGS", config), \
                 patch.object(control.scout, "STATE", root), patch.object(control.scout, "scan") as scan, \
                 patch.object(control.reply, "run") as run:
                self.assertIn("unsent", control.tick())
                scan.assert_called_once()
                run.assert_not_called()
                control.scout.save(queue, {"checked_at": "2099-01-01T00:00:00+00:00"})
                self.assertIn("not due", control.tick())
                scan.assert_called_once()

    def test_review_button_only_prepares_one_time_confirmation(self):
        item = {"id": "123", "title": "Python API",
                "url": "https://khamsat.com/community/requests/123-python"}
        cfg = {"portfolio_url": ""}
        draft = {"text": "مسودة"}
        with patch.object(control, "checked_draft", return_value=(item, cfg, draft, "الرد الموافق عليه")), \
             patch.object(control, "candidate", return_value=item), \
             patch.object(control.reply, "run") as run, \
             patch.object(control, "submit_reviewed", return_value=["Submitted"]) as submit:
            confirmation = control.begin_confirmation("123", "الرد الموافق عليه")
            run.assert_not_called()
            submit.assert_not_called()
            with self.assertRaisesRegex(ValueError, "حدد الموافقة"):
                control.confirm_submission("123", confirmation["approval"], "")
            submit.assert_not_called()
            self.assertEqual(control.confirm_submission("123", confirmation["approval"], "yes"), ["Submitted"])
            submit.assert_called_once_with("123", "الرد الموافق عليه")
            with self.assertRaisesRegex(ValueError, "استُخدم"):
                control.confirm_submission("123", confirmation["approval"], "yes")

    def test_confirmation_normalizes_multiline_form_submission(self):
        item = {"id": "123", "title": "Python API",
                "url": "https://khamsat.com/community/requests/123-python"}
        draft = {"url": item["url"], "text": "مسودة",
                 "created_at": datetime.now(timezone.utc).isoformat()}
        with patch.object(control.reply, "instructions", return_value={"portfolio_url": ""}), \
             patch.object(control, "candidate", return_value=item), \
             patch.object(control, "candidates", return_value=([item], {})), \
             patch.object(control, "private_json", return_value={"requests": {"123": draft}}):
            confirmation = control.begin_confirmation("123", "أول سطر\r\nثاني سطر")
        self.assertEqual(confirmation["text"], "أول سطر\nثاني سطر")

    def test_confirmation_page_shows_exact_text_and_separate_button(self):
        confirmation = {"id": "123", "title": "مشروع Python", "text": "النص الذي راجعته",
                        "url": "https://khamsat.com/community/requests/123-python", "approval": "one-time"}
        with patch.object(control, "candidates", return_value=([], {})):
            page = control.render("token", confirmation=confirmation)
        self.assertIn('action="/confirm-submit"', page)
        self.assertIn("النص الذي راجعته", page)
        self.assertIn("أؤكد النشر على خمسات", page)
        self.assertNotIn("Allow — إرسال تلقائي", page)

    def test_submit_http_route_only_prepares_confirmation(self):
        body = urlencode({"csrf": "secret", "id": "123", "text": "نص راجعته"}).encode()
        request = MagicMock()
        request.path = "/submit"
        request.headers = {"Host": "127.0.0.1:8788", "Origin": "http://127.0.0.1:8788",
                           "Content-Length": str(len(body))}
        request.token = "secret"
        request.rfile = BytesIO(body)
        request.allowed.return_value = True
        confirmation = {"approval": "single-use", "id": "123", "text": "نص راجعته"}
        with patch.object(control, "begin_confirmation", return_value=confirmation) as begin, \
             patch.object(control, "confirm_submission") as submit, \
             patch.object(control.reply, "run") as run, \
             patch.object(control, "render", return_value="confirmation page") as render:
            control.Handler.do_POST(request)
        begin.assert_called_once_with("123", "نص راجعته")
        render.assert_called_once_with("secret", unittest.mock.ANY, confirmation=confirmation)
        request.respond.assert_called_once_with("confirmation page")
        submit.assert_not_called()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
