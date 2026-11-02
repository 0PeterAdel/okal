"""Recovery: valid current Google events, no historical cursor changes or leaks."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from okal_core.calendar_cli import main
from okal_core.calendar_core import CalendarCore
from okal_core.calendar_google import (
    CalendarGoogleError, _init as init_sync, sync_calendar,
)
from okal_core.calendar_planning import unified_plan
from okal_core.calendar_window_recovery import recover_window
from okal_core.store import Store


def fixture(name, begin="2026-11-03T05:00:00+02:00",
            end="2026-11-03T06:00:00+02:00"):
    return {
        "id": name, "summary": "PRIVATE EVENT TITLE",
        "start": {"dateTime": begin}, "end": {"dateTime": end},
        "updated": "2026-11-01T14:00:00Z", "status": "confirmed",
    }


class Resource:
    def __init__(self, service, name):
        self.service, self.name = service, name

    def list(self, **kwargs):
        self.service.calls.append((self.name, kwargs))
        return self

    def execute(self, num_retries=0):
        assert num_retries == 0
        value = self.service.outcomes.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FakeService:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def calendarList(self):
        return Resource(self, "calendarList")

    def events(self):
        return Resource(self, "events")


def calendar():
    return {
        "id": "private-primary@example.invalid", "summary": "PERSONAL",
        "primary": True, "accessRole": "owner", "timeZone": "Africa/Cairo",
    }


class RecoverWindowTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.store = Store(Path(d.name) / "state", clock=lambda: 1793610000)

    def service(self, *pages):
        return FakeService({"items": [calendar()]}, *pages)

    def cached(self):
        return CalendarCore(self.store).agenda(days=7)["items"]

    def test_recover_primary_four_current_events_and_keep_checkpoint_absent(self):
        items = [fixture(f"ID-{i}") for i in range(4)]
        service = self.service(
            {"items": items[:2], "nextPageToken": "more"},
            {"items": items[2:]},
        )
        result = recover_window(self.store, service=service, days=7)
        self.assertEqual(result["received"], 4)
        self.assertEqual(result["written"], 4)
        self.assertEqual(result["calendar_role"], "primary")
        self.assertEqual(result["source_coverage"], "selected_calendar_window_only")
        self.assertFalse(result["full_sync_complete"])
        self.assertFalse(result["sync_cursor_advanced"])
        self.assertFalse(result["external_writes"])
        self.assertEqual(len(self.cached()), 4)
        plan = unified_plan(self.store, 7)
        self.assertEqual(plan["counts"]["calendar_events"], 4)
        self.assertIsNone(plan["coverage"]["last_sync"])
        self.assertEqual(plan["candidate_slots"], [])
        with self.store.connect() as db:
            has_sync = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='calendar_google_sync'"
            ).fetchone()
        self.assertIsNone(has_sync)
        for kind, args in service.calls:
            if kind == "events":
                self.assertIn("timeMin", args)
                self.assertIn("timeMax", args)
                self.assertEqual(args["showDeleted"], False)
                self.assertEqual(args["singleEvents"], True)
                self.assertNotIn("syncToken", args)
        # Full JSON result has no provider identifiers or titles.
        report = json.dumps(result)
        self.assertNotIn("private-primary", report)
        self.assertNotIn("PRIVATE EVENT TITLE", report)

    def test_idempotent_recovery_and_existing_checkpoint_still_unchanged(self):
        with self.store.connect() as db, db:
            init_sync(db)
            db.execute(
                "INSERT INTO calendar_google_sync VALUES(?,?,?,?,?)",
                ("default", calendar()["id"], "SECRET-OLD-CURSOR", 123, 9),
            )
        first = recover_window(self.store, service=self.service(
            {"items": [fixture("ID-A")]}
        ))
        second = recover_window(self.store, service=self.service(
            {"items": [fixture("ID-A")]}
        ))
        self.assertEqual(first["written"], 1)
        self.assertEqual(second["written"], 0)
        with self.store.connect() as db:
            checkpoint = db.execute(
                "SELECT sync_token,last_success,event_count FROM calendar_google_sync"
            ).fetchone()
        self.assertEqual(tuple(checkpoint), ("SECRET-OLD-CURSOR", 123, 9))

    def test_late_invalid_event_rejects_entire_window_before_cache_mutation(self):
        bad = fixture("invalid-zero", end="2026-11-03T05:00:00+02:00")
        svc = self.service(
            {"items": [fixture("valid-first")], "nextPageToken": "page2"},
            {"items": [bad]},
        )
        with self.assertRaisesRegex(
            CalendarGoogleError, "google_calendar_event_nonpositive_interval"
        ):
            recover_window(self.store, service=svc)
        self.assertEqual(self.cached(), [])
        with self.store.connect() as db:
            self.assertIsNone(db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='calendar_google_sync'"
            ).fetchone())

    def test_page_fetch_failure_keeps_cache_unmodified(self):
        service = self.service(
            {"items": [fixture("valid-first")], "nextPageToken": "next"},
            RuntimeError("PRIVATE HTTP response"),
        )
        with self.assertRaisesRegex(
            CalendarGoogleError, "google_calendar_provider_request_failed"
        ):
            recover_window(self.store, service=service)
        self.assertEqual(self.cached(), [])

    def test_recovery_does_not_delete_unrelated_or_cancelled_events(self):
        core = CalendarCore(self.store)
        core.ingest("google", "default", calendar()["id"], [{
            "id": "older", "title": "Private older record",
            "start": "2026-11-01T09:00:00+02:00",
            "end": "2026-11-01T10:00:00+02:00",
            "timezone": "Africa/Cairo",
            "updated": "2026-11-01T00:00:00Z",
        }])
        recover_window(self.store, service=self.service(
            {"items": [fixture("new-current")]}
        ))
        with self.store.connect() as db:
            count = db.execute(
                "SELECT count(*) FROM calendar_source_events"
            ).fetchone()[0]
        self.assertEqual(count, 2)

    def test_cli_owner_command_returns_redacted_counts_only(self):
        output = StringIO()
        svc = self.service({"items": [fixture("SECRET-ID")]})
        with patch("okal_core.calendar_window_recovery._service", return_value=svc), \
                redirect_stdout(output):
            code = main(self.store, [
                "recover-window", "--account", "default",
                "--calendar", "primary", "--days", "7",
            ])
        self.assertEqual(code, 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data["written"], 1)
        self.assertNotIn("SECRET-ID", output.getvalue())
        self.assertNotIn("private-primary", output.getvalue())

    def test_cli_fails_closed_when_one_event_is_invalid_no_private_error(self):
        out, err = StringIO(), StringIO()
        svc = self.service({"items": [
            fixture("PRIVATE-ID", end="2026-11-03T05:00:00+02:00")
        ]})
        with patch("okal_core.calendar_window_recovery._service", return_value=svc), \
                redirect_stdout(out), redirect_stderr(err):
            rc = main(self.store, ["recover-window"])
        self.assertEqual(rc, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("google_calendar_event_nonpositive_interval", err.getvalue())
        self.assertNotIn("PRIVATE-ID", err.getvalue())
        self.assertEqual(self.cached(), [])

    def test_rejects_unbounded_window_and_unreadable_calendar(self):
        for days in (0, 15, True, "7", None):
            with self.subTest(days=days), self.assertRaises(ValueError):
                recover_window(self.store, days=days, service=object())
        unreader = calendar()
        unreader["accessRole"] = "freeBusyReader"
        service = FakeService({"items": [unreader]})
        with self.assertRaisesRegex(
            CalendarGoogleError, "calendar_not_accessible_select_id_from_calendars"
        ):
            recover_window(self.store, service=service)


if __name__ == "__main__":
    unittest.main()
