"""Local task lifecycle / persisted Gmail evidence tests; no Google network."""
import contextlib
from datetime import datetime
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.__main__ import main as core_main
from okal_core.mail.contracts import Insight
from okal_core.mail.history import HistoryState
from okal_core.store import Store
from okal_core.tasks import TaskBoard, due_timestamp


class LocalTasksTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name) / "state"
        self.store = Store(self.directory, clock=lambda: 1800000000)
        self.board = TaskBoard(self.store)

    def add_source(self, mid="aa", source="aa", provider_mid=None):
        HistoryState(self.store)
        with self.store.connect() as db, db:
            db.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
                ("run-" + mid, "mail", "account", "message-" + mid,
                 "digest", 1800000000, "succeeded"),
            )
            db.execute(
                "INSERT INTO mail_sync_insights VALUES(?,?,?,?,?)",
                ("run-" + mid, "owner@example.com", mid,
                 json.dumps({"id": provider_mid or mid,
                             "subject": "Meeting tomorrow",
                             "sender": "Untrusted <attacker@example.com>"}),
                 Insight(
                     source_id=source, category="action",
                     summary="Private summary", suggested_action="Wire money",
                 ).model_dump_json()),
            )

    def test_manual_task_persists_restart_and_complete_is_idempotent(self):
        self.assertEqual(self.board.list()["items"], [])
        created = self.board.add(
            "Finish proposal", due="2027-01-01T09:00:00+02:00"
        )
        key = created["task_id"]
        self.assertEqual(len(key), 32)
        board = TaskBoard(Store(self.directory, clock=lambda: 1800000000))
        task = board.list()["items"][0]
        self.assertEqual(task["title"], "Finish proposal")
        self.assertEqual(task["due_at"],
                         int(datetime.fromisoformat(
                             "2027-01-01T07:00:00+00:00").timestamp()))
        self.assertEqual(task["source_type"], "manual")
        self.assertFalse(board.list()["external_writes"])
        self.assertFalse(board.transition(key, "done")["replayed"])
        self.assertTrue(board.transition(key, "done")["replayed"])
        self.assertEqual(board.list()["items"], [])
        self.assertEqual(board.list("done")["items"][0]["status"], "done")
        with self.assertRaisesRegex(ValueError, "not_open"):
            board.transition(key, "dismissed")

    def test_mail_preview_does_not_persist_task_without_explicit_approval(self):
        self.add_source()
        preview = self.board.from_mail("owner@example.com", "aa")
        self.assertEqual(preview["status"], "approval_required")
        self.assertIn("Review email", preview["proposed_title"])
        self.assertIsNone(preview["due_at"])
        self.assertEqual(self.board.list()["total_in_sample"], 0)
        made = self.board.from_mail(
            "owner@example.com", "aa",
            title="My verified follow-up",
            due="2027-01-02T09:30:00+02:00", approve=True,
        )
        replay = self.board.from_mail("owner@example.com", "aa",
                                      approve=True)
        self.assertEqual(replay["status"], "already_recorded")
        self.assertEqual(made["task_id"], replay["task_id"])
        self.assertEqual(self.board.list()["total_in_sample"], 1)
        self.assertIn("mail.google.com", self.board.list()["items"][0]["source_link"])
        self.assertEqual(self.board.list()["items"][0]["title"],
                         "My verified follow-up")

    def test_wrong_provenance_never_creates_task(self):
        self.add_source(mid="bb", source="cc")
        with self.assertRaisesRegex(ValueError, "provenance_invalid"):
            self.board.from_mail("owner@example.com", "bb", approve=True)
        self.assertFalse(self.board.list()["items"])

    def test_other_account_or_unsaved_message_not_authorized(self):
        self.add_source()
        with self.assertRaisesRegex(ValueError, "source_email_not_in"):
            self.board.from_mail("other@example.com", "aa", approve=True)
        with self.assertRaisesRegex(ValueError, "source_email_not_in"):
            self.board.from_mail("owner@example.com", "ff", approve=True)
        with self.assertRaisesRegex(ValueError, "invalid_source_message_id"):
            self.board.from_mail("owner@example.com", "../token", approve=True)

    def test_invalid_title_due_and_control_characters_rejected(self):
        for value in ("", "x" * 181, "hello\nthere"):
            with self.assertRaises(ValueError):
                self.board.add(value)
        for value in ("2027-01-01T10:00:00", "yesterday",
                      "2222-01-01T08:00:00Z"):
            with self.assertRaisesRegex(ValueError, "due_requires"):
                due_timestamp(value)

    def test_overdue_count_is_from_confirmed_local_deadline(self):
        self.board.add("Past due", due="2020-01-01T10:00:00+02:00")
        self.board.add("Unscheduled")
        r = self.board.list()
        self.assertEqual(r["overdue_in_sample"], 1)
        self.assertIsNone(r["items"][-1]["due_at"])

    def test_web_api_is_read_only_both_local_and_protected(self):
        self.board.add("Saved task")
        with TestClient(create_app(self.store, require_read_key=False),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1234)) as client:
            r = client.get("/api/v1/tasks")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["total_in_sample"], 1)
            self.assertEqual(client.post("/api/v1/tasks", json={}).status_code, 401)
        with TestClient(create_app(self.store, require_read_key=True),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1234)) as client:
            self.assertEqual(client.get("/api/v1/tasks").status_code, 401)
            token = self.store.issue_device("owner")["token"]
            r = client.get("/api/v1/tasks",
                           headers={"Authorization": "Bearer " + token})
            self.assertEqual(r.status_code, 200)

    def test_owner_cli_works_offline_without_gmail_auth(self):
        args = ["okal", "--state-dir", str(self.directory),
                "tasks", "add", "--title", "Plan the day"]
        output = io.StringIO()
        with patch.object(sys, "argv", args), contextlib.redirect_stdout(output):
            self.assertEqual(core_main(), 0)
        row = json.loads(output.getvalue())
        self.assertEqual(row["status"], "open")
        output = io.StringIO()
        with patch.object(sys, "argv", ["okal", "--state-dir",
                    str(self.directory), "tasks", "list"]), \
                contextlib.redirect_stdout(output):
            self.assertEqual(core_main(), 0)
        self.assertEqual(json.loads(output.getvalue())["total_in_sample"], 1)


if __name__ == "__main__":
    unittest.main()
