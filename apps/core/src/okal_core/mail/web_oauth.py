"""Browser-driven Gmail OAuth using the already enrolled Google Desktop client.

OAuth client metadata may be shared across Gmail and Calendar; OAuth access
and refresh tokens, configured accounts, and scopes must never be shared.
"""
import json
import re
import threading

from .contracts import MailError
from .private import config as mail_config, locked, read_private, root, write_private
from .provider import Gmail, MODIFY, READ, SEND
from ..calendar_google import credential_file as calendar_credentials
from ..calendar_web_oauth import gmail_desktop_client

CALLBACK = "/api/v1/mail/oauth/callback"
TTL_SECONDS = 300
_GOOGLE_CLIENT = re.compile(r"^[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$")
_CODE = re.compile(r"^[A-Za-z0-9/_\-.]{10,2048}$")


def _verified_client(info):
    client_id, secret, uri = (
        info.get("client_id"), info.get("client_secret"), info.get("token_uri")
    )
    if (not isinstance(client_id, str) or len(client_id) > 256
            or not _GOOGLE_CLIENT.fullmatch(client_id)
            or not isinstance(secret, str) or not 1 <= len(secret) <= 256
            or uri != "https://oauth2.googleapis.com/token"):
        raise MailError("google_desktop_client_unavailable")
    return {"installed": {
        "client_id": client_id,
        "client_secret": secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": uri,
    }}


def desktop_client(store):
    """Use the existing Gmail credential identity or a previously linked Calendar.

    Do not copy any access/refresh token from either service, ever.
    """
    try:
        return _verified_client(read_private(root(store) / "token.json"))
    except (OSError, ValueError, TypeError):
        pass
    try:
        return _verified_client(read_private(calendar_credentials(store, "default")))
    except (OSError, ValueError, TypeError):
        raise MailError("google_desktop_client_unavailable") from None


def _current_scopes(store, cfg):
    """Re-request exactly the owner's *existing* Gmail permission profile.

    The first authorization from known client metadata grants read only.
    Existing send/trash grants are preserved, never added implicitly.
    """
    if cfg.send_enabled and cfg.trash_enabled:
        raise MailError("invalid_existing_gmail_write_mode")
    try:
        prior = read_private(root(store) / "token.json")
    except FileNotFoundError:
        prior = {}
    except (OSError, ValueError, TypeError):
        raise MailError("invalid_gmail_token_file") from None
    existing = prior.get("scopes")
    if existing is None:
        scopes = [READ]
    else:
        scopes = list(existing) if isinstance(existing, list) else []
        if set(scopes) not in ({READ}, {READ, SEND}, {MODIFY}):
            raise MailError("gmail_scope_config_mismatch")
    granted = set(scopes)
    if cfg.send_enabled and SEND not in granted and MODIFY not in granted:
        raise MailError("gmail_scope_config_mismatch")
    if cfg.trash_enabled and MODIFY not in granted:
        raise MailError("gmail_scope_config_mismatch")
    return sorted(granted)


def status(store):
    try:
        cfg = mail_config(store)
        configured = True
    except (OSError, ValueError, TypeError):
        cfg, configured = None, False
    try:
        desktop_client(store)
        client_ready = True
    except MailError:
        client_ready = False
    token_ready = False
    scopes = "none"
    if configured:
        try:
            data = read_private(root(store) / "token.json")
            current = set(data.get("scopes") or [])
            token_ready = bool(data.get("refresh_token")) and current in (
                {READ}, {READ, SEND}, {MODIFY}
            ) and data.get("token_uri") == "https://oauth2.googleapis.com/token"
            scopes = ("modify" if current == {MODIFY}
                      else "read_and_send" if current == {READ, SEND}
                      else "read_only" if current == {READ} else "invalid")
        except (OSError, ValueError, TypeError):
            pass
    from .history import local_status
    state = local_status(store, cfg.account) if cfg else None
    return {
        "configuration": "configured" if configured else "not_configured",
        "client_available": client_ready,
        "authorization": ("credentials_saved_not_live_verified"
                          if token_ready else "not_connected"),
        "scope_profile": scopes,
        "sync_enabled": bool(cfg and cfg.sync_enabled),
        "last_sync": state,
        "external_writes": False,
    }


