"""Morning briefing and Gmail trash regression tests. No live Google calls."""
import contextlib
from datetime import datetime
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.__main__ import main as core_main
from okal_core.mail.contracts import Config, Insight, MailError
from okal_core.mail.history import HistoryState, recent_evidence
from okal_core.mail.private import root, write_private
from okal_core.mail.trash import apply, preview
from okal_core.morning import morning_brief
from okal_core.store import Store
from okal_core.tasks import TaskBoard


class MorningAndTrashTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.directory = Path(t.name) / "state"
        cairo = ZoneInfo("Africa/Cairo")
        self.now = int(datetime(2026, 11, 1, 9, 0, tzinfo=cairo).timestamp())
        self.store = Store(self.directory, clock=lambda: self.now)
        self.cfg = Config(account="owner@example.com", model="local:test",
                          model_digest="a" * 64, sync_enabled=True,
                          trash_enabled=True)
        write_private(root(self.store) / "config.json", self.cfg.model_dump())
        HistoryState(self.store)
        with self.store.connect() as db, db:
            db.execute(
                "INSERT INTO mail_sync_state VALUES(?,?,?,?,'history_delta',NULL,0)",
                (self.cfg.account, "100", self.now - 60, self.now - 60)
            )
        self.api = MagicMock()
        self.api.service.users.return_value.messages.return_value.get.side_effect = (
            lambda **kwargs: ("get", kwargs["id"])
        )
        self.api.call.side_effect = self.native_response
        self.api.move_to_trash.side_effect = (
            lambda mid: {"id": mid, "labelIds": ["TRASH"]}
        )
        self.messages = {}

    def insert(self, mid, subject="Newsletter", category="information",
               labels=None, minutes_old=15, sender="News <news@example.com>"):
        if labels is None:
            labels = ["INBOX", "UNREAD"]
        metadata = {
            "id": mid, "subject": subject, "sender": sender,
            "received_ms": (self.now - minutes_old * 60) * 1000,
            "labels": labels, "attachment_count": 0,
        }
        self.messages[mid] = metadata
        with self.store.connect() as db, db:
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
                       ("run" + mid, "mail", "account", "unique" + mid,
                        "digest", self.now, "succeeded"))
            db.execute("INSERT INTO mail_sync_insights VALUES(?,?,?,?,?)", (
                "run" + mid, self.cfg.account, mid, json.dumps(metadata),
                Insight(source_id=mid, category=category,
                        summary=("راجع الاجتماع الخاص بالمشروع" if category == "action"
                                 else "تحديث جديد بخصوص الشغل"),
                        suggested_action="راجع الرسالة").model_dump_json(),
            ))

    def native_response(self, request, **kwargs):
        _, mid = request
        m = self.messages[mid]
        return {
            "id": mid,
            "labelIds": m["labels"],
            "payload": {"headers": [{"name": "Subject",
                                      "value": m["subject"]}]},
        }

    def test_friendly_morning_only_claims_verified_local_task_deadline(self):
        self.insert("aa", subject="Please review status", category="action")
        self.insert("bb", subject="News", category="information")
        TaskBoard(self.store).add("Project review",
                                  due="2026-11-01T16:30:00+02:00")
        result = morning_brief(self.store)
        self.assertEqual(result["greeting"], "صباح الفل!")
        self.assertEqual(result["today_tasks"][0]["title"], "Project review")
        self.assertEqual(result["today_tasks"][0]["time"], "16:30")
        self.assertEqual(len(result["new_action_emails"]), 1)
        self.assertEqual(len(result["new_info_emails"]), 1)
        self.assertFalse(result["mail_sync_stale"])
        self.assertFalse(result["has_verified_calendar"])
        self.assertTrue(result["voice_ready"])
        self.assertIn("صباح الفل", result["spoken_text"])
        self.assertIn("16:30", result["spoken_text"])
        self.assertIn("تقويم Google", result["spoken_text"])

    def test_stale_mail_does_not_claim_inbox_is_empty(self):
        with self.store.connect() as db, db:
            db.execute("UPDATE mail_sync_state SET checked_at=?",
                       (self.now - 3600,))
        result = morning_brief(self.store)
        self.assertTrue(result["mail_sync_stale"])
        self.assertIn("مش هفترض", result["spoken_text"])

    def test_dashboard_morning_is_read_only_and_can_be_read_with_local_auto_unlock(self):
        with TestClient(create_app(self.store, require_read_key=False),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1234)) as client:
            r = client.get("/api/v1/morning")
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json()["voice_ready"])
            self.assertEqual(client.post("/api/v1/morning", json={}).status_code, 401)
        with TestClient(create_app(self.store, require_read_key=True),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1234)) as client:
            self.assertEqual(client.get("/api/v1/morning").status_code, 401)

    def test_morning_cli_uses_local_records_only(self):
        self.insert("aa", category="action")
        buffer = io.StringIO()
        with patch.object(sys, "argv", [
            "okal", "--state-dir", str(self.directory), "morning",
        ]), contextlib.redirect_stdout(buffer), patch(
            "socket.socket.connect",
            side_effect=AssertionError("network forbidden"),
        ):
            self.assertEqual(core_main(), 0)
        self.assertTrue(json.loads(buffer.getvalue())["voice_ready"])

    def test_trash_preview_and_interactive_apply_is_recoverable_and_deduped(self):
        self.insert("aa", subject="Read later A")
        self.insert("bb", subject="Read later B")
        res = preview(self.store, self.cfg, self.api, ["bb", "aa"])
        self.assertEqual(res["count"], 2)
        self.assertFalse(res["external_writes"])
        self.api.move_to_trash.assert_not_called()
        result = apply(self.store, self.cfg, self.api, ["aa", "bb"],
                       res["approval_digest"])
        self.assertEqual(result["status"], "confirmed_trash")
        self.assertEqual(result["moved"], 2)
        self.assertFalse(result["permanent_delete"])
        self.assertEqual(self.api.move_to_trash.call_count, 2)
        self.assertEqual(len(recent_evidence(self.store, self.cfg.account)), 0)
        with self.assertRaisesRegex(MailError, "previously_attempted"):
            preview(self.store, self.cfg, self.api, ["aa"])

    def test_non_information_and_protected_labels_can_never_be_trashed(self):
        self.insert("aa", category="action")
        with self.assertRaisesRegex(MailError, "only_information"):
            preview(self.store, self.cfg, self.api, ["aa"])
        self.insert("bb", labels=["INBOX", "STARRED"])
        with self.assertRaisesRegex(MailError, "protected"):
            preview(self.store, self.cfg, self.api, ["bb"])
        self.api.move_to_trash.assert_not_called()

    def test_native_subject_change_blocks_request(self):
        self.insert("aa", subject="Saved name")
        self.messages["aa"]["subject"] = "CHANGED"
        with self.assertRaisesRegex(MailError, "native_metadata_changed"):
            # Force mismatch between stored JSON and provider metadata.
            preview(self.store, self.cfg, self.api, ["aa"])
        self.api.move_to_trash.assert_not_called()

    def test_approval_digest_mismatch_prevents_write(self):
        self.insert("aa")
        with self.assertRaisesRegex(MailError, "approval_changed"):
            apply(self.store, self.cfg, self.api, ["aa"], "bad")
        self.api.move_to_trash.assert_not_called()

    def test_write_failure_stays_attempting_and_never_retries(self):
        self.insert("aa")
        digest = preview(self.store, self.cfg, self.api, ["aa"])["approval_digest"]
        self.api.move_to_trash.side_effect = RuntimeError("network unknown")
        with self.assertRaisesRegex(MailError, "uncertain_manual_gmail_review"):
            apply(self.store, self.cfg, self.api, ["aa"], digest)
        with self.store.connect() as db:
            state = db.execute("SELECT status FROM mail_trash_events").fetchone()[0]
        self.assertEqual(state, "attempting")
        with self.assertRaisesRegex(MailError, "previously_attempted"):
            apply(self.store, self.cfg, self.api, ["aa"], digest)
        self.assertEqual(self.api.move_to_trash.call_count, 1)

    def test_trash_permission_disabled_and_batch_limits(self):
        self.insert("aa")
        self.cfg.trash_enabled = False
        with self.assertRaisesRegex(MailError, "permission_disabled"):
            apply(self.store, self.cfg, self.api, ["aa"], "digest")
        with self.assertRaisesRegex(MailError, "1_to_20"):
            preview(self.store, self.cfg, self.api, ["aa"] * 21)


if __name__ == "__main__":
    unittest.main()
