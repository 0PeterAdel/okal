"""Authorization, refresh and duplicate gates for the local Khamsat page."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


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

    def test_review_is_default_and_auto_requires_explicit_confirmation(self):
        _, config = control.validate_settings(self.form)
        self.assertFalse(config["enabled"])
        self.assertEqual(config["authorization"], "review")
        with self.assertRaisesRegex(ValueError, "Confirm autonomous"):
            control.validate_settings(self.form | {"authorization": "auto"})
        with patch.object(control.reply, "profile_facts", return_value=["Verified Python project"]):
            _, auto = control.validate_settings(self.form | {"authorization": "auto", "confirm_auto": "yes"})
        self.assertTrue(auto["enabled"])

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

    def test_limits_and_proof_are_validated_before_auto(self):
        with self.assertRaisesRegex(ValueError, "Daily limit"):
            control.validate_settings(self.form | {"max_per_day": "6"})
        with patch.object(control.reply, "profile_facts", return_value=["Verified Python project"]):
            _, configured = control.validate_settings(self.form | {
                "authorization": "auto", "confirm_auto": "yes", "reply_selector": "", "submit_selector": ""})
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

    def test_overlong_model_reply_is_saved_for_edit_but_cannot_be_sent(self):
        item = {"id": "123", "url": "https://khamsat.com/community/requests/123-python",
                "title": "Python", "visible_text": "Need Python"}
        with tempfile.TemporaryDirectory() as td, patch.object(control, "DRAFTS", Path(td) / "drafts.json"), \
             patch.object(control, "candidate", return_value=item), \
             patch.object(control, "candidates", return_value=([item], {})), \
             patch.object(control.reply, "instructions", return_value={"portfolio_url": ""}), \
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

    def test_tick_respects_interval_and_does_not_post_in_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            watch = root / "watch.json"
            config = root / "reply.json"
            queue = root / "queue.json"
            control.scout.save(watch, {"keywords": ["Python"], "exclude_terms": []})
            control.scout.save(config, {"authorization": "review", "scan_interval_minutes": 30})
            with patch.object(control.scout, "CONFIG", watch), patch.object(control.reply, "SETTINGS", config), \
                 patch.object(control.scout, "STATE", root), patch.object(control.scout, "scan") as scan, \
                 patch.object(control.reply, "run") as run:
                self.assertIn("review mode", control.tick())
                scan.assert_called_once()
                run.assert_not_called()
                control.scout.save(queue, {"checked_at": "2099-01-01T00:00:00+00:00"})
                self.assertIn("not due", control.tick())
                scan.assert_called_once()


if __name__ == "__main__":
    unittest.main()
