"""Automatic Google sync: use full history first, bounded recovery on failure."""
from pathlib import Path
import tempfile
import unittest

from okal_core.calendar_core import CalendarCore
from okal_core.calendar_google import _sync_with_window_fallback
from okal_core.store import Store


class Resource:
    def __init__(self, owner):
        self.owner = owner

    def list(self, **args):
        self.owner.calls.append(args)
        return self

    def execute(self, num_retries=0):
        assert num_retries == 0
        item = self.owner.pages.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class Fake:
    def __init__(self, *pages):
        self.calls = []
        self.pages = list(pages)

    def events(self):
        return Resource(self)

    def calendarList(self):
        return Resource(self)


def row(event_id, end="2026-11-03T10:00:00+02:00"):
    return {
        "id": event_id, "summary": event_id,
        "start": {"dateTime": "2026-11-03T09:00:00+02:00"},
        "end": {"dateTime": end},
        "updated": "2026-11-02T01:00:00Z", "status": "confirmed",
    }


class AutoSyncTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.store = Store(Path(d.name) / "state", clock=lambda: 1793610000)
        self.item = {
            "id": "primary", "timezone": "Africa/Cairo",
            "access": "owner", "primary": True,
        }

    def test_full_sync_accepts_instant_event_and_checkpoint(self):
        service = Fake({
            "items": [row("zero", end="2026-11-03T09:00:00+02:00"),
                      row("meeting")],
            "nextSyncToken": "first-cursor",
        })
        result = _sync_with_window_fallback(self.store, "default",
                                            self.item, service)
        self.assertEqual(result["result"], "full_sync")
        self.assertEqual(len(CalendarCore(self.store).agenda(7)["items"]), 2)
        with self.store.connect() as db:
            cursor = db.execute(
                "SELECT sync_token FROM calendar_google_sync"
            ).fetchone()[0]
        self.assertEqual(cursor, "first-cursor")
        self.assertFalse(any("timeMin" in x for x in service.calls))
        intervals = CalendarCore(self.store).availability(days=7)["busy_intervals_utc"]
        self.assertEqual(len(intervals), 1)

    def test_reversed_historical_event_triggers_auto_window_recovery(self):
        old_invalid = row("historical-bad",
                          end="2026-11-03T08:00:00+02:00")
        service = Fake(
            {"items": [old_invalid], "nextSyncToken": "must-not-advance"},
            {"items": [row("current-1"), row("current-2")]},
        )
        result = _sync_with_window_fallback(self.store, "default",
                                            self.item, service)
        self.assertEqual(result["mode"], "bounded_window_recovery")
        self.assertEqual(result["written"], 2)
        self.assertEqual(len(CalendarCore(self.store).agenda(7)["items"]), 2)
        self.assertIn("timeMin", service.calls[1])
        self.assertNotIn("syncToken", service.calls[1])
        with self.store.connect() as db:
            self.assertIsNone(db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='calendar_google_sync'"
            ).fetchone())
            error = db.execute(
                "SELECT last_error FROM calendar_google_attempts"
            ).fetchone()[0]
        self.assertEqual(error, "google_calendar_event_nonpositive_interval")

        next_service = Fake(
            {"items": [old_invalid], "nextSyncToken": "still-not-advanced"},
            {"items": [row("current-2", end="2026-11-03T10:30:00+02:00")]},
        )
        result = _sync_with_window_fallback(
            self.store, "default", self.item, next_service
        )
        self.assertEqual(result["mode"], "bounded_window_recovery")
        self.assertEqual(result["removed_from_window"], 1)
        self.assertEqual(len(CalendarCore(self.store).agenda(7)["items"]), 1)
        with self.store.connect() as db:
            self.assertIsNone(db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='calendar_google_sync'"
            ).fetchone())

    def test_network_error_never_falls_back_or_guesses(self):
        service = Fake(RuntimeError("PRIVATE HTTP response"))
        result = _sync_with_window_fallback(
            self.store, "default", self.item, service,
        )
        self.assertIsNone(result)
        self.assertEqual(len(service.calls), 1)
        self.assertEqual(CalendarCore(self.store).agenda(7)["items"], [])


if __name__ == "__main__":
    unittest.main()
