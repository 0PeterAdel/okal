"""Review-only task block selection: never Google writes or invented duration."""
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.calendar_core import CalendarCore
from okal_core.calendar_google import _init as init_calendar_sync
from okal_core.calendar_task_proposals import propose_task_blocks
from okal_core.store import Store
from okal_core.task_planner import TaskPlanner


CAIRO = ZoneInfo("Africa/Cairo")


def ts(day, hour, minute=0):
    return int(datetime(2026, 11, day, hour, minute, tzinfo=CAIRO).timestamp())


class ReviewPlanTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.now = ts(2, 8)
        self.store = Store(Path(tmp.name) / "private", clock=lambda: self.now)
        self.tasks = TaskPlanner(self.store)
        self.calendar = CalendarCore(self.store)

    def synced(self, when=None):
        with self.store.connect() as db, db:
            init_calendar_sync(db)
            db.execute("INSERT OR REPLACE INTO calendar_google_sync VALUES(?,?,?,?,?)",
                       ("default", "primary", "cursor", self.now if when is None else when, 2))

    def busy(self, event_id, start="2026-11-02T09:00:00+02:00",
             end="2026-11-02T10:00:00+02:00"):
        self.calendar.ingest("google", "default", "primary", [{
            "id": event_id, "title": event_id,
            "start": start, "end": end,
            "updated": "2026-11-02T06:00:00+02:00",
            "timezone": "Africa/Cairo",
        }])

    def test_no_sync_blocks_all_suggested_work_blocks(self):
        self.tasks.create("Due soon", due="2026-11-02T14:00:00+02:00")
        data = propose_task_blocks(self.store, days=1)
        self.assertEqual(data["proposals"], [])
        self.assertEqual(data["status"], "blocked_by_missing_or_limited_calendar_evidence")
        self.assertFalse(data["external_writes"])

    def test_deadline_sorted_without_double_booking_or_busy_event_overlap(self):
        self.synced()
        self.busy("meeting")
        self.tasks.create("Later", due="2026-11-02T14:00:00+02:00")
        self.tasks.create("Sooner", due="2026-11-02T11:00:00+02:00")
        data = propose_task_blocks(self.store, 1)
        self.assertEqual(data["status"], "tentative_local_plan")
        self.assertEqual([p["title"] for p in data["proposals"]], ["Sooner", "Later"])
        first, second = data["proposals"]
        self.assertEqual(first["start_ts"], ts(2, 10))
        self.assertEqual(second["start_ts"], ts(2, 10, 30))
        self.assertLessEqual(first["end_ts"], first["due_at"])
        self.assertLessEqual(second["end_ts"], second["due_at"])
        self.assertTrue(all(p["duration_is_assumed"] for p in data["proposals"]))
        self.assertFalse(data["availability_verified"])

    def test_impossible_deadline_is_not_scheduled_after_deadline(self):
        self.synced()
        self.tasks.create("Urgent", due="2026-11-02T09:10:00+02:00")
        result = propose_task_blocks(self.store, 1)
        self.assertEqual(result["proposals"], [])
        self.assertEqual(result["unplaced_tasks"], 1)

    def test_stale_source_prohibits_pretend_automatic_booking(self):
        self.tasks.create("Review", due="2026-11-02T15:00:00+02:00")
        self.synced(self.now - 8000)
        result = propose_task_blocks(self.store, 1)
        self.assertEqual(result["proposals"], [])
        self.assertIn("google_calendar_cache_stale",
                      result["coverage"]["warnings"])

    def test_boundaries_one_and_seven_only(self):
        self.synced()
        for bad in (0, 3, True, "7"):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                propose_task_blocks(self.store, bad)
        self.tasks.create("Tomorrow", due="2026-11-03T12:00:00+02:00")
        self.assertEqual(propose_task_blocks(self.store, 1)["proposals"], [])
        self.assertEqual(len(propose_task_blocks(self.store, 7)["proposals"]), 1)

    def test_read_endpoint_and_no_spurious_calendar_mutation(self):
        with TestClient(create_app(self.store, require_read_key=False),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1234)) as client:
            value = client.get("/api/v1/calendar/review-plan?days=7")
            self.assertEqual(value.status_code, 200)
            self.assertFalse(value.json()["external_writes"])
            self.assertEqual(client.get(
                "/api/v1/calendar/review-plan?days=2").status_code, 422)
            self.assertEqual(client.post(
                "/api/v1/calendar/review-plan", json={}).status_code, 401)

    def test_protected_plan_requires_token(self):
        with TestClient(create_app(self.store, require_read_key=True),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1234)) as client:
            self.assertEqual(client.get("/api/v1/calendar/review-plan").status_code, 401)
            token = self.store.issue_device("test")["token"]
            response = client.get(
                "/api/v1/calendar/review-plan",
                headers={"Authorization": "Bearer " + token},
            )
            self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
