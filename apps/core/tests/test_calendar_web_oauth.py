"""One-click Google Calendar consent without new user-supplied OAuth files."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.calendar_google import SCOPES, credential_file
from okal_core.calendar_web_oauth import (
    CalendarOAuthWeb, client_available, gmail_desktop_client,
)
from okal_core.mail.private import read_private, root as mail_root, write_private
from okal_core.store import Store

CLIENT_ID = "123456789-test.apps.googleusercontent.com"
STATE = "fake-random-state-0123456789abcdef1234567"
AUTH_CODE = "4/0AAABBBCCCDDDEEEFFFGGGHHH"


class FakeCredentials:
    granted_scopes = SCOPES
    scopes = SCOPES
    refresh_token = "CALENDAR_REFRESH_ONLY"

    def to_json(self):
        return json.dumps({
            "token": "CALENDAR_ACCESS_ONLY",
            "refresh_token": self.refresh_token,
            "client_id": CLIENT_ID,
            "client_secret": "GOCSPX-desktop",
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": SCOPES,
        })


class FakeFlow:
    redirect_uri = None
    credentials = FakeCredentials()

    def __init__(self):
        self.exchanged = 0
        self.options = None

    def authorization_url(self, **kwargs):
        self.options = kwargs
        return (
            "https://accounts.google.com/o/oauth2/auth?" +
            urlencode({"state": STATE, "redirect_uri": self.redirect_uri}),
            STATE,
        )

    def fetch_token(self, **kwargs):
        if kwargs != {"code": AUTH_CODE}:
            raise ValueError("wrong test code")
        self.exchanged += 1


class BrowserOAuthTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = Store(Path(tmp.name) / "state", clock=lambda: self.now)
        self.now = 1793655000

    def gmail(self):
        write_private(mail_root(self.store) / "token.json", {
            "client_id": CLIENT_ID, "client_secret": "GOCSPX-desktop",
            "token_uri": "https://oauth2.googleapis.com/token",
            "token": "GMAIL_ACCESS_DO_NOT_COPY",
            "refresh_token": "GMAIL_REFRESH_DO_NOT_COPY",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        })

    def test_client_metadata_extracted_without_gmail_token(self):
        self.gmail()
        data = gmail_desktop_client(self.store)
        self.assertIn("installed", data)
        serialized = json.dumps(data)
        self.assertNotIn("GMAIL_", serialized)
        self.assertNotIn("gmail.readonly", serialized)
        self.assertEqual(data["installed"]["client_id"], CLIENT_ID)

    def test_missing_gmail_client_disables_calendar_connect(self):
        self.assertFalse(client_available(self.store))
        with TestClient(
            create_app(self.store),
            base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1234),
        ) as client:
            status = client.get("/api/v1/calendar/status").json()
            self.assertFalse(status["reuse_gmail_oauth_client_available"])
            response = client.post("/api/v1/calendar/oauth/start", json={},
                                   headers={"Origin": "http://127.0.0.1:8766"})
            self.assertEqual(response.status_code, 409)

    def test_pending_flow_uses_pkce_one_time_state_and_separate_token(self):
        self.gmail()
        flow = FakeFlow()
        manager = CalendarOAuthWeb(
            lambda: self.now,
            flow_builder=lambda config, scopes, **kwargs: self.inspect_flow(
                config, scopes, kwargs, flow
            ),
        )
        created = manager.start(self.store, "127.0.0.1:8766")
        self.assertIn("accounts.google.com", created["authorization_url"])
        self.assertEqual(flow.options["include_granted_scopes"], "false")
        self.assertTrue(flow.redirect_uri.endswith("/api/v1/calendar/oauth/callback"))
        manager.finish(self.store, STATE, AUTH_CODE)
        calendar = read_private(credential_file(self.store, "default"))
        gmail = read_private(mail_root(self.store) / "token.json")
        self.assertEqual(calendar["refresh_token"], "CALENDAR_REFRESH_ONLY")
        self.assertEqual(gmail["refresh_token"], "GMAIL_REFRESH_DO_NOT_COPY")
        self.assertEqual(flow.exchanged, 1)
        with self.assertRaisesRegex(ValueError, "expired_or_replayed"):
            manager.finish(self.store, STATE, AUTH_CODE)

    def inspect_flow(self, config, scopes, kwargs, flow):
        self.assertEqual(set(scopes), set(SCOPES))
        self.assertTrue(kwargs["autogenerate_code_verifier"])
        self.assertEqual(config["installed"]["client_id"], CLIENT_ID)
        return flow

    def test_expiry_mismatch_decline_and_invalid_code(self):
        self.gmail()
        for state, code, error, advance in [
            ("other_state", AUTH_CODE, None, 0),
            (STATE, AUTH_CODE, None, 301),
            (STATE, AUTH_CODE, "access_denied", 0),
            (STATE, "x", None, 0),
        ]:
            with self.subTest(state=state, code=code, error=error, advance=advance):
                manager = CalendarOAuthWeb(
                    lambda: self.now,
                    flow_builder=lambda *args, **kwargs: FakeFlow(),
                )
                manager.start(self.store, "localhost:8766")
                self.now += advance
                with self.assertRaises(ValueError):
                    manager.finish(self.store, state, code, error)
                self.now -= advance
        self.assertFalse(credential_file(self.store, "default").exists())

    def test_http_csrf_origin_host_and_cross_site_callback(self):
        self.gmail()
        fake = FakeFlow()
        with patch(
            "google_auth_oauthlib.flow.InstalledAppFlow.from_client_config",
            return_value=fake,
        ), patch("okal_core.calendar_google.sync_authorized_account") as sync:
            with TestClient(
                create_app(self.store), base_url="http://127.0.0.1:8766",
                client=("127.0.0.1", 1234),
            ) as client:
                self.assertEqual(client.post(
                    "/api/v1/calendar/oauth/start", json={},
                    headers={"Origin": "https://evil.example"},
                ).status_code, 403)
                self.assertEqual(client.post(
                    "/api/v1/calendar/oauth/start", json={},
                    headers={"Origin": "http://127.0.0.1:8766",
                             "Sec-Fetch-Site": "cross-site"},
                ).status_code, 403)
                self.assertEqual(client.get(
                    "/api/v1/calendar/status",
                    headers={"Sec-Fetch-Site": "cross-site"},
                ).status_code, 403)
                self.assertEqual(client.get(
                    "/api/v1/calendar/oauth/callback",
                    params={"state": STATE, "code": AUTH_CODE},
                    headers={"Origin": "https://evil.example",
                             "Sec-Fetch-Site": "cross-site"},
                ).status_code, 403)
                start = client.post(
                    "/api/v1/calendar/oauth/start", json={},
                    headers={"Origin": "http://127.0.0.1:8766",
                             "Sec-Fetch-Site": "same-origin"},
                )
                self.assertEqual(start.status_code, 200, start.text)
                done = client.get(
                    "/api/v1/calendar/oauth/callback",
                    params={"state": STATE, "code": AUTH_CODE,
                            "iss": "https://accounts.google.com"},
                    headers={"Sec-Fetch-Site": "cross-site"},
                    follow_redirects=False,
                )
                self.assertEqual(done.status_code, 200, done.text)
                sync.assert_called_once_with(self.store, "default")
                self.assertIn("calendar-oauth-return.js", done.text)
                self.assertNotIn(AUTH_CODE, done.text)
                self.assertNotIn(STATE, done.text)
                self.assertEqual(client.get(
                    "/api/v1/calendar/oauth/callback",
                    params={"state": STATE, "code": AUTH_CODE},
                    headers={"Sec-Fetch-Site": "cross-site"},
                ).status_code, 400)
                self.assertEqual(client.get(
                    "/api/v1/calendar/status", params={"code": AUTH_CODE}
                ).status_code, 400)

    def test_callback_rejects_wrong_duplicate_or_unknown_issuer_fields(self):
        self.gmail()
        fake = FakeFlow()
        with patch(
            "google_auth_oauthlib.flow.InstalledAppFlow.from_client_config",
            return_value=fake,
        ), patch("okal_core.calendar_google.sync_authorized_account") as sync:
            with TestClient(
                create_app(self.store), base_url="http://127.0.0.1:8766",
                client=("127.0.0.1", 1234),
            ) as client:
                started = client.post(
                    "/api/v1/calendar/oauth/start", json={},
                    headers={"Origin": "http://127.0.0.1:8766"},
                )
                self.assertEqual(started.status_code, 200, started.text)
                callback = "/api/v1/calendar/oauth/callback"
                bad_issuer = client.get(
                    callback,
                    params={"state": STATE, "code": AUTH_CODE,
                            "iss": "https://attacker.example"},
                    headers={"Sec-Fetch-Site": "cross-site"},
                )
                self.assertEqual(bad_issuer.status_code, 400)
                self.assertIn("لم يكتمل ربط Google Calendar", bad_issuer.text)
                self.assertNotIn(AUTH_CODE, bad_issuer.text)
                duplicate = client.get(
                    callback,
                    params=[("state", STATE), ("code", AUTH_CODE),
                            ("iss", "https://accounts.google.com"),
                            ("iss", "https://accounts.google.com")],
                    headers={"Sec-Fetch-Site": "cross-site"},
                )
                self.assertEqual(duplicate.status_code, 400)
                unknown = client.get(
                    callback,
                    params={"state": STATE, "code": AUTH_CODE,
                            "iss": "https://accounts.google.com",
                            "unexpected": "value"},
                    headers={"Sec-Fetch-Site": "cross-site"},
                )
                self.assertEqual(unknown.status_code, 400)
                self.assertIn("لم يكتمل ربط Google Calendar", unknown.text)
                self.assertEqual(fake.exchanged, 0)
                sync.assert_not_called()
                self.assertFalse(credential_file(self.store, "default").exists())

    def test_firefox_google_redirect_origin_null_and_document_navigation(self):
        self.gmail()
        fake = FakeFlow()
        with patch(
            "google_auth_oauthlib.flow.InstalledAppFlow.from_client_config",
            return_value=fake,
        ), patch("okal_core.calendar_google.sync_authorized_account") as sync:
            with TestClient(
                create_app(self.store), base_url="http://127.0.0.1:8766",
                client=("127.0.0.1", 1234),
            ) as client:
                start_headers = {
                    "Origin": "http://127.0.0.1:8766",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "cors",
                }
                callback = "/api/v1/calendar/oauth/callback"
                for browser_origin in ("null", "https://accounts.google.com"):
                    started = client.post(
                        "/api/v1/calendar/oauth/start", json={},
                        headers=start_headers,
                    )
                    self.assertEqual(started.status_code, 200)
                    completed = client.get(
                        callback,
                        params={"state": STATE, "code": AUTH_CODE,
                                "iss": "https://accounts.google.com"},
                        headers={
                            "Origin": browser_origin,
                            "Sec-Fetch-Site": "cross-site",
                            "Sec-Fetch-Mode": "navigate",
                            "Sec-Fetch-Dest": "document",
                        },
                        follow_redirects=False,
                    )
                    self.assertEqual(completed.status_code, 200, completed.text)
                self.assertEqual(sync.call_count, 2)

    def test_callback_exemption_never_allows_untrusted_origin_or_subresource(self):
        self.gmail()
        fake = FakeFlow()
        with patch(
            "google_auth_oauthlib.flow.InstalledAppFlow.from_client_config",
            return_value=fake,
        ), patch("okal_core.calendar_google.sync_authorized_account") as sync:
            with TestClient(
                create_app(self.store), base_url="http://127.0.0.1:8766",
                client=("127.0.0.1", 1234),
            ) as client:
                started = client.post(
                    "/api/v1/calendar/oauth/start", json={},
                    headers={"Origin": "http://127.0.0.1:8766"},
                )
                self.assertEqual(started.status_code, 200)
                callback = "/api/v1/calendar/oauth/callback"
                params = {"state": STATE, "code": AUTH_CODE,
                          "iss": "https://accounts.google.com"}
                for headers in (
                    {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site",
                     "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"},
                    {"Origin": "null", "Sec-Fetch-Site": "cross-site",
                     "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty"},
                    {"Origin": "https://accounts.google.com",
                     "Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "no-cors",
                     "Sec-Fetch-Dest": "script"},
                ):
                    denied = client.get(
                        callback, params=params, headers=headers,
                        follow_redirects=False,
                    )
                    self.assertEqual(denied.status_code, 403, denied.text)
                self.assertEqual(fake.exchanged, 0)
                sync.assert_not_called()
                accepted = client.get(
                    callback, params=params,
                    headers={"Sec-Fetch-Site": "cross-site",
                             "Sec-Fetch-Mode": "navigate",
                             "Sec-Fetch-Dest": "document"},
                    follow_redirects=False,
                )
                self.assertEqual(accepted.status_code, 200, accepted.text)

    def test_cross_site_redirect_chain_lands_only_on_inert_dashboard_html(self):
        self.gmail()
        with TestClient(
            create_app(self.store), base_url="http://127.0.0.1:8766",
            client=("127.0.0.1", 1234),
        ) as client:
            # Firefox sometimes retains a cross-site classification on 303.
            # The dashboard is a non-mutating HTML shell, NOT an API.
            document_headers = {
                "Origin": "null",
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document",
            }
            landed = client.get("/", headers=document_headers)
            self.assertEqual(landed.status_code, 200, landed.text)
            self.assertIn('id="integrations"', landed.text)
            self.assertEqual(client.get(
                "/api/v1/calendar/status", headers=document_headers,
            ).status_code, 403)
            self.assertEqual(client.post(
                "/api/v1/calendar/oauth/start", json={},
                headers={**document_headers,
                         "Content-Type": "application/json"},
            ).status_code, 403)
            self.assertEqual(client.get(
                "/app.js", headers=document_headers,
            ).status_code, 403)
            self.assertEqual(client.get("/", headers={
                **document_headers, "Sec-Fetch-Mode": "cors",
            }).status_code, 403)
            self.assertEqual(client.get("/", headers={
                **document_headers, "Origin": "https://evil.example",
            }).status_code, 403)

    def test_oauth_result_pages_have_no_provider_code_and_script_is_local(self):
        self.gmail()
        with TestClient(
            create_app(self.store), base_url="http://127.0.0.1:8766",
            client=("127.0.0.1", 1234),
        ) as client:
            page = client.get("/api/v1/calendar/oauth/callback",
                              params={"state": "unused_state", "code": AUTH_CODE})
            self.assertEqual(page.status_code, 400)
            self.assertIn("العودة إلى OKAL", page.text)
            self.assertNotIn(AUTH_CODE, page.text)
            response = client.get("/calendar-oauth-return.js")
            self.assertEqual(response.status_code, 200)
            self.assertIn('window.location.replace("/#calendar-connected")',
                          response.text)
            self.assertIn("script-src 'self'", response.headers[
                "content-security-policy"])
            self.assertNotIn(AUTH_CODE, response.text)

    def test_protected_mode_requires_authenticated_start(self):
        self.gmail()
        with TestClient(
            create_app(self.store, require_read_key=True),
            base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1234),
        ) as client:
            response = client.post(
                "/api/v1/calendar/oauth/start", json={},
                headers={"Origin": "http://127.0.0.1:8766"},
            )
            self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
