"""Live public facts must not reuse device history or invent current numbers."""
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from okal_core.computer.live_intent import live_intent, public_search_query
from okal_core.computer.chat import propose_for_chat
from okal_core.computer.engine import Engine
from okal_core.intelligence import Intelligence
from okal_core.store import Store


class LiveIntentTests(unittest.TestCase):
    def test_egyptian_weather_requires_explicit_city(self):
        for text in (
            "بروس كدا وشوف درجة الحرارة كام اليوم",
            "بروس كدا وشوف درجة الحرارة كام النهارده",
            "الجو عامل إيه دلوقتي؟",
            "What's the temperature today?",
        ):
            with self.subTest(text=text):
                choice = live_intent(text)
                self.assertEqual(choice.kind, "location_required")
                self.assertIn("مدينة", choice.answer)

    def test_city_weather_not_guessed_from_cairo_timezone(self):
        cases = {
            "شوف درجة الحرارة في أسيوط كام النهاردة": ("أسيوط", "اليوم"),
            "الجو عامل ايه النهاردة في القاهرة": ("القاهرة", "اليوم"),
            "طقس الإسكندرية بكرة": ("الإسكندرية", "غدًا"),
            "weather in London today": ("London", "اليوم"),
            "temperature in New York tomorrow": ("New York", "غدًا"),
        }
        for text, (city, day) in cases.items():
            with self.subTest(text=text):
                choice = live_intent(text)
                self.assertEqual(choice.kind, "weather_search")
                self.assertIn(city, choice.query)
                self.assertIn(day, choice.query)

    def test_live_currency_defaults_transparently_not_from_previous_topic(self):
        for text in ("بروس كدا وشوف سعر الريال كام النهاردة",
                     "سعر الريال السعودي كام اليوم"):
            with self.subTest(text=text):
                result = live_intent(text)
                self.assertEqual(result.kind, "rate_search")
                self.assertIn("SAR EGP", result.query)
                self.assertIn("الجنيه المصري", result.query)
                self.assertIn("الجنيه المصري", result.answer)
        result = live_intent("سعر الريال مقابل الدولار اليوم")
        self.assertEqual(result.kind, "rate_search")
        self.assertIn("الدولار", result.query)
        self.assertNotIn("SAR EGP", result.query)

    def test_do_not_leak_unrelated_questions_to_public_web(self):
        for text in ("كام هارد متوصل في جهازي؟", "حرارة المعالج كام؟",
                     "درجة حرارة الجهاز كام؟", "مساحة المثلث كام",
                     "ما هي نظرية النسبية؟", "احفظ معلوماتي دي"):
            with self.subTest(text=text):
                self.assertIsNone(live_intent(text))
        self.assertEqual(public_search_query("بروس كدا وشوف سعر الريال كام النهاردة"),
                         "سعر الريال كام النهاردة")

    def test_city_only_followup_is_scoped_to_prior_clarification(self):
        self.assertIsNone(live_intent("أسيوط"))
        self.assertIsNone(live_intent("تمام", weather_followup=True))
        self.assertIsNone(live_intent("نفذ في الترمينال: ls", weather_followup=True))
        result = live_intent("أسيوط", weather_followup=True)
        self.assertEqual(result.kind, "weather_search")
        self.assertIn("أسيوط", result.query)


class ChatLiveRouteTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(Path(temp.name) / "state")
        self.conversation = Intelligence(self.store).create()["id"]
        self.engine = Engine(self.store)

    def grant(self, *tools):
        current = self.engine.policy()
        self.engine.configure({
            "mode": "read_only", "tools": list(tools),
            "roots": [], "browser_origins": [],
            "accounts": [], "commands": {}, "applications": [],
        }, current["revision"])

    def send(self, message, **kwargs):
        return propose_for_chat(
            self.store, self.conversation, uuid.uuid4().hex,
            message, **kwargs,
        )

    def test_weather_location_clarifies_without_permission_or_network(self):
        with patch("okal_core.computer.browser.network") as network:
            answer = self.send("بروس كدا وشوف درجة الحرارة كام النهاردة")
            self.assertEqual(answer["source"], "location_clarification")
            self.assertNotIn("action_run", answer)
            network.assert_not_called()

    def test_followup_reuses_only_trusted_weather_clarification(self):
        self.grant("browser.search")
        with patch("okal_core.computer.browser.network", return_value="PINNED"):
            answer = self.send("أسيوط", previous_source="location_clarification")
        run = self.engine.get(answer["action_run"])
        self.assertEqual(run["plan"]["steps"][0]["tool"], "browser.search")
        self.assertIn("أسيوط", run["plan"]["steps"][0]["arguments"]["query"])
        self.assertNotIn("hard drive", run["plan"]["steps"][0]["arguments"]["query"])
        self.assertEqual(run["status"], "ready")

    def test_riyal_and_weather_plan_use_real_browser_tool(self):
        self.grant("browser.search")
        with patch("okal_core.computer.browser.network", return_value="PINNED"):
            for text, expected in (
                ("بروس كدا وشوف سعر الريال كام النهاردة", "SAR EGP"),
                ("درجة الحرارة في أسيوط كام النهارده", "أسيوط"),
            ):
                with self.subTest(text=text):
                    response = self.send(text)
                    self.assertEqual(response["source"], "proposed_action_plan")
                    run = self.engine.get(response["action_run"])
                    self.assertEqual(run["plan"]["steps"][0]["tool"], "browser.search")
                    self.assertIn(expected, run["plan"]["steps"][0]["arguments"]["query"])
                    self.assertNotIn("هارد", run["plan"]["steps"][0]["arguments"]["query"])

    def test_missing_web_grant_is_precise(self):
        result = self.send("شوف درجة الحرارة النهارده في المنيا")
        self.assertEqual(result["source"], "action_permission_policy")
        self.assertIn("browser.search", result["answer"])
        self.assertNotIn("action_run", result)

    def test_existing_device_routing_unchanged(self):
        self.grant("system.status")
        result = self.send("عندي كام هارد متوصل؟")
        self.assertEqual(result["source"], "proposed_action_plan")
        self.assertEqual(self.engine.get(result["action_run"])["plan"]["steps"][0]["tool"],
                         "system.status")


if __name__ == "__main__":
    unittest.main()
