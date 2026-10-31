"""Single-user auto-unlock is read-only and refuses other origins/hosts/clients."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.store import Store


class LocalDashboardAutoUnlockTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(Path(temp.name) / "state")
        self.url = "http://127.0.0.1:8766"

    def client(self, *, protected=False, address="127.0.0.1"):
        return TestClient(
            create_app(self.store, require_read_key=protected),
            base_url=self.url,
            client=(address, 23571),
        )

    def test_default_is_keyless_loopback_read_only_and_no_session_token_needed(self):
        with patch.dict(os.environ, {}, clear=True):
            with TestClient(create_app(self.store), base_url=self.url,
                            client=("127.0.0.1", 23571)) as client:
                for path in (
                    "/api/v1/capabilities", "/api/v1/summaries",
                    "/api/v1/mail/triage", "/api/v1/mail/assistant",
                ):
                    response = client.get(
                        path, headers={"Sec-Fetch-Site": "same-origin"}
                    )
                    self.assertEqual(response.status_code, 200, path)
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertEqual(
                        response.headers["Cross-Origin-Resource-Policy"], "same-origin"
                    )
                caps = client.get("/api/v1/capabilities").json()
                self.assertTrue(caps["local_auto_unlock"])
                self.assertFalse(caps["read_key_required"])
                self.assertFalse(caps["external_writes"])
                self.assertEqual(
                    client.post("/api/v1/session", headers={"Origin": self.url},
                                json={"token": "unused"}).status_code, 404
                )
                self.assertEqual(
                    client.delete("/api/v1/session",
                                  headers={"Origin": self.url}).status_code, 404
                )

    def test_passwordless_never_inherits_new_or_write_endpoints(self):
        with self.client() as client:
            self.assertEqual(client.post("/api/v1/summaries", json={}).status_code, 401)
            self.assertEqual(client.get("/api/v1/new-privileged-command").status_code, 401)
            self.assertEqual(client.get("/api/v1/runs/no-such-run").status_code, 401)
            self.assertEqual(
                client.get("/api/v1/runs/" + "a" * 32).status_code, 404
            )
            self.assertEqual(
                client.get("/api/v1/runs/" + "a" * 32 + "/send").status_code,
                401,
            )

    def test_remote_client_and_rebinding_host_are_forbidden(self):
        with self.client(address="192.168.1.42") as client:
            self.assertEqual(client.get("/api/v1/summaries").status_code, 403)
        with self.client() as client:
            for hostile_host in ("evil.example:8766", "127.0.0.1.evil.com:8766",
                                 "192.168.1.1:8766"):
                self.assertEqual(
                    client.get("/api/v1/summaries",
                               headers={"Host": hostile_host}).status_code,
                    403,
                )

    def test_cross_site_and_same_site_other_port_are_forbidden(self):
        with self.client() as client:
            for hostile in (
                {"Origin": "https://evil.example"},
                {"Origin": "http://localhost:9000"},
                {"Sec-Fetch-Site": "cross-site"},
                {"Sec-Fetch-Site": "same-site"},
                {"Origin": "http://127.0.0.1:9000",
                 "Sec-Fetch-Site": "same-site"},
            ):
                self.assertEqual(
                    client.get("/api/v1/mail/assistant", headers=hostile).status_code,
                    403,
                    hostile,
                )
            self.assertEqual(
                client.get("/api/v1/mail/assistant",
                           headers={"Origin": self.url,
                                    "Sec-Fetch-Site": "same-origin"}).status_code,
                200,
            )

    def test_protected_mode_requires_old_key_and_preserves_pairing(self):
        with self.client(protected=True) as client:
            self.assertEqual(client.get("/api/v1/summaries").status_code, 401)
            caps_key = self.store.issue_device("browser", 1)["token"]
            r = client.get("/api/v1/capabilities",
                           headers={"Authorization": "Bearer " + caps_key})
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json()["read_key_required"])
            self.assertFalse(r.json()["local_auto_unlock"])
            self.assertEqual(
                client.post("/api/v1/session", json={"token": caps_key}).status_code,
                403,
            )
            exchange = client.post("/api/v1/session",
                                   json={"token": caps_key},
                                   headers={"Origin": self.url,
                                            "Sec-Fetch-Site": "same-origin"})
            self.assertEqual(exchange.status_code, 200)
            self.assertEqual(client.get("/api/v1/summaries").status_code, 200)
            revoke = client.delete("/api/v1/session",
                                   headers={"Origin": self.url,
                                            "Sec-Fetch-Site": "same-origin"})
            self.assertEqual(revoke.status_code, 200)
            self.assertEqual(client.get("/api/v1/summaries").status_code, 401)

    def test_invalid_environment_flag_fails_closed(self):
        with patch.dict(os.environ, {"OKAL_REQUIRE_READ_KEY": "maybe"}):
            with self.assertRaisesRegex(ValueError, "OKAL_REQUIRE_READ_KEY"):
                create_app(self.store)


if __name__ == "__main__":
    unittest.main()
