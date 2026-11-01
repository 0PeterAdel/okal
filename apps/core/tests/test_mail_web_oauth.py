"""One-click Gmail OAuth: exact permission profile and secure local return."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.calendar_google import credential_file
from okal_core.mail.contracts import MailError
from okal_core.mail.private import read_private, root, write_private
from okal_core.mail.provider import MODIFY, READ, SEND
from okal_core.mail.web_oauth import GmailOAuthWeb, desktop_client, status
from okal_core.store import Store

ACCOUNT = "owner@example.com"
CLIENT = "123456789-test.apps.googleusercontent.com"
STATE = "gmail-unique-state-abcdefghijklmnop012345"
CODE = "4/0ABCDE9999999000000"


class FakeCredentials:
    def __init__(self, scopes):
        self.scopes = list(scopes)
        self.granted_scopes = list(scopes)
        self.refresh_token = "NEW_GMAIL_REFRESH"

    def to_json(self):
        return json.dumps({
            "client_id": CLIENT, "client_secret": "GOCSPX-desktop",
            "token_uri": "https://oauth2.googleapis.com/token",
            "token": "NEW_GMAIL_ACCESS",
            "refresh_token": self.refresh_token,
            "scopes": self.scopes,
        })


class FakeFlow:
    def __init__(self, scopes):
        self.scopes = list(scopes)
        self.credentials = FakeCredentials(scopes)
        self.exchanges = 0
        self.redirect_uri = ""
        self.opts = {}

    def authorization_url(self, **kwargs):
        self.opts = kwargs
        return "https://accounts.google.com/o/oauth2/auth?state=" + STATE, STATE

    def fetch_token(self, **kwargs):
        if kwargs != {"code": CODE}:
            raise RuntimeError("invalid fake OAuth code")
        self.exchanges += 1


class FakeGmail:
    def __init__(self, account=ACCOUNT):
        self.account = account
        self.checked = []
        self.closed = False

    def check_account(self, expected):
        self.checked.append(expected)
        if self.account != expected:
            raise MailError("wrong_google_account")

    def close(self):
        self.closed = True


class GmailBrowserOAuthTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.now = 1793660000
        self.store = Store(Path(temp.name) / "state",
                           clock=lambda: self.now)

    def setup(self, send=False, trash=False, scopes=None,
              with_token=True, sync=True):
        write_private(root(self.store) / "config.json", {
            "account": ACCOUNT,
            "model": "test-model",
            "model_digest": "a" * 64,
            "local_only_confirmed": True,
            "sync_enabled": sync,
            "send_enabled": send,
            "trash_enabled": trash,
        })
        if with_token:
            data = {
                "client_id": CLIENT,
                "client_secret": "GOCSPX-desktop",
                "token_uri": "https://oauth2.googleapis.com/token",
                "token": "OLD_GMAIL_ACCESS",
                "refresh_token": "OLD_GMAIL_REFRESH",
                "scopes": scopes if scopes is not None else [READ],
            }
            write_private(root(self.store) / "token.json", data)

    def flow(self, scopes=None, account=ACCOUNT):
        requested = scopes or [READ]
        fake = FakeFlow(requested)
        provider = FakeGmail(account)
        web = GmailOAuthWeb(
            lambda: self.now,
            flow_builder=lambda client, scopes, **kwargs: self.inspect(
                client, scopes, kwargs, requested, fake
            ),
            gmail_factory=lambda creds: provider,
        )
        return web, fake, provider

    def inspect(self, client, scopes, kwargs, expected, fake):
        self.assertEqual(set(scopes), set(expected))
        self.assertEqual(client["installed"]["client_id"], CLIENT)
        self.assertEqual(kwargs["autogenerate_code_verifier"], True)
        return fake

    def test_read_only_reconnect_preserves_existing_config_and_is_one_use(self):
        self.setup()
        before_cfg = read_private(root(self.store) / "config.json")
        web, fake, provider = self.flow()
        result = web.start(self.store, "127.0.0.1:8766")
        self.assertIn("accounts.google.com", result["authorization_url"])
        self.assertTrue(fake.opts["access_type"] == "offline")
        self.assertTrue(fake.opts["include_granted_scopes"] == "false")
        self.assertTrue(fake.redirect_uri.endswith("/api/v1/mail/oauth/callback"))
        finished = web.finish(self.store, STATE, CODE)
        self.assertTrue(finished["sync_pending"])
        data = read_private(root(self.store) / "token.json")
        self.assertEqual(data["refresh_token"], "NEW_GMAIL_REFRESH")
        self.assertEqual(data["scopes"], [READ])
        self.assertEqual(read_private(root(self.store) / "config.json"), before_cfg)
        self.assertEqual(provider.checked, [ACCOUNT])
        self.assertTrue(provider.closed)
        with self.assertRaisesRegex(MailError, "expired_or_replayed"):
            web.finish(self.store, STATE, CODE)

    def test_send_and_trash_reconnection_request_exact_existing_scopes(self):
        for mode, scopes, send, trash in [
            ("send", [READ, SEND], True, False),
            ("trash", [MODIFY], False, True),
        ]:
            with self.subTest(mode=mode):
                temp = tempfile.TemporaryDirectory()
                try:
                    self.store = Store(Path(temp.name) / "state",
                                       clock=lambda: self.now)
                    self.setup(send=send, trash=trash, scopes=scopes)
                    web, fake, provider = self.flow(scopes=scopes)
                    web.start(self.store, "localhost:8766")
                    web.finish(self.store, STATE, CODE)
                    persisted = read_private(root(self.store) / "token.json")
                    self.assertEqual(set(persisted["scopes"]), set(scopes))
                    self.assertTrue(provider.closed)
                finally:
                    temp.cleanup()

    def test_modify_scope_cannot_satisfy_send_permission(self):
        self.setup(send=True, scopes=[MODIFY])
        old = read_private(root(self.store) / "token.json")
        web, fake, _ = self.flow(scopes=[MODIFY])
        with self.assertRaisesRegex(MailError, "gmail_scope_config_mismatch"):
            web.start(self.store, "localhost:8766")
        self.assertEqual(read_private(root(self.store) / "token.json"), old)
        self.assertEqual(fake.exchanges, 0)

    def test_account_mismatch_keeps_old_token_and_settings(self):
        self.setup(scopes=[READ, SEND], send=True)
        before = read_private(root(self.store) / "token.json")
        before_cfg = read_private(root(self.store) / "config.json")
        web, fake, provider = self.flow(
            scopes=[READ, SEND], account="someone-else@example.com"
        )
        web.start(self.store, "127.0.0.1:8766")
        with self.assertRaisesRegex(MailError, "wrong_google_account"):
            web.finish(self.store, STATE, CODE)
        self.assertTrue(provider.closed)
        self.assertEqual(read_private(root(self.store) / "token.json"), before)
        self.assertEqual(read_private(root(self.store) / "config.json"), before_cfg)

    def test_calendar_client_metadata_bootstraps_read_only_gmail(self):
        self.setup(with_token=False)
        write_private(credential_file(self.store, "default"), {
            "client_id": CLIENT, "client_secret": "GOCSPX-desktop",
            "token_uri": "https://oauth2.googleapis.com/token",
            "token": "CALENDAR_ACCESS_NEVER_COPIED",
            "refresh_token": "CALENDAR_REFRESH_NEVER_COPIED",
        })
        client = desktop_client(self.store)
        self.assertNotIn("CALENDAR_", json.dumps(client))
        web, _, _ = self.flow()
        web.start(self.store, "localhost:8766")
        web.finish(self.store, STATE, CODE)
        gmail = read_private(root(self.store) / "token.json")
        self.assertEqual(gmail["refresh_token"], "NEW_GMAIL_REFRESH")
        self.assertEqual(gmail["scopes"], [READ])

    def test_missing_config_or_client_blocks_authorization_without_token_write(self):
        with self.assertRaises(MailError):
            desktop_client(self.store)
        self.assertEqual(status(self.store)["configuration"], "not_configured")
        self.setup(with_token=False)
        self.assertFalse(status(self.store)["client_available"])
        web, _, _ = self.flow()
        with self.assertRaisesRegex(MailError, "google_desktop_client_unavailable"):
            web.start(self.store, "localhost:8766")

    def test_scope_mismatch_expiry_denial_fail_closed(self):
        self.setup()
        web, fake, _ = self.flow()
        web.start(self.store, "localhost:8766")
        with self.assertRaises(MailError):
            web.finish(self.store, "nonmatching-state", CODE)
        self.now += 301
        with self.assertRaisesRegex(MailError, "expired_or_replayed"):
            web.finish(self.store, STATE, CODE)
        self.assertEqual(fake.exchanges, 0)
        self.assertEqual(read_private(root(self.store) / "token.json")[
            "refresh_token"], "OLD_GMAIL_REFRESH")
        self.now -= 301
        web.start(self.store, "localhost:8766")
        with self.assertRaisesRegex(MailError, "consent_declined"):
            web.finish(self.store, STATE, CODE, "access_denied")
        self.assertEqual(fake.exchanges, 0)

    def test_http_callback_returns_html_and_keeps_other_api_protected(self):
        self.setup()
        fake = FakeFlow([READ])
        fake_provider = FakeGmail()
        with patch(
            "google_auth_oauthlib.flow.InstalledAppFlow.from_client_config",
            return_value=fake,
        ), patch(
            "okal_core.mail.provider.Gmail.from_credentials",
            return_value=fake_provider,
        ):
            with TestClient(
                create_app(self.store), base_url="http://127.0.0.1:8766",
                client=("127.0.0.1", 1234),
            ) as client:
                status_result = client.get("/api/v1/mail/oauth/status")
                self.assertEqual(status_result.status_code, 200)
                self.assertNotIn("refresh_token", status_result.text)
                self.assertEqual(client.post(
                    "/api/v1/mail/oauth/start", json={},
                    headers={"Origin": "https://attacker.example"},
                ).status_code, 403)
                self.assertEqual(client.post(
                    "/api/v1/mail/oauth/start", json={},
                    headers={"Origin": "http://127.0.0.1:8766",
                             "Sec-Fetch-Site": "cross-site"},
                ).status_code, 403)
                started = client.post(
                    "/api/v1/mail/oauth/start", json={},
                    headers={"Origin": "http://127.0.0.1:8766",
                             "Sec-Fetch-Site": "same-origin"},
                )
                self.assertEqual(started.status_code, 200, started.text)
                callback = "/api/v1/mail/oauth/callback"
                args = {"state": STATE, "code": CODE,
                        "iss": "https://accounts.google.com"}
                denied = client.get(
                    callback, params=args, headers={
                        "Origin": "https://attacker.example",
                        "Sec-Fetch-Site": "cross-site",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Dest": "document",
                    }
                )
                self.assertEqual(denied.status_code, 403)
                completed = client.get(
                    callback, params=args, headers={
                        "Origin": "null", "Sec-Fetch-Site": "cross-site",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Dest": "document",
                    },
                )
                self.assertEqual(completed.status_code, 200, completed.text)
                self.assertIn("mail-oauth-return.js", completed.text)
                self.assertNotIn(CODE, completed.text)
                self.assertNotIn(STATE, completed.text)
                self.assertEqual(fake_provider.checked, [ACCOUNT])
                self.assertEqual(client.get(
                    callback, params=args, headers={
                        "Sec-Fetch-Site": "cross-site"},
                ).status_code, 400)
                self.assertEqual(client.get(
                    callback, params={**args, "iss": "https://bad.example"},
                    headers={"Sec-Fetch-Site": "cross-site"},
                ).status_code, 400)
                self.assertEqual(client.get(
                    "/api/v1/mail/oauth/status",
                    headers={"Sec-Fetch-Site": "cross-site"},
                ).status_code, 403)

    def test_protected_mode_never_allows_unauthorized_start(self):
        self.setup()
        with TestClient(create_app(self.store, require_read_key=True),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1234)) as client:
            denied = client.post(
                "/api/v1/mail/oauth/start", json={},
                headers={"Origin": "http://127.0.0.1:8766"},
            )
            self.assertEqual(denied.status_code, 401)


if __name__ == "__main__":
    unittest.main()
