"""Opt-in public browser search/read, no hidden broad-origin escalation."""
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
import uuid
from unittest.mock import patch

from okal_core.computer.browser import browse
from okal_core.computer.chat import WEB_SEARCH, WEB_OPEN, LIVE_RATE, propose_for_chat
from okal_core.computer.contracts import Denied
from okal_core.computer.engine import Engine
from okal_core.computer.registry import Browser, SearchWeb, public_origin, search_url
from okal_core.intelligence import Intelligence
from okal_core.store import Store


PAGE = {
    "url": "https://www.google.com/search?q=synthetic",
    "title": "Synthetic public search",
    "text": "Verified synthetic response. Not a model answer.",
    "links": [{"text": "Public result", "url": "https://example.org/"}],
    "limited": False,
}


class BrowserChatTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(Path(temp.name) / "state")
        self.conversation = Intelligence(self.store).create()["id"]
        self.engine = Engine(self.store)

    def configure(self, tools):
        record = self.engine.policy()
        self.engine.configure({
            "mode": "read_only",
            "tools": tools,
            "roots": [],
            "browser_origins": [],
            "accounts": [],
            "commands": {},
            "applications": [],
        }, record["revision"])

    def test_explicit_web_queries_and_url_open_are_distinct(self):
        for query in ("ابحث في النت عن أخبار تقنية", "دور على جوجل عن النماذج", "Search the web for robotics", "تصفح الإنترنت عن الذكاء الاصطناعي"):
            self.assertIsNotNone(WEB_SEARCH.search(query))
        self.assertIsNone(WEB_SEARCH.search("What is an electron?"))
        self.assertIsNone(WEB_SEARCH.search("كام هارد في جهازي؟"))
        self.assertEqual(WEB_OPEN.search("افتح https://example.org/").group(1), "https://example.org/")
        self.assertIsNone(WEB_OPEN.search("افتح الإيميل"))

    @patch("okal_core.computer.browser.network", return_value="PINNED")
    def test_colloquial_live_riyal_rate_routes_to_real_web_tool(self, network):
        query = "بروس كدا وشوف سعر الريال كام النهاردة"
        self.assertIsNotNone(LIVE_RATE.search(query))
        self.assertIsNone(LIVE_RATE.search("اشرح معنى سعر الصرف"))
        denied = propose_for_chat(self.store, self.conversation, uuid.uuid4().hex, query)
        self.assertEqual(denied["source"], "action_permission_policy")
        self.assertIn("browser.search", denied["answer"])
        self.configure(["browser.search"])
        answer = propose_for_chat(self.store, self.conversation, uuid.uuid4().hex, query)
        self.assertEqual(answer["source"], "proposed_action_plan")
        plan = self.engine.get(answer["action_run"])["plan"]
        self.assertEqual(plan["steps"][0]["tool"], "browser.search")
        self.assertEqual(plan["steps"][0]["arguments"], {
            "query": "سعر الريال السعودي مقابل الجنيه المصري اليوم SAR EGP",
        })
        self.assertNotIn("بروس", plan["steps"][0]["arguments"]["query"])

    def test_public_https_origin_is_restricted(self):
        self.assertEqual(public_origin("https://example.org/path?q=a"), "https://example.org")
        for url in (
            "http://example.org/", "https://127.0.0.1/",
            "https://localhost/", "https://mybox.local/path",
            "https://example.org:8443/", "https://user:secret@example.org/",
        ):
            with self.subTest(url=url), self.assertRaises((Denied, ValueError)):
                public_origin(url)
        self.assertIn("q=a%26b", search_url("a&b"))
        with self.assertRaises(ValueError):
            SearchWeb(query="x")
        with self.assertRaises(ValueError):
            SearchWeb(query="x"*181)

    def test_missing_tool_is_explicit_not_fabricated(self):
        for query, tool in (("ابحث في النت عن الفيزياء", "browser.search"),
                            ("افتح https://example.org/", "browser.public_read")):
            with self.subTest(query=query):
                answer = propose_for_chat(self.store, self.conversation, uuid.uuid4().hex, query)
                self.assertEqual(answer["source"], "action_permission_policy")
                self.assertIn(tool, answer["answer"])
                self.assertNotIn("action_run", answer)

    @patch("okal_core.computer.browser.network", return_value="PINNED")
    def test_deterministic_search_uses_real_receipts(self, network):
        self.configure(["browser.search", "browser.public_read"])
        with patch("okal_core.computer.browser.browse", return_value=PAGE) as browser:
            answer = propose_for_chat(
                self.store, self.conversation, uuid.uuid4().hex,
                "ابحث في النت عن أحدث أدوات الروبوتات",
            )
            self.assertEqual(answer["source"], "proposed_action_plan")
            run = self.engine.get(answer["action_run"])
            self.assertEqual(run["plan"]["steps"][0]["tool"], "browser.search")
            self.assertEqual(run["status"], "ready")
            self.assertEqual(self.engine.execute(run["id"])["status"], "succeeded")
            result = self.engine.get(run["id"])["steps"][0]["result"]
            self.assertEqual(result["evidence"]["title"], PAGE["title"])
            self.assertTrue(result["verified"])
            self.assertTrue(browser.called)
        with patch("okal_core.computer.browser.browse", return_value=dict(PAGE, url="https://example.org/")):
            answer = propose_for_chat(
                self.store, self.conversation, uuid.uuid4().hex,
                "افتح https://example.org/",
            )
            self.assertEqual(self.engine.get(answer["action_run"])["plan"]["steps"][0]["tool"], "browser.public_read")
            self.assertEqual(self.engine.execute(answer["action_run"])["status"], "succeeded")

    @patch("okal_core.computer.browser.network", return_value="PINNED")
    def test_browser_failure_is_recorded_not_claimed_as_success(self, network):
        self.configure(["browser.search"])
        with patch("okal_core.computer.browser.browse", side_effect=ValueError("browser_navigation_failed")):
            answer = propose_for_chat(self.store, self.conversation, uuid.uuid4().hex, "ابحث في النت عن حاجه")
            finished = self.engine.execute(answer["action_run"])
            self.assertNotEqual(finished["status"], "succeeded")

    def test_private_dns_target_cannot_ride_public_read_grant(self):
        from okal_core.computer.registry import public_read_preview
        ctx = SimpleNamespace(policy=SimpleNamespace(browser_origins=[]))
        with patch("okal_core.computer.browser.socket.getaddrinfo",
                   return_value=[(None, None, None, None, ("10.1.2.3", 443))]):
            with self.assertRaises(Denied):
                public_read_preview(ctx, Browser(url="https://not-public.example.org/"))

    def test_browser_origin_override_never_allows_interaction(self):
        ctx = SimpleNamespace(policy=SimpleNamespace(browser_origins=[]), check=lambda: None)
        with patch("okal_core.computer.browser.network", return_value="PINNED"), patch(
            "okal_core.computer.browser.run", return_value=json.dumps(PAGE).encode()
        ) as native:
            result = browse(ctx, Browser(url="https://www.google.com/search?q=synthetic"),
                            read_origins=["https://www.google.com"])
            self.assertEqual(result["title"], PAGE["title"])
            payload = json.loads(native.call_args.kwargs["input_data"])
            self.assertEqual(payload["origins"], ["https://www.google.com"])
            self.assertFalse(payload["interactive"])
            with self.assertRaises(Denied):
                browse(ctx, Browser(url="https://www.google.com/"),
                       interactive=True, read_origins=["https://www.google.com"])


if __name__ == "__main__":
    unittest.main()
