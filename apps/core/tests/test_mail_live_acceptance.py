"""Live operator probes are tested without Gmail, OAuth or systemd."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "mail-live-acceptance.py"
spec = importlib.util.spec_from_file_location("okal_live_acceptance", SCRIPT)
accept = importlib.util.module_from_spec(spec)
spec.loader.exec_module(accept)


class AcceptanceScriptTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name) / "okal-core"
        self.state.mkdir(mode=0o700)
        (self.state / "mail").mkdir(mode=0o700)
        accept.write_private(self.state / "mail" / "config.json", {
            "account": "owner@example.com", "sync_enabled": True,
            "send_enabled": False
        })
        self.db = sqlite3.connect(self.state / "core.sqlite3")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE mail_sync_state(
                account TEXT PRIMARY KEY,cursor TEXT,
                last_result TEXT,last_count INTEGER
            );
            CREATE TABLE mail_sync_failures(account TEXT PRIMARY KEY,code TEXT);
            CREATE TABLE mail_sync_insights(
                account TEXT,message_id TEXT,metadata TEXT
            );
            INSERT INTO mail_sync_state VALUES
                ('owner@example.com','100','history_delta',0);
        """)
        self.db.commit()

    def invoke(self, phase):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = accept.main([phase, "--state-dir", str(self.state)])
        return code, json.loads(out.getvalue())

    def test_counts_only_unique_probe_ids_and_hides_private_body(self):
        self.db.execute("INSERT INTO mail_sync_insights VALUES (?,?,?)",
                        ("owner@example.com", "aa", json.dumps({
                            "subject": "OKAL-LIVE-TEST-AR",
                            "sender": "private@domain.com",
                            "body": "secret body never printed"})))
        self.db.execute("INSERT INTO mail_sync_insights VALUES (?,?,?)",
                        ("owner@example.com", "aa",
                         json.dumps({"subject": "OKAL-LIVE-TEST-AR"})))
        self.db.commit()
        result = accept.status(self.state, "owner@example.com", ["OKAL-LIVE-TEST-AR"])
        self.assertEqual(result["matched_distinct_messages"], [1])
        self.assertNotIn("private@domain", str(result))
        self.assertNotIn("secret body", str(result))

    def test_explicit_outage_stops_core_only_and_saves_private_probe(self):
        calls = []
        with patch.object(accept, "systemd", side_effect=lambda action: calls.append(action)):
            code, data = self.invoke("outage-start")
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["stop"])
        self.assertTrue(data["core_service_stopped"])
        probe = accept.load_probe(self.state)
        self.assertEqual(probe["cursor_before"], "100")
        self.assertNotIn("owner@example.com", str(data))
        self.assertEqual(
            (self.state / "mail/live-acceptance.json").stat().st_mode & 0o777,
            0o600
        )
        code, blocked = self.invoke("outage-start")
        self.assertEqual((code, blocked["safe_error_code"]), (
            1, "existing_outage_probe_must_be_finished"
        ))

    def test_restart_requires_both_messages_once_and_new_checkpoint(self):
        with patch.object(accept, "systemd") as systemd:
            self.invoke("outage-start")
            code, response = self.invoke("outage-finish")
            self.assertEqual(code, 0)
            self.assertTrue(response["core_service_active"])
            self.assertEqual(systemd.call_args_list[-1].args, ("start",))
        code, result = self.invoke("check")
        self.assertEqual(code, 2)
        self.assertFalse(result["gmail_sync_probes_passed"])
        probe = accept.load_probe(self.state)
        self.db.execute(
            "UPDATE mail_sync_state SET cursor='300' WHERE account='owner@example.com'"
        )
        for i, subject in enumerate((probe["ar_subject"], probe["en_subject"])):
            self.db.execute(
                "INSERT INTO mail_sync_insights VALUES (?,?,?)",
                ("owner@example.com", f"{i+1:02x}", json.dumps({"subject": subject}))
            )
        self.db.commit()
        code, result = self.invoke("check")
        self.assertEqual(code, 0)
        self.assertTrue(result["gmail_sync_probes_passed"])
        self.assertTrue(result["human_quality_review_still_required"])

    def test_provider_error_or_unadvanced_cursor_never_passes(self):
        with patch.object(accept, "systemd"):
            self.invoke("outage-start")
            self.invoke("outage-finish")
        probe = accept.load_probe(self.state)
        for i, subject in enumerate((probe["ar_subject"], probe["en_subject"])):
            self.db.execute(
                "INSERT INTO mail_sync_insights VALUES (?,?,?)",
                ("owner@example.com", f"{i+1:02x}", json.dumps({"subject": subject}))
            )
        self.db.execute(
            "INSERT INTO mail_sync_failures VALUES (?,?)",
            ("owner@example.com", "authorization_required")
        )
        self.db.commit()
        code, result = self.invoke("check")
        self.assertEqual(code, 2)
        self.assertEqual(result["safe_error_code"], "authorization_required")

    def test_readonly_preflight_blocks_missing_oauth(self):
        code, data = self.invoke("preflight")
        self.assertEqual(code, 1)
        self.assertEqual(data["safe_error_code"], "oauth_token_missing_authorize_locally")


if __name__ == "__main__":
    unittest.main()
