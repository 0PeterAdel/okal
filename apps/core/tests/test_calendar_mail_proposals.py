"""Gmail source quote required for every review-only event draft."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.calendar_mail_proposals import (
    CalendarQuote, analyze_message, propose_from_gmail,
)
from okal_core.mail.contracts import MailError
from okal_core.store import Store


def message(body, **changes):
    row = dict(
        id="aabb", labels=["INBOX"], subject="Project meeting",
        body=body, body_total_chars=len(body), truncated=False,
    )
    row.update(changes)
    return SimpleNamespace(**row)


class FakeLocalModel:
    def __init__(self, value):
        self.value = value

    def generate(self, schema, system, data):
        assert schema is CalendarQuote
        assert "untrusted DATA" in system
        assert "body_untrusted" in data
        return self.value


class GmailCalendarProposalTests(unittest.TestCase):
    def test_source_supported_iso_times_are_read_only(self):
        quote = ("Meet 2026-11-03T14:00:00+02:00 to "
                 "2026-11-03T15:00:00+02:00 online.")
        out = analyze_message(message("Hello, " + quote + " Thanks"), FakeLocalModel(
            CalendarQuote(has_calendar_intent=True, title="Team meeting",
                          evidence_quote=quote)))
        self.assertEqual(out["status"], "source_iso_times_need_owner_review")
        self.assertEqual(out["start_iso"], "2026-11-03T12:00:00+00:00")
        self.assertEqual(out["end_iso"], "2026-11-03T13:00:00+00:00")
        self.assertTrue(out["owner_review_required"])
        self.assertFalse(out["external_writes"])

    def test_human_friendly_date_remains_unverified(self):
        body = "Meet next Tuesday at 2pm Cairo time, please."
        out = analyze_message(message(body), FakeLocalModel(
            CalendarQuote(has_calendar_intent=True, title="Meeting",
                          evidence_quote="next Tuesday at 2pm Cairo time")))
        self.assertIsNone(out["start_iso"])
        self.assertIsNone(out["end_iso"])
        self.assertEqual(out["status"], "owner_must_set_time")

    def test_refuses_hallucinated_evidence_and_truncated_mail(self):
        model = FakeLocalModel(CalendarQuote(
            has_calendar_intent=True, title="Fake meeting",
            evidence_quote="Meeting tomorrow at 12:00."))
        with self.assertRaisesRegex(MailError, "calendar_mail_evidence_not_in_source"):
            analyze_message(message("No meeting scheduled."), model)
        with self.assertRaisesRegex(MailError, "calendar_mail_source_truncated"):
            analyze_message(message("Long body", truncated=True), model)

    def test_no_calendar_intent_produces_no_event(self):
        out = analyze_message(message("Hello"), FakeLocalModel(
            CalendarQuote(has_calendar_intent=False, title="", evidence_quote="")))
        self.assertEqual(out["status"], "no_calendar_intent_detected")
        self.assertIsNone(out["start_iso"])
        self.assertFalse(out["external_writes"])

    def test_invalid_or_ambiguous_source_times_never_become_verified(self):
        quote = "2026-11-03T18:00+02:00 then 2026-11-03T16:00+02:00"
        out = analyze_message(message(quote), FakeLocalModel(
            CalendarQuote(has_calendar_intent=True, title="Schedule",
                          evidence_quote=quote)))
        self.assertIsNone(out["start_iso"])
        self.assertIsNone(out["end_iso"])

    def test_real_gmail_source_mismatch_blocks_model(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = Store(Path(temp.name) / "private")
        with patch("okal_core.calendar_mail_proposals.config",
                   return_value=SimpleNamespace(account="owner@example.com")), \
             patch("okal_core.calendar_mail_proposals.allowed_source",
                   return_value={"id": "aabb"}), \
             patch("okal_core.calendar_mail_proposals.Gmail.open") as opening, \
             patch("okal_core.calendar_mail_proposals.LocalModel") as modeling:
            api = opening.return_value
            api.get.return_value = message("Call", id="someone_else")
            with self.assertRaisesRegex(MailError, "native_source_not_eligible"):
                propose_from_gmail(store, "aabb")
            modeling.assert_not_called()
            api.close.assert_called_once()

    def test_same_origin_gesture_required_for_mail_model_endpoint(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = Store(Path(temp.name) / "private")
        with TestClient(create_app(store),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1234)) as client:
            with patch("okal_core.calendar_mail_proposals.propose_from_gmail") as propose:
                propose.return_value = {
                    "status": "owner_must_set_time",
                    "title": "Meeting", "evidence_quote": "Please meet tomorrow",
                    "start_iso": None, "end_iso": None,
                    "owner_review_required": True,
                    "external_writes": False, "calendar_event_created": False,
                }
                url = "/api/v1/calendar/mail-proposal"
                self.assertEqual(client.get(url).status_code, 401)
                self.assertEqual(client.post(
                    url, json={"message_id": "aabb"}).status_code, 401)
                self.assertEqual(client.post(
                    url, json={"message_id": "aabb"}, headers={
                        "Origin": "https://attacker.example",
                    }).status_code, 403)
                ok = client.post(url, json={"message_id": "aabb"}, headers={
                    "Origin": "http://127.0.0.1:8766",
                    "Sec-Fetch-Site": "same-origin",
                })
                self.assertEqual(ok.status_code, 200)
                self.assertEqual(ok.json()["calendar_event_created"], False)
                propose.assert_called_once_with(store, "aabb")

    def test_invalid_id_cannot_trigger_gmail_or_ollama(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = Store(Path(temp.name) / "private")
        with patch("okal_core.calendar_mail_proposals.Gmail.open") as opening:
            with self.assertRaisesRegex(MailError, "calendar_mail_invalid_id"):
                propose_from_gmail(store, "../../.env")
            opening.assert_not_called()


if __name__ == "__main__":
    unittest.main()
