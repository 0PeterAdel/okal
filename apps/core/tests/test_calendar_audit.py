"""Owner-invoked Calendar audit never changes cursors or leaks event identity."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from okal_core.calendar_audit import audit_google_calendar
from okal_core.calendar_cli import main
from okal_core.calendar_google import _init as init_google_sync
from okal_core.store import Store


class Resource:
    def __init__(self, parent, kind):
        self.parent = parent
        self.kind = kind

    def list(self, **kwargs):
        self.parent.calls.append((self.kind, kwargs))
        self.args = kwargs
        return self

    def execute(self, num_retries=0):
        self.parent.last_retries = num_retries
        outcome = self.parent.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeService:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.last_retries = None

    def events(self):
        return Resource(self, "events")

    def calendarList(self):
        return Resource(self, "calendars")


def cal(name, primary=False):
    return {"id": name, "summary": name, "timeZone": "Africa/Cairo",
            "accessRole": "owner", "primary": primary}


def event(name, end="2026-11-03T11:00:00+02:00", start="2026-11-03T10:00:00+02:00"):
    return {"id": name, "summary": "SECRET-TITLE", "start": {"dateTime": start},
            "end": {"dateTime": end}, "updated": "2026-11-02T01:00:00Z"}


class AuditTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        # ~Nov 2, 2026, in Cairo.
        self.store = Store(Path(d.name) / "state", clock=lambda: 1793610000)

    def test_distinguishes_primary_and_diagnoses_intervals_without_secrets(self):
        service = FakeService(
            {"items": [cal("secret-primary@example.invalid", True),
                       cal("secret-secondary@example.invalid")]},
            {"items": [
                event("A-SECRET-ID"),
                event("ZERO-SECRET-ID", end="2026-11-03T10:00:00+02:00"),
                event("REVERSED-SECRET-ID", end="2026-11-03T09:59:00+02:00"),
                event("OVERLONG-SECRET-ID", end="2028-11-03T09:59:00+02:00"),
            ]},
            {"items": []},
        )
        result = audit_google_calendar(self.store, service=service)
        self.assertTrue(result["complete"])
        self.assertEqual(result["calendars_listed"], 2)
        self.assertTrue(result["calendars"][0]["primary"])
        self.assertFalse(result["calendars"][1]["primary"])
        first = result["calendars"][0]
        self.assertEqual(first["live_events_in_window"], 4)
        self.assertEqual(first["interval_shapes"]["valid"], 1)
        self.assertEqual(first["interval_shapes"]["zero_duration_timed"], 1)
        self.assertEqual(first["interval_shapes"]["reversed_interval"], 1)
        self.assertEqual(first["interval_shapes"]["overlong_interval"], 1)
        self.assertEqual(result["calendars"][1]["live_events_in_window"], 0)
        self.assertFalse(result["cache_mutated"])
        self.assertFalse(result["sync_cursor_mutated"])
        self.assertFalse(result["external_writes"])
        serialized = json.dumps(result)
        for private in ("secret-primary", "secret-secondary",
                        "SECRET-TITLE", "SECRET-ID"):
            self.assertNotIn(private, serialized)
        for kind, args in service.calls:
            if kind == "events":
                self.assertIn("timeMin", args)
                self.assertIn("timeMax", args)
                self.assertNotIn("syncToken", args)

    def test_reads_cache_count_without_advancing_cursor(self):
        with self.store.connect() as db, db:
            init_google_sync(db)
            db.execute(
                "INSERT INTO calendar_google_sync VALUES(?,?,?,?,?)",
                ("default", "primary-secret", "TOP-SECRET-CURSOR", 123, 3),
            )
        svc = FakeService(
            {"items": [cal("primary-secret", True)]},
            {"items": []},
        )
        data = audit_google_calendar(self.store, service=svc)
        self.assertEqual(data["calendars"][0]["cached_events_in_window"], 0)
        self.assertTrue(data["calendars"][0]["has_sync_checkpoint"])
        with self.store.connect() as db:
            row = db.execute(
                "SELECT sync_token,last_success FROM calendar_google_sync"
            ).fetchone()
        self.assertEqual(tuple(row), ("TOP-SECRET-CURSOR", 123))
        self.assertNotIn("TOP-SECRET-CURSOR", json.dumps(data))

    def test_provider_error_is_opaque_and_remaining_calendar_continues(self):
        svc = FakeService(
            {"items": [cal("private", True), cal("other")]},
            RuntimeError("sensitive HTTP Authorization Bearer token"),
            {"items": []},
        )
        result = audit_google_calendar(self.store, service=svc)
        self.assertFalse(result["complete"])
        self.assertEqual(result["calendars"][0]["audit_status"],
                         "provider_read_failed")
        self.assertEqual(result["calendars"][1]["audit_status"], "complete")
        self.assertNotIn("sensitive", json.dumps(result))
        self.assertNotIn("Bearer", json.dumps(result))

    def test_rejects_unbounded_days_before_external_calls(self):
        for days in (0, 15, True, 7.0, "7"):
            with self.subTest(days=days), self.assertRaises(ValueError):
                audit_google_calendar(self.store, days=days,
                                      service=FakeService())

    def test_page_budget_is_honest_without_partial_event_counts(self):
        pages = [
            {"items": [event("x")], "nextPageToken": f"PAGE-{n}"}
            for n in range(1, 9)
        ]
        svc = FakeService({"items": [cal("private", True)]}, *pages)
        result = audit_google_calendar(self.store, service=svc)
        self.assertFalse(result["complete"])
        self.assertEqual(result["calendars"][0]["audit_status"], "page_limit")
        self.assertIsNone(result["calendars"][0]["live_events_in_window"])

    def test_cli_audit_prints_json_only_and_no_provider_ids(self):
        from io import StringIO
        from contextlib import redirect_stdout
        svc = FakeService(
            {"items": [cal("secret@example.invalid", True)]},
            {"items": [event("A")]}
        )
        output = StringIO()
        with patch("okal_core.calendar_audit._service", return_value=svc), \
                redirect_stdout(output):
            rc = main(self.store, ["audit", "--days", "7"])
        self.assertEqual(rc, 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data["calendars"][0]["live_events_in_window"], 1)
        self.assertNotIn("secret@example.invalid", output.getvalue())


if __name__ == "__main__":
    unittest.main()
