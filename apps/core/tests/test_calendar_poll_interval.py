"""Calendar reads must honor a persisted 3-hour due gate after restarts.

All tests are local fake-provider fixtures; no Google API or OAuth access.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from okal_core.calendar_google import (
    CalendarWorker, _claim_periodic_calendar_check, status,
    sync_authorized_account,
)
from okal_core.store import Store


class CalendarPollingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.now = [1793610000]
        self.store = Store(Path(tmp.name) / "private",
                           clock=lambda: self.now[0])

    def test_due_gate_survives_service_restarts_and_clock_jumps(self):
        self.assertTrue(_claim_periodic_calendar_check(
            self.store, "default", 10800
        ))
        # Different worker processes would consult this same SQLite row.
        self.assertFalse(_claim_periodic_calendar_check(
            self.store, "default", 10800
        ))
        self.now[0] += 10799
        self.assertFalse(_claim_periodic_calendar_check(
            self.store, "default", 10800
        ))
        self.now[0] += 1
        self.assertTrue(_claim_periodic_calendar_check(
            self.store, "default", 10800
        ))
        self.now[0] -= 3600
        self.assertFalse(_claim_periodic_calendar_check(
            self.store, "default", 10800
        ))

    def test_due_is_separate_for_each_authorized_account(self):
        self.assertTrue(_claim_periodic_calendar_check(
            self.store, "default", 10800))
        self.assertTrue(_claim_periodic_calendar_check(
            self.store, "secondary", 10800))
        self.assertFalse(_claim_periodic_calendar_check(
            self.store, "default", 10800))
        self.now[0] += 10800
        self.assertTrue(_claim_periodic_calendar_check(
            self.store, "default", 10800))
        self.assertTrue(_claim_periodic_calendar_check(
            self.store, "secondary", 10800))

    def test_worker_restarts_do_not_make_duplicate_google_calls(self):
        calls=[]
        fake_calendar={"id":"primary","access":"owner",
                       "timezone":"Africa/Cairo"}
        with (patch("okal_core.calendar_google.configured_accounts",
                    return_value=["default"]),
              patch("okal_core.calendar_google._service",
                    side_effect=lambda store,account:calls.append(
                        ("google",account)) or object()),
              patch("okal_core.calendar_google.list_calendars",
                    return_value=[fake_calendar]),
              patch("okal_core.calendar_google._sync_with_window_fallback",
                    side_effect=lambda *args:calls.append(("sync","primary")))):
            CalendarWorker(self.store).tick()
            self.assertEqual(calls,[("google","default"),("sync","primary")])
            CalendarWorker(self.store).tick()  # simulate logout/login
            self.assertEqual(len(calls),2)
            self.now[0] += 10800
            CalendarWorker(self.store).tick()
            self.assertEqual(len(calls),4)

    def test_failed_api_call_does_not_trigger_restart_retry_storm(self):
        with (patch("okal_core.calendar_google.configured_accounts",
                    return_value=["default"]),
              patch("okal_core.calendar_google._service",
                    side_effect=RuntimeError("secret provider error")) as mock):
            CalendarWorker(self.store).tick()
            CalendarWorker(self.store).tick()
            self.assertEqual(mock.call_count,1)
            self.now[0] += 10800
            CalendarWorker(self.store).tick()
            self.assertEqual(mock.call_count,2)
        with self.store.connect() as db:
            result=db.execute(
                "SELECT last_error FROM calendar_google_attempts"
            ).fetchone()
        self.assertEqual(result[0],"google_calendar_provider_request_failed")

    def test_oauth_connect_is_immediate_and_suppresses_followup_poll(self):
        service=object()
        with (patch("okal_core.calendar_google._service",return_value=service) as svc,
              patch("okal_core.calendar_google.list_calendars",return_value=[]),
              patch("okal_core.calendar_google.configured_accounts",
                    return_value=["default"])):
            sync_authorized_account(self.store)
            self.assertEqual(svc.call_count,1)
            CalendarWorker(self.store).tick()
            self.assertEqual(svc.call_count,1)
            self.now[0]+=10800
            CalendarWorker(self.store).tick()
            self.assertEqual(svc.call_count,2)

    def test_status_read_is_local_only_and_does_not_create_poll_table(self):
        with patch("okal_core.calendar_google._service",
                   side_effect=AssertionError("status must not fetch Google")):
            before=status(self.store)
            self.assertIsNone(before["background_poll"]["last_attempt"])
            self.assertEqual(before["background_poll"]["interval_seconds"],10800)
            self.assertTrue(before["background_poll"]["restart_safe"])
            with self.store.connect() as db:
                exists=db.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='calendar_google_poll_attempts'"
                ).fetchone()
            self.assertIsNone(exists)
            # No configured credentials means not exposing attempted timestamps.
            _claim_periodic_calendar_check(self.store,"default",10800)
            after=status(self.store)
            self.assertIsNone(after["background_poll"]["last_attempt"])

    def test_period_validation(self):
        for bad in (0,-1,True,1.5):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                _claim_periodic_calendar_check(self.store,"default",bad)


if __name__ == "__main__":
    unittest.main()
