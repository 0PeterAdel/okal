"""Browser pairing is one-time, read-only, revocable and origin-restricted."""
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.store import Store


class BrowserSessionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.now = 1_800_000_000
        self.store = Store(Path(tmp.name) / "state", clock=lambda: self.now)
        self.device = self.store.issue_device("trusted-local-browser", days=2)
        self.client = TestClient(
            create_app(self.store), base_url="http://127.0.0.1:8766",
            client=("127.0.0.1", 1234),
        )
        self.addCleanup(self.client.close)
        self.origin = {"Origin": "http://127.0.0.1:8766"}

    def pair(self, key=None):
        return self.client.post(
            "/api/v1/session", json={"token": key or self.device["token"]},
            headers=self.origin,
        )

    def test_pair_once_cookie_reloads_read_only_and_logout_revokes(self):
        self.assertEqual(self.client.get("/api/v1/capabilities").status_code, 401)
        response = self.pair()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["permissions"], ["inbox:read"])
        self.assertIn("httponly", response.headers["set-cookie"].lower())
        self.assertIn("samesite=strict", response.headers["set-cookie"].lower())
        self.assertIn("path=/api", response.headers["set-cookie"].lower())
        self.assertEqual(self.client.get("/api/v1/summaries").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/capabilities").status_code, 200)
        revoked = self.client.delete("/api/v1/session", headers=self.origin)
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/capabilities").status_code, 401)

    def test_revoking_original_device_revokes_browser_session(self):
        self.assertEqual(self.pair().status_code, 200)
        self.assertTrue(self.store.revoke_device(self.device["id"]))
        self.assertEqual(self.client.get("/api/v1/capabilities").status_code, 401)

    def test_device_expiry_limits_cookie_even_if_client_retains_it(self):
        self.assertEqual(self.pair().status_code, 200)
        self.now += 3 * 86400
        self.assertEqual(self.client.get("/api/v1/capabilities").status_code, 401)

    def test_pairing_rejects_forged_key_and_bad_origin(self):
        self.assertEqual(self.pair("invalid").status_code, 401)
        self.assertEqual(self.client.post(
            "/api/v1/session", json={"token": self.device["token"]},
            headers={"Origin": "http://malicious.invalid"},
        ).status_code, 403)
        self.assertEqual(self.client.post(
            "/api/v1/session", json={"token": self.device["token"], "send": True},
            headers=self.origin,
        ).status_code, 400)
        self.assertEqual(self.client.post(
            "/api/v1/session", json={"token": self.device["token"]},
        ).status_code, 403)

    def test_cookie_cannot_authorize_provider_writes(self):
        self.assertEqual(self.pair().status_code, 200)
        self.assertEqual(self.client.post(
            "/api/v1/mail/send", json={"draft_id": "dummy"},
            headers=self.origin,
        ).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/capabilities").json()["external_writes"],
                         False)
