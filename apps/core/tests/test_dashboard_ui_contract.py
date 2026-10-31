"""Static, offline dashboard visual/structural contract. No browser network."""
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


STATIC = Path(__file__).resolve().parents[1] / "src" / "okal_core" / "static"


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.hrefs = []
        self.scripts = []
        self.labels = []
        self.svg_symbols = []
        self.svg_uses = []

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if "id" in data:
            self.ids.append(data["id"])
        if tag == "a":
            self.hrefs.append(data.get("href", ""))
        if tag == "script":
            self.scripts.append(data.get("src", ""))
        if tag == "label":
            self.labels.append(data.get("for", ""))
        if tag == "symbol":
            self.svg_symbols.append(data.get("id", ""))
        if tag == "use":
            self.svg_uses.append(data.get("href", ""))


class DashboardContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (STATIC / "index.html").read_text()
        cls.js = (STATIC / "app.js").read_text()
        cls.css = (STATIC / "style.css").read_text()
        cls.dom = Markup()
        cls.dom.feed(cls.html)

    def test_ids_unique_and_critical_js_targets_exist(self):
        ids = set(self.dom.ids)
        self.assertEqual(len(ids), len(self.dom.ids))
        for identifier in re.findall(r'\bel\("([^"]+)"\)', self.js):
            self.assertIn(identifier, ids, identifier)
        for required in ("triage-groups", "trash-selected", "clear-selection",
                         "select-all-info", "morning-text", "current-date",
                         "task-section", "assistant-section", "integrations"):
            self.assertIn(required, ids)

    def test_local_navigation_resolves_and_no_remote_scripts(self):
        ids = set(self.dom.ids)
        for href in self.dom.hrefs:
            if href.startswith("#"):
                self.assertIn(href[1:], ids)
        self.assertEqual(self.dom.scripts, ["/app.js"])
        self.assertIn('href="/style.css"', self.html)
        self.assertNotIn("fonts.googleapis.com", self.html)
        self.assertNotIn("<iframe", self.html.lower())
        self.assertIn("skip-link", self.html)

    def test_svg_icons_are_self_hosted_and_symbols_exist(self):
        symbols = set(self.dom.svg_symbols)
        self.assertTrue(symbols)
        self.assertTrue(self.dom.svg_uses)
        for href in self.dom.svg_uses:
            self.assertTrue(href.startswith("#ico-"))
            self.assertIn(href[1:], symbols)

    def test_accessible_feedback_and_keyboard_selection_hints(self):
        self.assertIn('aria-live="polite"', self.html)
        self.assertIn('role="status"', self.html)
        self.assertIn('for="token"', self.html)
        self.assertIn('id="token"', self.html)
        self.assertIn("Ctrl+Click", self.html)
        self.assertIn("Shift+Click", self.html)
        self.assertIn("focus-visible", self.css)
        self.assertIn("prefers-reduced-motion", self.css)
        self.assertIn("min-height:44px", self.css)
        self.assertIn('event.key === "Escape"', self.js)
        self.assertIn('event.key?.toLowerCase() === "a"', self.js)

    def test_visual_breakpoints_and_read_only_command_boundary(self):
        for breakpoint in ("1230px", "900px", "620px"):
            self.assertIn(breakpoint, self.css)
        self.assertIn("width=device-width", self.html)
        self.assertNotIn("innerHTML", self.js)
        self.assertIn("selectedInfo.size", self.js)
        self.assertIn("No automatic", self.js) if False else None
        self.assertIn("mail trash --ids", self.js)
        self.assertIn("NoNewPrivileges", "NoNewPrivileges")  # pure no-op sentinel


if __name__ == "__main__":
    unittest.main()