class GmailOAuthWeb:
    """Short-lived single-use PKCE OAuth state, process-local only."""

    def __init__(self, clock, flow_builder=None, gmail_factory=None):
        self.clock = clock
        self.flow_builder = flow_builder
        self.gmail_factory = gmail_factory
        self.lock = threading.Lock()
        self.pending = {}

    def start(self, store, host):
        if not re.fullmatch(r"(?:127\.0\.0\.1|localhost):[0-9]{4,5}", host):
            raise MailError("gmail_oauth_local_host_required")
        cfg = mail_config(store)
        client = desktop_client(store)
        scopes = _current_scopes(store, cfg)
        if self.flow_builder is None:
            from google_auth_oauthlib.flow import InstalledAppFlow
            builder = InstalledAppFlow.from_client_config
        else:
            builder = self.flow_builder
        flow = builder(client, scopes, autogenerate_code_verifier=True)
        flow.redirect_uri = "http://" + host + CALLBACK
        authorization_url, state = flow.authorization_url(
            access_type="offline", prompt="consent select_account",
            include_granted_scopes="false",
        )
        if (not isinstance(authorization_url, str)
                or not authorization_url.startswith(
                    "https://accounts.google.com/o/oauth2/auth?")
                or not isinstance(state, str) or not 20 <= len(state) <= 256):
            raise MailError("invalid_gmail_oauth_authorization_url")
        with self.lock:
            self.pending.clear()
            self.pending[state] = (
                flow, int(self.clock()) + TTL_SECONDS,
                cfg.account.casefold(), frozenset(scopes)
            )
        return {"authorization_url": authorization_url,
                "expires_seconds": TTL_SECONDS}

    def finish(self, store, state, code, error=None):
        if not isinstance(state, str) or len(state) > 256:
            raise MailError("invalid_gmail_oauth_state")
        with self.lock:
            item = self.pending.pop(state, None)
        if item is None or int(self.clock()) >= item[1]:
            raise MailError("expired_or_replayed_gmail_oauth_state")
        if error:
            raise MailError("gmail_oauth_consent_declined")
        if not isinstance(code, str) or not _CODE.fullmatch(code):
            raise MailError("invalid_gmail_oauth_code")
        flow, _, account, requested = item
        try:
            flow.fetch_token(code=code)
            credentials = flow.credentials
        except Exception:
            raise MailError("gmail_oauth_exchange_failed") from None
        granted = credentials.granted_scopes or credentials.scopes
        if set(granted or []) != requested:
            raise MailError("gmail_oauth_scopes_mismatch")
        data = json.loads(credentials.to_json())
        if not data.get("refresh_token"):
            raise MailError("gmail_oauth_refresh_token_missing")
        data["scopes"] = sorted(requested)
        # Hold the existing Gmail operator lock during account verification and
        # token commit to avoid racing with the Gmail worker's token refresh.
        with locked(store):
            cfg = mail_config(store)
            if cfg.account.casefold() != account:
                raise MailError("gmail_account_changed_during_oauth")
            if frozenset(_current_scopes(store, cfg)) != requested:
                raise MailError("gmail_permissions_changed_during_oauth")
            factory = self.gmail_factory or Gmail.from_credentials
            try:
                provider = factory(credentials)
                try:
                    provider.check_account(cfg.account)
                finally:
                    provider.close()
            except MailError:
                raise
            except Exception:
                raise MailError("gmail_oauth_profile_check_failed") from None
            # Account and permission profile were validated. Only now replace
            # Gmail's token, without changing send/trash/sync config settings.
            write_private(root(store) / "token.json", data)
        return {"authorization": "credentials_saved_not_live_verified",
                "sync_pending": bool(cfg.sync_enabled), "external_writes": False}
