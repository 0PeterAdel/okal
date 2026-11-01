"""Fake-transport coverage for Google Calendar read-only sync and OAuth boundaries."""
from pathlib import Path
import json
import tempfile
import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.calendar_google import (
    CalendarGoogleError, configured_accounts, list_calendars, normalize,
    status, sync_calendar, validate_account,
)
from okal_core.mail.private import write_private
from okal_core.store import Store


def fixture(**changes):
    row = {
        "id": "google-1", "summary": "مذاكرة OKAL",
        "start": {"dateTime": "2026-11-03T10:00:00+02:00"},
        "end": {"dateTime": "2026-11-03T11:00:00+02:00"},
        "updated": "2026-11-02T01:00:00Z",
        "status": "confirmed",
    }
    row.update(changes)
    return row


class FakeResource:
    def __init__(self, parent):
        self.parent = parent

    def list(self, **kwargs):
        self.parent.calls.append(kwargs)
        self.kwargs = kwargs
        return self

    def execute(self, num_retries=0):
        assert num_retries == 0
        if not self.parent.pages:
            raise AssertionError("Unexpected provider request")
        outcome = self.parent.pages.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeService:
    def __init__(self, *pages):
        self.pages = list(pages)
        self.calls = []

    def events(self):
        return FakeResource(self)

    def calendarList(self):
        return FakeResource(self)


class Gone(Exception):
    def __init__(self):
        super().__init__("expired")
        self.resp = SimpleNamespace(status=410)


class ProviderTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = Store(Path(tmp.name) / "state", clock=lambda: 1793610000)

    def sync(self, service, **kwargs):
        return sync_calendar(
            self.store, "default", "primary",
            service=service, calendar_timezone="Africa/Cairo", **kwargs
        )

    def test_no_credentials_no_false_connected_state(self):
        self.assertEqual(configured_accounts(self.store), [])
        result = status(self.store)
        self.assertEqual(result["authorization"], "not_configured")
        self.assertFalse(result["connected"])
        self.assertNotIn("token", json.dumps(result))
        with TestClient(
            create_app(self.store),
            base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1234)
        ) as client:
            self.assertEqual(client.get("/api/v1/calendar/status").json()["accounts"], [])

    def test_rejects_alias_traversal(self):
        for alias in ("../secret", ".env", "UPPER", "default/other", ""):
            with self.assertRaises(CalendarGoogleError):
                validate_account(alias)

    def test_calendar_listing_is_paginated_and_read_only(self):
        service = FakeService(
            {"items": [{"id": "c1@example.com", "summary": "Main",
                        "accessRole": "owner", "timeZone": "Africa/Cairo"}],
             "nextPageToken": "p1"},
            {"items": [{"id": "c2@example.com", "summary": "Work",
                        "accessRole": "reader", "timeZone": "Europe/Berlin"}]},
        )
        result = list_calendars(service)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]["timezone"], "Europe/Berlin")
        self.assertEqual(service.calls[1]["pageToken"], "p1")

    def test_first_sync_then_incremental_with_cancellation_tombstone(self):
        one = FakeService({"items": [fixture()], "nextSyncToken": "cursor-1"})
        self.assertEqual(self.sync(one)["result"], "full_sync")
        self.assertEqual(self.store.connect is not None, True)
        second = FakeService({
            "items": [{"id": "google-1", "status": "cancelled",
                       "updated": "2026-11-02T02:00:00Z"}],
            "nextSyncToken": "cursor-2",
        })
        self.assertEqual(self.sync(second)["result"], "history_delta")
        self.assertEqual(second.calls[0]["syncToken"], "cursor-1")
        with TestClient(create_app(self.store),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1234)) as client:
            data = client.get("/api/v1/calendar/agenda").json()
            self.assertEqual(data["items"], [])
            self.assertEqual(data["provider_status"], "cached_google_synced")

    def test_pagination_and_no_cursor_until_last_page(self):
        service = FakeService(
            {"items": [fixture()], "nextPageToken": "next"},
            {"items": [fixture(id="google-2")], "nextSyncToken": "cursor-ok"},
        )
        result = self.sync(service)
        self.assertEqual(result["received"], 2)
        self.assertEqual(service.calls[1]["pageToken"], "next")
        self.assertEqual(self.store.connect is not None, True)
        self.assertEqual(status(self.store)["last_sync"][0]["event_count"], 2)

    def test_partial_api_failure_does_not_save_cursor_or_events(self):
        service = FakeService(
            {"items": [fixture()], "nextPageToken": "page-two"},
            RuntimeError("offline"),
        )
        with self.assertRaises(CalendarGoogleError):
            self.sync(service)
        self.assertEqual(status(self.store)["last_sync"], [])
        with TestClient(create_app(self.store),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1234)) as client:
            self.assertEqual(client.get("/api/v1/calendar/agenda").json()["count"], 0)

    def test_expired_token_forces_full_and_prunes_old_events(self):
        self.sync(FakeService({
            "items": [fixture(), fixture(id="removed")],
            "nextSyncToken": "expired",
        }))
        response = self.sync(FakeService(
            Gone(),
            {"items": [fixture()], "nextSyncToken": "new-token"},
        ))
        self.assertEqual(response["result"], "full_sync")
        with TestClient(create_app(self.store),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1234)) as client:
            self.assertEqual(client.get("/api/v1/calendar/agenda").json()["count"], 1)

    def test_all_day_in_ianna_zone_and_exclusive_end(self):
        event = fixture(start={"date": "2026-11-03"},
                        end={"date": "2026-11-04"})
        result = normalize(event, "Africa/Cairo")
        self.assertTrue(result["all_day"])
        self.assertTrue(result["end"].startswith("2026-11-04T00:00:00"))
        self.assertEqual(result["timezone"], "Africa/Cairo")

    def test_recurring_instance_keeps_original_occurrence_identity(self):
        event = fixture(
            id="instance-123", recurringEventId="series-1",
            originalStartTime={"dateTime": "2026-11-03T10:00:00+02:00"},
        )
        result = normalize(event, "Africa/Cairo")
        self.assertEqual(result["instance_id"], "2026-11-03T10:00:00+02:00")

    def test_stored_token_never_in_status_api_response(self):
        from okal_core.calendar_google import credential_file
        write_private(credential_file(self.store, "private"), {
            "token": "SECRET_TOKEN_MUST_NOT_APPEAR",
            "refresh_token": "SECRET_REFRESH_MUST_NOT_APPEAR",
            "scopes": ["example"],
        })
        result = status(self.store, "private")
        self.assertTrue(result["authorization"] == "configured_not_verified")
        self.assertNotIn("SECRET_", json.dumps(result))
        with TestClient(create_app(self.store),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1234)) as client:
            self.assertNotIn("SECRET_", client.get("/api/v1/calendar/status").text)


if __name__ == "__main__":
    unittest.main()
