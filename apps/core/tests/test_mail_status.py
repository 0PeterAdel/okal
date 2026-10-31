"""Authenticated local status is evidence, not a live provider health claim."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.mail.contracts import Config
from okal_core.mail.private import write_private
from okal_core.mail.state import MailState
from okal_core.models import SummaryInput
from okal_core.store import Store


class MailStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "state", clock=lambda: 100)
        self.cfg = Config(
            account="owner@example.com", model="local:test", model_digest="a" * 64
        )
        self.path = self.store.directory / "mail" / "config.json"
        self.headers = {
            "Authorization": "Bearer " + self.store.issue_device("test")["token"]
        }
        self.client = TestClient(
            create_app(self.store),
            base_url="http://127.0.0.1:8766",
            client=("127.0.0.1", 1234),
        )
        self.addCleanup(self.client.close)
        self.addCleanup(patch.stopall)
        patch(
            "socket.socket.connect", side_effect=AssertionError("no external network")
        ).start()

    def status(self):
        response = self.client.get("/api/v1/capabilities", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        return response.json()["mail"]

    def configure(self, **changes):
        write_private(self.path, {**self.cfg.model_dump(), **changes})

    def complete(self, account=None):
        state = MailState(self.store)
        account = account or self.cfg.account
        key, _ = state.begin(account, 1, 2)
        state.complete(key, account, 1, 2, "Synthetic digest", [])
        return state

    def test_status_requires_token(self):
        self.assertEqual(self.client.get("/api/v1/capabilities").status_code, 401)

    def test_absent_status_does_not_create_mail_tables_or_directory(self):
        self.assertEqual(self.status()["configuration"], "absent")
        self.assertFalse(self.path.parent.exists())
        with self.store.connect() as db:
            self.assertEqual(
                db.execute(
                    "SELECT name FROM sqlite_master WHERE name LIKE 'mail_%'"
                ).fetchall(),
                [],
            )

    def test_configuration_is_not_authorization_or_inference_success(self):
        self.configure()
        result = self.status()
        self.assertEqual(result["configuration"], "configured")
        self.assertEqual(result["authorization"], "not_checked")
        self.assertIsNone(result["latest_success"])
        self.assertNotIn(self.cfg.account, json.dumps(result))
        self.assertNotIn(self.cfg.model_digest, json.dumps(result))

    def test_demo_mail_never_counts_as_live_success(self):
        self.configure()
        self.store.record_success(
            SummaryInput(
                workflow="mail",
                account_ref="fixture",
                occurrence="demo",
                title="Demo",
                body="fixture",
                data_kind="fixture",
            )
        )
        self.assertIsNone(self.status()["latest_success"])

    def test_empty_success_and_new_failed_attempt_are_distinct(self):
        self.configure()
        state = self.complete()
        key, _ = state.begin(self.cfg.account, 2, 3)
        state.fail(key, "synthetic_failure")
        with self.store.connect() as db, db:
            db.execute("UPDATE mail_jobs SET updated=101 WHERE id=?", (key,))
        result = self.status()
        self.assertEqual(result["latest_success"]["count"], 0)
        self.assertEqual(result["latest_attempt"]["status"], "failed")
        self.assertNotIn("error", result["latest_attempt"])

    def test_other_account_history_is_not_exposed(self):
        self.configure()
        self.complete("other@example.com")
        self.assertIsNone(self.status()["latest_success"])
        self.assertIsNone(self.status()["latest_attempt"])

    def test_invalid_config_and_future_schema_fail_closed(self):
        self.configure()
        self.path.chmod(0o644)
        self.assertEqual(self.status()["configuration"], "invalid")
        self.path.chmod(0o600)
        self.complete()
        with self.store.connect() as db, db:
            db.execute("UPDATE mail_meta SET value='999' WHERE key='version'")
        result = self.status()
        self.assertEqual(result["history"], "unavailable")
        self.assertIsNone(result["latest_success"])

    def test_schedule_and_send_are_configuration_not_http_permissions(self):
        self.configure(daily_at="09:00", send_enabled=True)
        result = self.status()
        self.assertEqual(result["daily_at"], "09:00")
        self.assertTrue(result["local_send_enabled"])
        caps = self.client.get("/api/v1/capabilities", headers=self.headers).json()
        self.assertFalse(caps["external_writes"])
        self.assertEqual(caps["permissions"], ["inbox:read"])
