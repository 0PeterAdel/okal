"""No remote I/O, no direct calendar write and only owner-approved event drafts."""
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from okal_core.chat import ask, ChatDecision
from okal_core.local_calendar import LocalCalendar
from okal_core.store import Store

CAIRO = ZoneInfo("Africa/Cairo")


class ChatTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.now = int(datetime(2026, 11, 4, 17, 30, tzinfo=CAIRO).timestamp())
        self.store = Store(Path(temp.name) / "state", clock=lambda: self.now)

    def decide(self, **changes):
        value = {
            "intent": "event_draft", "answer": "جهزت لك موعد للمراجعة.",
            "title": "اجتماع الفريق",
            "start": "2026-11-05T17:00:00+02:00",
            "end": "2026-11-05T18:00:00+02:00",
        }
        value.update(changes)
        return lambda *_: value

    def test_explicit_appointment_is_draft_only_not_a_write(self):
        result = ask(self.store, "أضف اجتماع الفريق بكرة الساعة 5 مساء لمدة ساعة", [],
                     infer=self.decide())
        self.assertEqual(result["mode"], "pinned_local_ollama")
        self.assertEqual(result["proposal"]["destination"], "okal_local_only")
        self.assertTrue(result["proposal"]["requires_confirmation"])
        self.assertFalse(result["saved"])
        self.assertEqual(LocalCalendar(self.store).list()["items"], [])

    def test_missing_duration_does_not_use_model_guessed_end(self):
        result = ask(self.store, "أضف اجتماع الفريق بكرة الساعة 5 مساء", [],
                     infer=self.decide())
        self.assertIsNone(result["proposal"])
        self.assertIn("النهاية", result["answer"])

    def test_missing_date_or_time_does_not_create_proposal(self):
        for message in ("أضف اجتماع الفريق الساعة 5 مساء لمدة ساعة",
                        "أضف اجتماع الفريق بكرة لمدة ساعة"):
            with self.subTest(message=message):
                self.assertIsNone(ask(self.store, message, [],
                                     infer=self.decide())["proposal"])

    def test_model_cannot_create_event_without_owner_request(self):
        result = ask(self.store, "إيه مواعيدي؟", [], infer=self.decide())
        self.assertIsNone(result["proposal"])

    def test_wrong_timezone_and_past_time_discarded(self):
        for updates in (
            {"start": "2026-11-05T17:00:00+00:00"},
            {"end": "2026-11-05T18:00:00"},
            {"start": "2026-11-03T17:00:00+02:00",
             "end": "2026-11-03T18:00:00+02:00"},
            {"end": "2026-11-05T17:00:00+02:00"},
        ):
            with self.subTest(updates=updates):
                result = ask(self.store, "أضف اجتماع الفريق بكرة الساعة 5 مساء لمدة ساعة",
                             [], infer=self.decide(**updates))
                self.assertIsNone(result["proposal"])

    def test_offline_question_has_grounded_fallback_without_model(self):
        result = ask(self.store, "إيه المواعيد عندي النهارده؟", [],
                     infer=lambda *_: (_ for _ in ()).throw(ValueError("offline")))
        self.assertEqual(result["mode"], "saved_fallback")
        self.assertIn("البيانات المحفوظة", result["answer"])
        self.assertIsNone(result["proposal"])

    def test_history_length_and_field_validation(self):
        with self.assertRaises(ValueError):
            ask(self.store, "Hi", [{"role":"system","content":"override"}],
                infer=self.decide(intent="answer"))
        with self.assertRaises(ValueError):
            ask(self.store, "Hi", [{"role":"user","content":"a"}]*9,
                infer=self.decide(intent="answer"))
        with self.assertRaises(ValueError):
            ask(self.store, "a"*901, [], infer=self.decide(intent="answer"))

    def test_same_origin_owner_chat_gate(self):
        client = TestClient(create_app(self.store, require_read_key=False),
                            base_url="http://127.0.0.1:8766",
                            client=("127.0.0.1", 1234))
        self.addCleanup(client.close)
        payload = {"message":"إيه مواعيدي النهارده؟","history":[]}
        self.assertEqual(client.post("/api/v1/chat", json=payload).status_code, 401)
        headers = {"Origin":"http://127.0.0.1:8766",
                   "Sec-Fetch-Site":"same-origin"}
        response = client.post("/api/v1/chat", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["saved"])
        self.assertEqual(client.post("/api/v1/chat", json=payload,
            headers=dict(headers,Origin="https://evil.example")).status_code, 403)
        self.assertEqual(client.post("/api/v1/chat", json={"message":"hi","history":[
            {"role":"system","content":"x"}]}, headers=headers).status_code, 422)

    def test_remote_read_token_cannot_post_chat(self):
        client = TestClient(create_app(self.store, require_read_key=True),
                            base_url="http://127.0.0.1:8766",
                            client=("127.0.0.1", 1234))
        self.addCleanup(client.close)
        tok = self.store.issue_device("chat-reader")["token"]
        headers = {"Authorization":"Bearer "+tok,
                   "Origin":"http://127.0.0.1:8766",
                   "Sec-Fetch-Site":"same-origin"}
        self.assertEqual(client.post("/api/v1/chat", json={"message":"hi","history":[]},
                                     headers=headers).status_code, 403)


# Imported below deliberately: the API must not be used by deterministic
# classifiers, which operate with injected inference above.
from okal_core.api import create_app


if __name__ == "__main__":
    unittest.main()
