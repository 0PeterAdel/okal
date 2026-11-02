"""Local Calendar V1 projection tests: no Google or external writes."""
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.calendar_core import CalendarConflict, CalendarCore, assess_ai_action
from okal_core.store import Store


def event(**changes):
    item = {
        "id": "meeting", "title": "OKAL Review",
        "start": "2026-11-02T11:00:00+02:00",
        "end": "2026-11-02T12:00:00+02:00",
        "updated": "2026-11-01T22:00:00+02:00",
        "timezone": "Africa/Cairo",
    }
    item.update(changes)
    return item


class CalendarFoundationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = Store(Path(tmp.name) / "private", clock=lambda: 1793541600)
        self.cal = CalendarCore(self.store)

    def test_no_connection_is_reported_honestly(self):
        result = self.cal.agenda()
        self.assertEqual(result["items"], [])
        self.assertEqual(result["connected_providers"], [])
        self.assertEqual(result["provider_status"], "not_connected_in_foundation")
        self.assertFalse(result["external_writes"])
        self.assertFalse(result["external_reads"])

    def test_idempotent_ingestion_survives_reopen(self):
        self.assertEqual(self.cal.ingest("google", "acct", "primary", [event()])["written"], 1)
        unchanged = CalendarCore(self.store).ingest("google", "acct", "primary", [event()])
        self.assertEqual(unchanged["written"], 0)
        self.assertEqual(unchanged["unchanged_or_stale"], 1)
        self.assertEqual(self.cal.agenda()["count"], 1)

    def test_provider_account_calendar_and_instance_ids_are_isolated(self):
        for provider, account, calendar, instance in (
            ("google", "a", "primary", None),
            ("google", "b", "primary", None),
            ("google", "a", "work", None),
            ("microsoft", "a", "primary", None),
            ("google", "a", "primary", "2026-11-02"),
        ):
            self.cal.ingest(provider, account, calendar, [event(instance_id=instance)])
        self.assertEqual(self.cal.agenda()["count"], 5)

    def test_changed_and_cancelled_provider_event(self):
        self.cal.ingest("google", "a", "primary", [event()])
        self.cal.ingest("google", "a", "primary", [
            event(title="Changed", updated="2026-11-02T01:00:00+02:00")
        ])
        self.assertEqual(self.cal.agenda()["items"][0]["title"], "Changed")
        self.cal.ingest("google", "a", "primary", [
            event(title="Changed", updated="2026-11-02T02:00:00+02:00",
                  cancelled=True)
        ])
        self.assertEqual(self.cal.agenda()["count"], 0)

    def test_stale_snapshot_cannot_revert_newer_event(self):
        self.cal.ingest("google", "a", "primary", [
            event(title="Fresh", updated="2026-11-02T03:00:00+02:00")
        ])
        result = self.cal.ingest("google", "a", "primary", [event(title="Old")])
        self.assertEqual(result["written"], 0)
        self.assertEqual(self.cal.agenda()["items"][0]["title"], "Fresh")

    def test_equal_revision_collision_rolls_back_entire_batch(self):
        self.cal.ingest("google", "a", "primary", [event()])
        with self.assertRaises(CalendarConflict):
            self.cal.ingest("google", "a", "primary", [
                event(id="new"), event(title="not identical")
            ])
        self.assertEqual(self.cal.agenda()["count"], 1)

    def test_rejects_ambiguous_dates_invalid_timezone_bad_fields(self):
        samples = [
            {"start": "2026-11-02T11:00:00"},
            {"end": "2026-11-02T09:00:00+02:00"},
            {"timezone": "Not/A/Timezone"},
            {"all_day": "yes"},
            {"title": ""},
            {"unknown_key": "oops"},
        ]
        for values in samples:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.cal.ingest("google", "a", "primary", [event(**values)])
        self.assertEqual(self.cal.agenda()["count"], 0)

    def test_duplicate_batch_rejected_before_any_write(self):
        with self.assertRaisesRegex(ValueError, "duplicate_calendar_batch_event"):
            self.cal.ingest("google", "a", "primary", [event(), event()])
        self.assertEqual(self.cal.agenda()["count"], 0)

    def test_instant_timed_event_is_visible_but_not_busy(self):
        self.cal.ingest("google", "a", "primary", [
            event(id="instant", start="2026-11-02T11:00:00+02:00",
                  end="2026-11-02T11:00:00+02:00")
        ])
        result = self.cal.agenda()
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["start_ts"],
                         result["items"][0]["end_ts"])
        self.assertFalse(result["items"][0]["busy"])
        self.assertEqual(self.cal.availability()["busy_intervals_utc"], [])
        with self.assertRaisesRegex(ValueError, "invalid_calendar_event_interval"):
            self.cal.ingest("google", "a", "primary", [
                event(id="zero-all-day", all_day=True,
                      end="2026-11-02T11:00:00+02:00",
                      start="2026-11-02T11:00:00+02:00")
            ])

    def test_busy_merges_overlaps_excluding_transparent_events(self):
        self.cal.ingest("google", "a", "primary", [
            event(id="a"),
            event(id="b", start="2026-11-02T11:30:00+02:00",
                  end="2026-11-02T12:30:00+02:00"),
            event(id="transparent", busy=False,
                  start="2026-11-02T13:00:00+02:00",
                  end="2026-11-02T14:00:00+02:00"),
        ])
        result = self.cal.availability()
        self.assertEqual(len(result["busy_intervals_utc"]), 1)
        start, end = result["busy_intervals_utc"][0]
        self.assertEqual(end-start, 5400)
        self.assertTrue(result["limited_to_loaded_projection"])

    def test_policy_enforces_owner_scope_and_ownership(self):
        for action in ("create", "update", "delete"):
            policy = assess_ai_action(action)
            self.assertFalse(policy["eligible_for_auto"])
            self.assertTrue(policy["requires_approval"])
            self.assertFalse(policy["executed"])
        self.assertFalse(assess_ai_action(
            "delete", owner_granted=True, scope="scoped_auto"
        )["eligible_for_auto"])
        self.assertTrue(assess_ai_action(
            "delete", owner_granted=True, scope="scoped_auto", ai_created=True
        )["eligible_for_auto"])
        self.assertFalse(assess_ai_action(
            "create", owner_granted=True, scope="scoped_auto", has_attendees=True
        )["eligible_for_auto"])
        self.assertFalse(assess_ai_action(
            "update", owner_granted=True, scope="scoped_auto", recurring=True
        )["eligible_for_auto"])
        self.assertTrue(assess_ai_action("summarize")["eligible_for_auto"])

    def test_unconfigured_api_reads_snapshot_without_side_effects(self):
        with TestClient(create_app(self.store),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1234)) as client:
            response = client.get("/api/v1/calendar/agenda")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["provider_status"], "not_connected_in_foundation")
            self.assertEqual(client.get("/api/v1/calendar/availability").status_code, 200)
            self.assertEqual(client.get(
                "/api/v1/calendar/agenda?provider=google"
            ).status_code, 400)
            self.assertEqual(client.post(
                "/api/v1/calendar/agenda", json={}
            ).status_code, 401)

    def test_protected_mode_requires_existing_read_token(self):
        with TestClient(create_app(self.store, require_read_key=True),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1234)) as client:
            self.assertEqual(client.get("/api/v1/calendar/agenda").status_code, 401)
            token = self.store.issue_device("test")["token"]
            self.assertEqual(client.get(
                "/api/v1/calendar/agenda",
                headers={"Authorization": "Bearer " + token}
            ).status_code, 200)


if __name__ == "__main__":
    unittest.main()
