"""https://okal is an explicit LOCAL alias, not an arbitrary domain.

No network sockets or Google authorization during this test.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from okal_core.api import create_app
from okal_core.store import Store


class LocalOkalHostTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store=Store(Path(tmp.name)/"private")

    def browser(self, *, host="okal", client_ip="127.0.0.1", protected=False):
        return TestClient(
            create_app(self.store, require_read_key=protected),
            base_url=("https://" if host == "okal" else "http://") + host,
            client=(client_ip,12345),
        )

    def test_okal_origin_read_allowed_only_for_loopback_client(self):
        with self.browser() as client:
            r=client.get("/api/v1/health",
                         headers={"Origin":"https://okal",
                                  "Sec-Fetch-Site":"same-origin"})
            self.assertEqual(r.status_code,200,r.text)
            self.assertIn("same-origin",r.headers["Cross-Origin-Resource-Policy"])
            self.assertEqual(client.get("/api/v1/mail/triage").status_code,200)
        with self.browser(client_ip="192.168.1.5") as client:
            self.assertEqual(client.get("/api/v1/health").status_code,403)

    def test_unknown_hosts_same_site_other_port_and_spoofed_forwarded_headers_rejected(self):
        with self.browser() as client:
            for host in ("okal:8766","okal.attacker.example","evil.com",
                         "localhost","127.0.0.1:8766"):
                with self.subTest(host=host):
                    # Host and Origin must both match this precise origin.
                    self.assertEqual(client.get("/api/v1/health",headers={
                        "Host":host,"Origin":"https://okal",
                        "Sec-Fetch-Site":"same-origin",
                    }).status_code,403 if host!="okal" else 200)
            for hdr in (
                {"Origin":"http://localhost:8766"},
                {"Origin":"http://evil.com"},
                {"Sec-Fetch-Site":"cross-site"},
                {"Sec-Fetch-Site":"same-site"},
                {"Origin":"https://okal:80", "Sec-Fetch-Site":"same-origin"},
                {"X-Forwarded-Host":"evil.com","Origin":"http://evil.com"},
            ):
                with self.subTest(headers=hdr):
                    self.assertEqual(client.get("/api/v1/health",
                                                headers=hdr).status_code,403)
            # Forwarded spoofing alone must not turn an otherwise valid
            # loopback same-origin request into a privileged remote request.
            self.assertEqual(client.get("/api/v1/health",headers={
                "X-Forwarded-Host":"evil.example",
                "Origin":"https://okal","Sec-Fetch-Site":"same-origin",
            }).status_code,200)

    def test_http_local_alias_origin_is_rejected_after_https_upgrade(self):
        with self.browser() as client:
            self.assertEqual(client.get("/api/v1/health",headers={
                "Origin":"http://okal","Sec-Fetch-Site":"same-origin",
            }).status_code,403)

    def test_all_google_oauth_starts_redirect_to_desktop_loopback_not_okal(self):
        calls=[]
        def fake_start(self, store, host):
            calls.append(host)
            return {"authorization_url":
                    "https://accounts.google.com/o/oauth2/auth?state=ok",
                    "expires_seconds":300}
        with (patch("okal_core.calendar_web_oauth.CalendarOAuthWeb.start",
                    fake_start),
              patch("okal_core.mail.web_oauth.GmailOAuthWeb.start",
                    fake_start),
              patch("okal_core.google_tasks_oauth.TasksOAuthWeb.start",
                    fake_start)):
            with self.browser() as client:
                for path in (
                    "/api/v1/calendar/oauth/start",
                    "/api/v1/mail/oauth/start",
                    "/api/v1/google-tasks/oauth/start",
                ):
                    res=client.post(path,json={},headers={
                        "Origin":"https://okal",
                        "Sec-Fetch-Site":"same-origin",
                    })
                    self.assertEqual(res.status_code,200,(path,res.text))
                self.assertEqual(calls,["127.0.0.1:8766"]*3)

    def test_sensitive_post_still_rejects_cross_origin_even_if_proxy_exists(self):
        with self.browser() as client:
            for headers in (
                {"Origin":"https://evil.example",
                 "Sec-Fetch-Site":"cross-site"},
                {"Origin":"http://localhost:8766",
                 "Sec-Fetch-Site":"same-origin"},
            ):
                r=client.post("/api/v1/calendar/oauth/start",
                              json={},headers=headers)
                self.assertEqual(r.status_code,403)
            r=client.post("/api/v1/calendar/oauth/start",json={},
                           headers={"Origin":"https://okal",
                                    "Sec-Fetch-Site":"same-origin"})
            # Valid owner origin reaches the action, but lacks Google client
            # credentials in fake private test store.
            self.assertEqual(r.status_code,409,r.text)

    def test_protected_mode_has_no_passwordless_bypass_on_okal(self):
        with self.browser(protected=True) as client:
            self.assertEqual(client.get("/api/v1/mail/triage").status_code,401)
            key=self.store.issue_device("browser",1)["token"]
            res=client.post("/api/v1/session",json={"token":key},headers={
                "Origin":"https://okal","Sec-Fetch-Site":"same-origin"})
            self.assertEqual(res.status_code,200,res.text)
            self.assertIn("Secure",res.headers.get("Set-Cookie",""))
            self.assertEqual(client.get("/api/v1/mail/triage").status_code,200)

    def test_proxy_config_binds_loopback_without_https_or_forwarded_host_rewrite(self):
        root=Path(__file__).resolve().parents[3]
        proxy=(root/"deploy/okal-local.Caddyfile").read_text()
        service=(root/"deploy/okal-local-proxy.service").read_text()
        installer=(root/"scripts/install-okal-local-host.sh").read_text()
        self.assertIn("https://okal {",proxy)
        self.assertIn("bind 127.0.0.1",proxy)
        self.assertIn("tls internal",proxy)
        self.assertIn("redir https://okal{uri} 308",proxy)
        self.assertIn("StateDirectory=okal-local-proxy",service)
        self.assertIn("XDG_DATA_HOME=/var/lib/okal-local-proxy",service)
        self.assertIn("reverse_proxy 127.0.0.1:8766",proxy)
        self.assertNotIn("header_up Host",proxy)
        self.assertIn("header_up -X-Forwarded-Host",proxy)
        self.assertIn("tls internal",proxy)
        self.assertIn("DynamicUser=yes",service)
        self.assertIn("IPAddressDeny=any",service)
        self.assertIn("IPAddressAllow=localhost",service)
        self.assertIn("upgrade-okal-local-https.sh",installer)
        upgrade=(root/"scripts/upgrade-okal-local-https.sh").read_text()
        self.assertIn("sudo -v",upgrade)
        self.assertIn("https://okal/api/v1/health",upgrade)
        self.assertIn("--cacert",upgrade)
        self.assertNotIn("curl -k",upgrade)

    def test_fullcalendar_archive_manifest_not_early_pipe_closed(self):
        root=Path(__file__).resolve().parents[3]
        script=(root/"scripts/install-fullcalendar-standard.sh").read_text()
        self.assertIn('tar -tzf "$package" > "$work/package-list.txt"',script)
        self.assertNotIn('tar -tzf "$package" | grep -Fxq',script)


if __name__ == "__main__":
    unittest.main()
