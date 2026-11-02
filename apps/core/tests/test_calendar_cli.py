"""Calendar operator sync failure isolation: no secrets and no false success."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from okal_core.calendar_cli import main, safe_sync_error
from okal_core.calendar_google import CalendarGoogleError
from okal_core.store import Store


def calendar(number, access="reader"):
    return {"id": f"private-{number}@example.invalid", "name": f"Private {number}",
            "timezone": "Africa/Cairo", "access": access,
            "primary": number == 1}


class CalendarBatchCLIExperiments(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = Store(Path(directory.name) / "private",
                           clock=lambda: 1793610000)

    def run_sync(self, calendars, outcomes, args=None):
        stdout, stderr = StringIO(), StringIO()
        with patch("okal_core.calendar_cli._service", return_value=object()), \
             patch("okal_core.calendar_cli.list_calendars",
                   return_value=calendars), \
             patch("okal_core.calendar_cli.sync_calendar",
                   side_effect=outcomes) as sync, \
             redirect_stdout(stdout), redirect_stderr(stderr):
            rc = main(self.store, args or ["sync", "--account", "default", "--all"])
        return rc, stdout.getvalue(), stderr.getvalue(), sync

    def test_one_invalid_interval_does_not_abort_other_calendars(self):
        success = {"received": 3, "written": 2, "external_writes": False}
        rc, output, errors, sync = self.run_sync(
            [calendar(1), calendar(2), calendar(3)],
            [CalendarGoogleError("google_calendar_event_overlong_interval"),
             success, {"received": 0, "written": 0, "external_writes": False}]
        )
        self.assertEqual(rc, 2)
        self.assertEqual(sync.call_count, 3)
        self.assertFalse(errors)
        body = json.loads(output)
        self.assertEqual(body["sync_status"], "partial")
        self.assertEqual(body["successful_calendars"], 2)
        self.assertEqual(body["failed_calendars"], 1)
        self.assertEqual(body["failures"], [{
            "calendar_number": 1,
            "error_code": "google_calendar_event_overlong_interval",
        }])
        self.assertFalse(body["external_writes"])
        self.assertNotIn("private-1@example.invalid", output)
        self.assertNotIn("Private 1", output)
        with self.store.connect() as db:
            failed_code = db.execute(
                "SELECT last_error FROM calendar_google_attempts "
                "WHERE account_id='default' AND calendar_id=?",
                (calendar(1)["id"],),
            ).fetchone()[0]
        self.assertEqual(failed_code, "google_calendar_event_overlong_interval")

    def test_failing_calendar_does_not_mutate_its_existing_cursor(self):
        from okal_core.calendar_google import _init
        with self.store.connect() as db, db:
            _init(db)
            db.execute("INSERT INTO calendar_google_sync VALUES(?,?,?,?,?)",
                       ("default", calendar(1)["id"], "original-cursor", 123, 8))
        self.run_sync(
            [calendar(1), calendar(2)],
            [ValueError("invalid_calendar_event_interval"),
             {"received": 1, "written": 1, "external_writes": False}],
        )
        with self.store.connect() as db:
            checkpoint = db.execute(
                "SELECT sync_token,last_success,event_count FROM calendar_google_sync "
                "WHERE account_id='default' AND calendar_id=?",
                (calendar(1)["id"],),
            ).fetchone()
        self.assertEqual(tuple(checkpoint), ("original-cursor", 123, 8))

    def test_provider_exception_is_not_exposed_in_output(self):
        private_text = "secret OAuth bearer and private event body"
        rc, output, errors, _ = self.run_sync(
            [calendar(1), calendar(2)],
            [RuntimeError(private_text),
             {"received": 0, "written": 0, "external_writes": False}],
        )
        self.assertEqual(rc, 2)
        self.assertNotIn(private_text, output + errors)
        self.assertEqual(json.loads(output)["failures"][0]["error_code"],
                         "google_calendar_sync_failed")
        self.assertEqual(safe_sync_error(RuntimeError(private_text)),
                         "google_calendar_sync_failed")

    def test_all_success_returns_zero_and_valid_json(self):
        rc, output, errors, sync = self.run_sync(
            [calendar(1), calendar(2)],
            [{"received": 2, "written": 2, "external_writes": False},
             {"received": 0, "written": 0, "external_writes": False}],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(sync.call_count, 2)
        self.assertEqual(json.loads(output)["sync_status"], "complete")
        self.assertEqual(json.loads(output)["failed_calendars"], 0)
        self.assertFalse(errors)

    def test_unreadable_calendar_is_reported_as_partial_coverage(self):
        rc, output, _, sync = self.run_sync(
            [calendar(1, "none"), calendar(2)],
            [{"received": 1, "written": 1, "external_writes": False}],
        )
        self.assertEqual(rc, 2)
        self.assertEqual(sync.call_count, 1)
        self.assertEqual(json.loads(output)["unreadable_calendars"], 1)

    def test_single_calendar_failure_stays_nonzero_and_redacted(self):
        rc, output, errors, sync = self.run_sync(
            [calendar(1)],
            [CalendarGoogleError("google_calendar_event_nonpositive_interval")],
            args=["sync", "--account", "default", "--calendar", calendar(1)["id"]],
        )
        self.assertEqual(rc, 1)
        self.assertEqual(sync.call_count, 1)
        self.assertEqual(output, "")
        self.assertIn("google_calendar_event_nonpositive_interval", errors)
        self.assertNotIn(calendar(1)["id"], errors)


if __name__ == "__main__":
    unittest.main()
