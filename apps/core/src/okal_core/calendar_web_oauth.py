"""Browser-initiated Google Calendar OAuth using the existing Gmail Desktop client.

Only Google OAuth client identity is reused: NEVER Gmail access/refresh tokens.
This module is intentionally not imported by the Ollama/model runtime.
"""
import json
import re
import secrets
import threading

from .calendar_google import CalendarGoogleError, SCOPES, credential_file
from .mail.private import read_private, root as mail_root, write_private

_GOOGLE_CLIENT = re.compile(r"^[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$")
_CODE = re.compile(r"^[A-Za-z0-9/_\-.]{10,2048}$")
OAUTH_TTL_SECONDS = 300
CALLBACK = "/api/v1/calendar/oauth/callback"


def gmail_desktop_client(store):
    """Reconstruct known, official Desktop client metadata, not Gmail tokens."""
    try:
        gmail = read_private(mail_root(store) / "token.json")
    except (OSError, ValueError, TypeError):
        raise CalendarGoogleError("gmail_oauth_client_unavailable") from None
    client_id = gmail.get("client_id")
    client_secret = gmail.get("client_secret")
    if (not isinstance(client_id, str)
            or len(client_id) > 256
            or not _GOOGLE_CLIENT.fullmatch(client_id)
            or not isinstance(client_secret, str)
            or not 1 <= len(client_secret) <= 256
            or gmail.get("token_uri") != "https://oauth2.googleapis.com/token"):
        raise CalendarGoogleError("gmail_oauth_client_invalid")
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def client_available(store):
    try:
        gmail_desktop_client(store)
        return True
    except CalendarGoogleError:
        return False


class CalendarOAuthWeb:
    """Bounded one-use state + PKCE, scoped to one FastAPI process and loopback."""

    def __init__(self, clock, flow_builder=None):
        self.clock = clock
        self.flow_builder = flow_builder
        self.lock = threading.Lock()
        self.pending = {}

    def start(self, store, host):
        config = gmail_desktop_client(store)
        if not (host.startswith("127.0.0.1:") or host.startswith("localhost:")):
            raise CalendarGoogleError("calendar_oauth_local_host_required")
        if self.flow_builder is None:
            from google_auth_oauthlib.flow import InstalledAppFlow
            builder = InstalledAppFlow.from_client_config
        else:
            builder = self.flow_builder
        flow = builder(config, SCOPES, autogenerate_code_verifier=True)
        flow.redirect_uri = "http://" + host + CALLBACK
        authorization_url, state = flow.authorization_url(
            access_type="offline", prompt="consent select_account",
            include_granted_scopes="false",
        )
        if (not isinstance(authorization_url, str)
                or not authorization_url.startswith(
                    "https://accounts.google.com/o/oauth2/auth?")
                or not isinstance(state, str) or len(state) < 20
                or len(state) > 256):
            raise CalendarGoogleError("invalid_google_oauth_authorization_url")
        with self.lock:
            # One pending consent at a time avoids resource exhaustion and
            # invalidates prior attempts, including expired OAuth windows.
            self.pending.clear()
            self.pending[state] = (flow, int(self.clock()) + OAUTH_TTL_SECONDS)
        return {"authorization_url": authorization_url,
                "expires_seconds": OAUTH_TTL_SECONDS}

    def finish(self, store, state, code, error=None):
        # Always consume a matching state even when Google consent was denied.
        if not isinstance(state, str) or len(state) > 256:
            raise CalendarGoogleError("invalid_calendar_oauth_state")
        with self.lock:
            entry = self.pending.pop(state, None)
        if entry is None or int(self.clock()) >= entry[1]:
            raise CalendarGoogleError("expired_or_replayed_calendar_oauth_state")
        if error:
            raise CalendarGoogleError("calendar_oauth_consent_declined")
        if not isinstance(code, str) or not _CODE.fullmatch(code):
            raise CalendarGoogleError("invalid_calendar_oauth_code")
        flow = entry[0]
        try:
            flow.fetch_token(code=code)
            creds = flow.credentials
        except Exception:
            # Never echo provider error responses (can contain tokens/code).
            raise CalendarGoogleError("calendar_oauth_exchange_failed") from None
        granted = creds.granted_scopes or creds.scopes
        if set(granted or []) != set(SCOPES):
            raise CalendarGoogleError("calendar_oauth_scopes_mismatch")
        data = json.loads(creds.to_json())
        if not data.get("refresh_token"):
            raise CalendarGoogleError("calendar_oauth_refresh_token_missing")
        data["scopes"] = list(granted)
        # Separate private calendar token, never touch mail/token.json.
        write_private(credential_file(store, "default"), data)
        return {"authorization": "configured_not_verified",
                "sync_pending": True, "external_writes": False}
