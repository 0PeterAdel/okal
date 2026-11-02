"""Read-only unified calendar planning contract and API regression tests."""
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.calendar_core import CalendarCore
from okal_core.calendar_google import _init as init_google_sync
from okal_core.calendar_planning import unified_plan
from okal_core.store import Store
from okal_core.task_planner import TaskPlanner


CAIRO = ZoneInfo("Africa/Cairo")


def event(event_id="meeting", start="2026-11-02T10:00:00+02:00",
          end="2026-11-02T11:00:00+02:00", **changes):
    result = {
        "id": event_id, "title": event_id,
        "start": start, "end": end,
        "updated": "2026-11-01T20:00:00+02:00",
        "timezone": "Africa/Cairo",
    }
    result.update(changes)
    return result


class UnifiedPlannerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        # 08:00 Cairo, November 2, 2026.
        self.now = int(datetime(2026, 11, 2, 8, tzinfo=CAIRO).timestamp())
        self.store = Store(Path(temp.name) / "private", clock=lambda: self.now)
        self.calendar = CalendarCore(self.store)

    def sync_checkpoint(self, when=None):
        with self.store.connect() as db, db:
            init_google_sync(db)
            db.execute(
                "INSERT OR REPLACE INTO calendar_google_sync VALUES(?,?,?,?,?)",
                ("default", "primary", "fake-cursor", self.now if when is None else when, 1)
            )

    def test_unconfigured_has_no_false_availability(self):
        result = unified_plan(self.store)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["candidate_slots"], [])
        self.assertIsNone(result["coverage"]["last_sync"])
        self.assertFalse(result["coverage"]["availability_verified"])
        self.assertEqual(result["candidate_slots_status"],
                         "disabled_unverified_calendar_sources")
        self.assertFalse(result["coverage"]["source_evidence"]["desired_sources_verified"])
        self.assertFalse(result["external_reads"])
        self.assertFalse(result["external_writes"])
        self.assertFalse(result["ai_actions_executed"])

    def test_events_tasks_and_provider_identity_stay_distinct(self):
        self.calendar.ingest("google", "default", "primary", [event()])
        self.calendar.ingest("google", "work", "office", [event()])
        created = TaskPlanner(self.store).create(
            "Finish report", due="2026-11-02T10:45:00+02:00")
        TaskPlanner(self.store).create("Unscheduled")
        TaskPlanner(self.store).create(
            "Overdue", due="2026-11-01T10:00:00+02:00")
        self.sync_checkpoint()
        result = unified_plan(self.store, 1)
        self.assertEqual(result["counts"]["calendar_events"], 2)
        self.assertEqual(result["counts"]["scheduled_local_tasks"], 1)
        self.assertEqual(result["counts"]["unscheduled_local_tasks_in_sample"], 1)
        self.assertEqual(result["counts"]["overdue_local_tasks_in_sample"], 1)
        self.assertEqual(len(result["items"]), 3)
        calendars = [x for x in result["items"] if x["kind"] == "calendar_event"]
        self.assertEqual({x["id"][1] for x in calendars}, {"default", "work"})
        task = [x for x in result["items"] if x["kind"] == "local_task"][0]
        self.assertEqual(task["id"], created["task_id"])
        self.assertIsNone(task["end_ts"])  # Never infer meeting duration.

    def test_potential_overlap_and_deadline_in_busy_event(self):
        self.calendar.ingest("google", "default", "primary", [
            event("meeting-a"),
            event("meeting-b", start="2026-11-02T10:30:00+02:00",
                  end="2026-11-02T11:30:00+02:00"),
            event("transparent", start="2026-11-02T10:30:00+02:00",
                  end="2026-11-02T11:30:00+02:00", busy=False),
        ])
        TaskPlanner(self.store).create(
            "Due while busy", due="2026-11-02T10:45:00+02:00")
        self.sync_checkpoint()
        result = unified_plan(self.store, 1)
        types = [x["kind"] for x in result["conflicts"]]
        self.assertEqual(types.count("potential_event_overlap"), 1)
        self.assertEqual(types.count("deadline_during_busy_event"), 2)
        self.assertFalse(result["coverage"]["availability_verified"])
        self.assertEqual(result["candidate_slots"], [])
        self.assertFalse(result["coverage"]["coverage_verified"])
        self.assertEqual(
            result["coverage"]["source_evidence"]["synced_calendar_count"], 1)

    def test_cancellation_and_busy_flag_do_not_create_conflicts(self):
        self.calendar.ingest("google", "default", "primary", [
            event("visible"),
            event("transparent", busy=False),
            event("deleted", cancelled=True),
        ])
        result = unified_plan(self.store, 1)
        self.assertEqual(result["counts"]["calendar_events"], 2)
        self.assertEqual(result["conflicts"], [])

    def test_one_day_excludes_tomorrow_week_includes_it(self):
        self.calendar.ingest("google", "default", "primary", [
            event("tomorrow", start="2026-11-03T11:00:00+02:00",
                  end="2026-11-03T12:00:00+02:00")
        ])
        self.assertEqual(unified_plan(self.store, 1)["items"], [])
        self.assertEqual(len(unified_plan(self.store, 7)["items"]), 1)
        for days in (0, 2, 14, True, "7"):
            with self.subTest(days=days), self.assertRaises(ValueError):
                unified_plan(self.store, days)

    def test_stale_cache_suppresses_slots_and_warns(self):
        self.sync_checkpoint(self.now - 3 * 3600)
        data = unified_plan(self.store, 1)
        self.assertEqual(data["candidate_slots"], [])
        self.assertFalse(data["coverage"]["recent_successful_sync"])
        self.assertIn("google_calendar_cache_stale", data["coverage"]["warnings"])

    def test_candidate_slot_future_and_stays_inside_local_workday(self):
        self.sync_checkpoint()
        self.now = int(datetime(2026, 11, 2, 17, 45, tzinfo=CAIRO).timestamp())
        data = unified_plan(self.store, 1)
        self.assertEqual(data["candidate_slots"], [])
        self.now = int(datetime(2026, 11, 2, 8, tzinfo=CAIRO).timestamp())
        data = unified_plan(self.store, 1)
        # Even with a recent successful checkpoint and no busy cache rows,
        # unknown provider/account coverage cannot prove these hours are free.
        self.assertEqual(data["candidate_slots"], [])
        self.assertEqual(
            data["candidate_slots_status"],
            "disabled_unverified_calendar_sources")

    def test_recent_checkpoint_zero_events_is_reported_as_incomplete(self):
        self.sync_checkpoint()
        result = unified_plan(self.store, 7)
        evidence = result["coverage"]["source_evidence"]
        self.assertEqual(evidence["synced_calendar_count"], 1)
        self.assertEqual(evidence["recent_calendar_count"], 1)
        self.assertEqual(evidence["cached_google_events_in_window"], 0)
        self.assertEqual(result["candidate_slots"], [])
        self.assertIn("zero_cached_google_events_in_window",
                      result["coverage"]["warnings"])
        self.assertIn("desired_calendar_sources_not_verified",
                      result["coverage"]["warnings"])

    def test_multiple_checkpoints_and_failures_are_aggregate_only(self):
        self.calendar.ingest("google", "a-secret-account", "private-calendar",
                             [event(event_id="TOP-SECRET-EVENT")])
        self.sync_checkpoint()
        with self.store.connect() as db, db:
            db.execute(
                "INSERT INTO calendar_google_sync VALUES(?,?,?,?,?)",
                ("a-secret-account", "private-calendar",
                 "private-sync-token", self.now - 10000, 20)
            )
            db.execute("""CREATE TABLE calendar_google_attempts (
                account_id TEXT NOT NULL, calendar_id TEXT NOT NULL,
                last_attempt INTEGER NOT NULL, last_error TEXT NOT NULL,
                PRIMARY KEY(account_id,calendar_id))""")
            db.execute(
                "INSERT INTO calendar_google_attempts VALUES(?,?,?,?)",
                ("a-secret-account", "private-calendar", self.now,
                 "google_calendar_provider_request_failed")
            )
        result = unified_plan(self.store, 1)
        evidence = result["coverage"]["source_evidence"]
        self.assertEqual(evidence["synced_calendar_count"], 2)
        self.assertEqual(evidence["recent_calendar_count"], 1)
        self.assertEqual(evidence["stale_calendar_count"], 1)
        self.assertEqual(evidence["recorded_sync_failures"], 1)
        self.assertEqual(evidence["cached_google_events_in_window"], 1)
        self.assertEqual(result["candidate_slots"], [])
        self.assertIn("some_google_calendars_stale", result["coverage"]["warnings"])
        self.assertIn("google_calendar_sync_failures_recorded",
                      result["coverage"]["warnings"])
        import json
        serialized = json.dumps(result["coverage"])
        self.assertNotIn("a-secret-account", serialized)
        self.assertNotIn("private-calendar", serialized)
        self.assertNotIn("private-sync-token", serialized)
        self.assertNotIn("TOP-SECRET-EVENT", serialized)

    def test_daylight_saving_window_uses_cairo_local_midnights(self):
        self.now = int(datetime(2027, 4, 29, 8, tzinfo=CAIRO).timestamp())
        self.calendar.ingest("google", "default", "primary", [
            event("after-dst", start="2027-04-30T10:00:00+03:00",
                  end="2027-04-30T11:00:00+03:00")
        ])
        self.assertEqual(unified_plan(self.store, 1)["items"], [])
        self.assertEqual(len(unified_plan(self.store, 7)["items"]), 1)

    def test_read_api_is_bounded_and_works_with_session_protection(self):
        with TestClient(
            create_app(self.store, require_read_key=True),
            base_url="http://127.0.0.1:8766",
            client=("127.0.0.1", 1234),
        ) as client:
            self.assertEqual(client.get("/api/v1/calendar/plan").status_code, 401)
            auth = {"Authorization": "Bearer " + self.store.issue_device("test")["token"]}
            response = client.get("/api/v1/calendar/plan?days=7", headers=auth)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["external_writes"])
            for query in ("days=2", "days=100", "days=nope"):
                self.assertEqual(client.get(
                    "/api/v1/calendar/plan?" + query, headers=auth).status_code, 422)
            self.assertEqual(client.post(
                "/api/v1/calendar/plan", json={}, headers=auth).status_code, 405)

    def test_self_hosted_mit_calendar_assets_require_no_external_cdn(self):
        with TestClient(
            create_app(self.store),
            base_url="http://127.0.0.1:8766",
            client=("127.0.0.1", 1234),
        ) as client:
            for endpoint, mimetype, marker in (
                ("/vanilla-calendar.min.js", "text/javascript", b"vanilla-calendar"),
                ("/vanilla-calendar.min.css", "text/css", b"vanilla-calendar"),
            ):
                with self.subTest(endpoint=endpoint):
                    response = client.get(endpoint)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(mimetype, response.headers["content-type"])
                    self.assertIn(marker, response.content)
                    self.assertIn("no-store", response.headers["cache-control"])
                    self.assertIn("script-src", response.headers["content-security-policy"])
            html = client.get("/").text
            self.assertIn('src="/vanilla-calendar.min.js"', html)
            self.assertNotIn("cdn.jsdelivr.net", html)

    def test_limit_warning_is_not_silent(self):
        self.calendar.ingest("google", "default", "primary", [
            event("event-" + str(index), start="2026-11-02T10:00:00+02:00",
                  end="2026-11-02T11:00:00+02:00") for index in range(200)
        ])
        self.sync_checkpoint()
        result = unified_plan(self.store, 1)
        self.assertTrue(result["coverage"]["calendar_limit_reached"])
        self.assertIn("calendar_event_limit_reached", result["coverage"]["warnings"])
        self.assertEqual(result["candidate_slots"], [])
        self.assertTrue(result["coverage"]["conflicts_truncated"])


if __name__ == "__main__":
    unittest.main()
