"""No-send live audit unit tests; never contact real Gmail or Ollama."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock

from okal_core.mail.contracts import Config, Insight

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "mail-live-readonly-audit.py"
spec = importlib.util.spec_from_file_location("okal_readonly_live_audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class NoSendAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.state = Path(temp.name) / "okal-core"
        self.state.mkdir(mode=0o700)
        self.db = sqlite3.connect(self.state / "core.sqlite3")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE mail_sync_state(
                account TEXT PRIMARY KEY, cursor TEXT, checked_at INTEGER,
                attempted_at INTEGER, last_result TEXT, last_count INTEGER
            );
            CREATE TABLE mail_sync_failures(account TEXT PRIMARY KEY, code TEXT);
            CREATE TABLE mail_sync_insights(account TEXT, message_id TEXT,
                                            metadata TEXT, insight TEXT);
            CREATE TABLE mail_sync_quarantine(account TEXT, message_id TEXT);
            CREATE TABLE mail_sync_seen(account TEXT, message_id TEXT);
            INSERT INTO mail_sync_state VALUES(
                'owner@example.com','100',1800000000,1800000000,'history_delta',1
            );
            INSERT INTO mail_sync_seen VALUES('owner@example.com','ab');
        """)
        self.cfg = Config(
            account="owner@example.com", model="local:test",
            model_digest="a" * 64,
        )
        self.insert("ab", "Inbox reminder", "action")
        self.db.commit()
        api = MagicMock()
        api.history_changes.return_value = ("120", ["ab"], 0)
        api.ids.return_value = ["ab"]
        api.call.return_value = {"id": "ab", "threadId": "ff"}
        self.api = api

    def insert(self, mid, subject, category):
        self.db.execute("INSERT INTO mail_sync_insights VALUES(?,?,?,?)", (
            "owner@example.com", mid,
            json.dumps({"id": mid, "subject": subject,
                        "sender": "PRIVATE SENDER", "body_sha256": "hash"}),
            Insight(
                source_id=mid, category=category,
                summary="Private summary must never appear", suggested_action=""
            ).model_dump_json(),
        ))

    def test_reconciles_stored_source_against_native_gmail_without_sending(self):
        result = audit.audit(self.state, self.cfg, self.api, now=1800000100)
        self.assertTrue(result["mail_reconciliation_passed"])
        self.assertEqual(result["native_gmail_messages_verified"], 1)
        self.assertEqual(result["historic_live_test_subjects"], 0)
        self.assertEqual(result["unprocessed_new_gmail_history_ids"], 0)
        self.assertFalse(result["specific_outage_catchup_proven"])
        self.assertFalse(result["owner_must_send_more_test_messages"])
        self.assertNotIn("PRIVATE SENDER", json.dumps(result))
        self.assertNotIn("Private summary", json.dumps(result))
        self.api.service.users.return_value.messages.return_value.get.assert_called_once()
        self.assertEqual(
            self.api.service.users.return_value.messages.return_value.get.call_args.kwargs["format"],
            "metadata",
        )

    def test_duplicate_saved_ids_block_acceptance(self):
        self.insert("ab", "Duplicate", "action")
        self.db.commit()
        result = audit.audit(self.state, self.cfg, self.api, now=1800000100)
        self.assertEqual(result["stored_duplicate_source_ids"], 1)
        self.assertFalse(result["mail_reconciliation_passed"])

    def test_mismatched_model_reference_blocks_acceptance(self):
        self.db.execute(
            "UPDATE mail_sync_insights SET insight=? WHERE message_id='ab'",
            (Insight(
                source_id="wrong", category="action", summary="Private",
                suggested_action=""
            ).model_dump_json(),),
        )
        self.db.commit()
        result = audit.audit(self.state, self.cfg, self.api, now=1800000100)
        self.assertEqual(result["stored_source_mismatches_in_sample"], 1)
        self.assertFalse(result["mail_reconciliation_passed"])

    def test_unprocessed_gmail_messages_are_reported_not_hidden(self):
        self.api.history_changes.return_value = ("150", ["ab", "cd"], 0)
        self.api.ids.return_value = ["ab", "cd"]
        result = audit.audit(self.state, self.cfg, self.api, now=1800000100)
        self.assertEqual(result["unprocessed_new_gmail_history_ids"], 1)
        self.assertEqual(result["recent_visible_messages_not_yet_seen"], 1)
        self.assertTrue(result["mail_reconciliation_passed"])

    def test_prior_test_subjects_are_counted_without_revealing_subjects(self):
        self.insert("ce", "OKAL-LIVE-TEST-AR", "information")
        self.db.execute("INSERT INTO mail_sync_seen VALUES('owner@example.com','ce')")
        self.db.commit()
        self.api.ids.return_value = ["ab", "ce"]
        self.api.history_changes.return_value = ("150", ["ab", "ce"], 0)
        self.api.call.side_effect = [
            {"id": "ce", "threadId": "ff"},
            {"id": "ab", "threadId": "ff"},
        ]
        result = audit.audit(self.state, self.cfg, self.api, now=1800000100)
        self.assertEqual(result["historic_live_test_subjects"], 1)
        self.assertTrue(result["mail_reconciliation_passed"])
        self.assertNotIn("OKAL-LIVE-TEST-AR", str(result))


if __name__ == "__main__":
    unittest.main()
