"""Boundary tests for the local Studio display and voice bridge."""

import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen


MODULE_PATH = Path(__file__).resolve().parents[1] / "server.py"
spec = importlib.util.spec_from_file_location("okal_studio_server", MODULE_PATH)
studio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(studio)


class StudioBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = studio.StudioServer(("127.0.0.1", 0))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"OKAL_STUDIO_RUNTIME_DIR": self.temp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def get(self, route, headers=None):
        return urlopen(Request(self.url + route, headers=headers or {}), timeout=3)

    def post(self, command, headers=None):
        defaults = {"Content-Type": "application/json", "Origin": self.url,
                    "X-Okal-CSRF": self.server.csrf}
        defaults.update(headers or {})
        body = json.dumps({"command": command}).encode("utf-8")
        return urlopen(Request(self.url + "/api/voice", data=body, headers=defaults), timeout=3)

    def test_page_and_idle_state(self):
        response = self.get("/")
        self.assertIn(self.server.csrf.encode(), response.read())
        self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])
        state = json.load(self.get("/api/state"))
        self.assertFalse(state["voice"]["available"])
        self.assertIsNone(state["canvas"])

    def test_host_and_origin_and_csrf_rejected(self):
        with self.assertRaises(HTTPError) as error:
            self.get("/api/state", {"Host": "attacker.test"})
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(HTTPError) as error:
            self.post("ask", {"Origin": "http://attacker.test"})
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(HTTPError) as error:
            self.post("ask", {"X-Okal-CSRF": "wrong"})
        self.assertEqual(error.exception.code, 403)

    def test_only_narrow_voice_commands_reach_owned_socket(self):
        folder = studio.runtime_root() / "voice"
        folder.mkdir(parents=True)
        path = folder / "control.sock"
        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(path))
        sock.listen(1)
        received = []

        def reply():
            client, _ = sock.accept()
            with client:
                received.append(json.loads(client.recv(4096).decode()))
                client.sendall(b'{"ok": true, "phase": "routing"}\n')

        thread = threading.Thread(target=reply, daemon=True)
        thread.start()
        self.assertEqual(json.load(self.post("ask"))["phase"], "routing")
        thread.join(timeout=2)
        sock.close()
        self.assertEqual(received, [{"command": "ask", "text": ""}])
        with self.assertRaises(HTTPError) as error:
            self.post("shell")
        self.assertEqual(error.exception.code, 400)

    def test_canvas_sanitizes_and_ignores_bad_shapes(self):
        base = {"schema_version": studio.SCHEMA, "kind": "gallery", "title": "<script>bad</script>",
                "images": [{"src": "https://example.com/a.png"},
                           {"src": "/media/../secret.png"},
                           {"src": "/assets/noor.svg", "caption": "local"}]}
        clean = studio.safe_canvas(base)
        self.assertEqual(clean["images"], [{"src": "/assets/noor.svg", "alt": "", "caption": "local"}])
        self.assertEqual(clean["title"], "<script>bad</script>")  # client uses textContent
        self.assertIsNone(studio.safe_canvas({**base, "kind": []}))
        self.assertEqual(studio.safe_canvas({**base, "kind": "chart",
                                            "series": [{"label": "bad", "value": float("nan")},
                                                       {"label": "good", "value": 52}]})["series"],
                         [{"label": "good", "value": 52}])

    def test_valid_canvas_is_live_and_unknown_paths_are_not_served(self):
        folder = studio.runtime_root() / "studio"
        folder.mkdir(parents=True)
        (folder / "canvas.json").write_text(json.dumps({
            "schema_version": studio.SCHEMA, "kind": "text", "title": "نتيجة",
            "body": "جملة من مصدر محلي", "source": "اختبار"}, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(json.load(self.get("/api/state"))["canvas"]["body"], "جملة من مصدر محلي")
        with self.assertRaises(HTTPError) as error:
            self.get("/../../README.md")
        self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
