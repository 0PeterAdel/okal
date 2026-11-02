"""One-use browser Tasks OAuth; separate read-only token and PKCE state."""
import json
import re
import secrets
import threading

from .calendar_web_oauth import gmail_desktop_client
from .google_tasks import SCOPES, GoogleTasksError, private_credentials
from .mail.private import write_private

CALLBACK = "/api/v1/google-tasks/oauth/callback"
_CODE = re.compile(r"^[A-Za-z0-9/_\\-.]{10,2048}$")
TTL = 300


class TasksOAuthWeb:
    def __init__(self, clock, flow_builder=None):
        self.clock, self.flow_builder = clock, flow_builder
        self.lock = threading.Lock()
        self.pending = {}

    def start(self, store, host):
        if not (host.startswith("localhost:") or host.startswith("127.0.0.1:")):
            raise GoogleTasksError("tasks_oauth_localhost_only")
        try:
            client = gmail_desktop_client(store)
        except Exception:
            raise GoogleTasksError("tasks_oauth_client_missing") from None
        if self.flow_builder is None:
            from google_auth_oauthlib.flow import InstalledAppFlow
            builder = InstalledAppFlow.from_client_config
        else:
            builder = self.flow_builder
        flow = builder(client, SCOPES, autogenerate_code_verifier=True)
        flow.redirect_uri = "http://" + host + CALLBACK
        url, state = flow.authorization_url(
            access_type="offline", prompt="consent select_account",
            include_granted_scopes="false",
        )
        if (not isinstance(url, str) or
                not url.startswith("https://accounts.google.com/o/oauth2/auth?") or
                not isinstance(state, str) or not 20 <= len(state) <= 256):
            raise GoogleTasksError("invalid_tasks_oauth_request")
        with self.lock:
            self.pending.clear()
            self.pending[state] = (flow, int(self.clock()) + TTL)
        return {"authorization_url":url,"expires_seconds":TTL}

    def finish(self, store, state, code, error=None):
        if not isinstance(state, str) or len(state) > 256:
            raise GoogleTasksError("invalid_tasks_oauth_state")
        with self.lock:
            entry = self.pending.pop(state, None)
        if entry is None or int(self.clock()) >= entry[1]:
            raise GoogleTasksError("expired_tasks_oauth_state")
        if error:
            raise GoogleTasksError("tasks_oauth_declined")
        if not isinstance(code, str) or not _CODE.fullmatch(code):
            raise GoogleTasksError("invalid_tasks_oauth_code")
        try:
            entry[0].fetch_token(code=code)
            creds = entry[0].credentials
        except Exception:
            raise GoogleTasksError("tasks_oauth_exchange_failed") from None
        granted = creds.granted_scopes or creds.scopes
        if set(granted or []) != set(SCOPES):
            raise GoogleTasksError("tasks_oauth_scope_mismatch")
        payload = json.loads(creds.to_json())
        if not payload.get("refresh_token"):
            raise GoogleTasksError("tasks_oauth_refresh_token_missing")
        payload["scopes"] = list(granted)
        write_private(private_credentials(store, "default"), payload)
        return {"authorization":"configured_not_verified",
                "provider_writes":False,"sync_pending":True}
