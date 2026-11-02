"""Loopback-only local Core API, with explicit preview-confirmed Gmail Trash."""

import ipaddress
from pathlib import Path
from urllib.parse import quote
import json
import os
import re

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from .store import InvalidCursor, Store

def _owner_trash_is_configured(store):
    """Configuration hint only — not live OAuth confirmation."""
    try:
        from .mail.private import config
        return bool(config(store).trash_enabled)
    except (OSError, ValueError):
        return False


STATIC = Path(__file__).parent / "static"
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self' data: https:; frame-src 'self' about:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)


def create_app(
    store: Store, port: int = 8766, lifespan=None,
    require_read_key: bool | None = None,
) -> FastAPI:
    # Single-user desktop default: no repetitive read key on loopback.
    # Explicit opt-in restores key-protected API and browser pairing.
    if require_read_key is None:
        setting = os.environ.get("OKAL_REQUIRE_READ_KEY", "0")
        if setting not in {"0", "1"}:
            raise ValueError("OKAL_REQUIRE_READ_KEY must be 0 or 1")
        require_read_key = setting == "1"
    if type(require_read_key) is not bool:
        raise ValueError("require_read_key must be boolean")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    from .mail.approval import PendingTrashConfirmations
    approvals = PendingTrashConfirmations(store.clock)
    from .calendar_web_oauth import CalendarOAuthWeb, CALLBACK
    from .google_tasks_oauth import TasksOAuthWeb, CALLBACK as TASKS_CALLBACK
    calendar_oauth = CalendarOAuthWeb(store.clock)
    tasks_oauth = TasksOAuthWeb(store.clock)
    from .mail.web_oauth import GmailOAuthWeb, CALLBACK as GMAIL_CALLBACK
    gmail_oauth = GmailOAuthWeb(store.clock)
    from .day_planner import DayPlanManager
    day_plans = DayPlanManager(store)
    # Only the explicitly supported local reverse-proxy hostname. Never
    # trust arbitrary DNS names or forwarded host headers.
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}", "okal"}

    def browser_origin(host):
        # HTTPS is mandatory for the private hostname. Direct 127.0.0.1
        # continues to support Google Desktop OAuth loopback redirects.
        return "https://okal" if host == "okal" else f"http://{host}"

    def oauth_loopback_host(request):
        """Desktop Google OAuth only accepts a loopback redirect, not 'okal'.

        The browser can use http://okal, but the authorization code must be
        returned to the existing direct localhost port, preserving PKCE.
        """
        host = request.headers.get("host", "")
        return f"127.0.0.1:{port}" if host == "okal" else host

    # Never let a future privileged /api/ endpoint inherit passwordless access.
    local_read_paths = {
        "/api/v1/health", "/api/v1/capabilities", "/api/v1/summaries",
        "/api/v1/mail/triage", "/api/v1/mail/assistant", "/api/v1/tasks",
        "/api/v1/morning", "/api/v1/planner",
        "/api/v1/tasks/history", "/api/v1/calendar/agenda",
        "/api/v1/calendar/availability", "/api/v1/calendar/status",
        "/api/v1/calendar/plan",
        "/api/v1/calendar/day-plan/saved",
        "/api/v1/google-tasks/status", "/api/v1/google-tasks/cached",
        "/api/v1/mail/oauth/status",
    }

    def public_local_read(path, method):
        return method == "GET" and (
            path in local_read_paths
            or re.fullmatch(r"/api/v1/runs/[a-f0-9]{32}", path) is not None
            or re.fullmatch(r"/api/v1/mail/messages/[a-fA-F0-9]{1,64}", path) is not None
        )

    def authorized_ui_trash(request):
        # This route is write-sensitive even when the rest of the dashboard
        # auto-opens: enforce browser same-origin + JSON + fresh preview ticket.
        return (
            request.url.path in {
                "/api/v1/mail/trash", "/api/v1/mail/trash/preview",
                "/api/v1/mail/actions/preview", "/api/v1/mail/actions/commit",
                "/api/v1/mail/viewed",
                "/api/v1/mail/image-preference",
                "/api/v1/mail/tasks/from-message",
                "/api/v1/tasks/create", "/api/v1/tasks/edit",
                "/api/v1/tasks/transition",
                "/api/v1/mail/reply-drafts/generate",
                "/api/v1/mail/reply-drafts/revise",
                "/api/v1/mail/reply-drafts/preview-send",
                "/api/v1/mail/reply-drafts/confirm-send",
                "/api/v1/calendar/oauth/start",
                "/api/v1/google-tasks/oauth/start",
                "/api/v1/mail/oauth/start",
                "/api/v1/calendar/day-plan/preview",
                "/api/v1/calendar/day-plan/ai-suggest",
                "/api/v1/calendar/day-plan/confirm"
            }
            and request.method == "POST"
            and request.headers.get("origin") == browser_origin(
                request.headers.get("host", "")
            )
            and request.headers.get("sec-fetch-site", "same-origin")
                in {"same-origin", "none"}
            and request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                == "application/json"
            # Protected mode still requires an authenticated browser session.
            and (not require_read_key
                 or store.authenticate_browser_session(
                    request.cookies.get("okal_session", "")
                 ))
        )

    def is_google_oauth_callback(request):
        # Google redirects the owner's top-level browser navigation here.
        # Firefox can send Origin: null after cross-site redirects; other
        # browsers may send the Google origin or omit Origin entirely.
        # This exception is ONLY for a document GET to the OAuth callback;
        # its state, issuer, one-use nonce and PKCE are checked below.
        host = request.headers.get("host", "")
        origin = request.headers.get("origin")
        return (
            request.method == "GET"
            and request.url.path in {CALLBACK, GMAIL_CALLBACK, TASKS_CALLBACK}
            and origin in (None, "null", "https://accounts.google.com",
                           browser_origin(host))
            and request.headers.get("sec-fetch-mode") in (None, "navigate")
            and request.headers.get("sec-fetch-dest") in (None, "document")
        )

    def is_dashboard_document_navigation(request):
        # A browser may keep Sec-Fetch-Site: cross-site across OAuth 303
        # redirects. Opening only the inert HTML shell is safe; API calls,
        # POSTs, subresources and framing retain the existing strict policy.
        return (
            request.method == "GET"
            and request.url.path == "/"
            and request.headers.get("origin") in (None, "null")
            and request.headers.get("sec-fetch-mode") == "navigate"
            and request.headers.get("sec-fetch-dest") == "document"
        )

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        # Do not trust forwarded headers; the supported launcher disables them.
        try:
            local = (
                request.client is not None
                and ipaddress.ip_address(request.client.host).is_loopback
            )
        except ValueError:
            local = False
        host = request.headers.get("host", "")
        origin = request.headers.get("origin")
        if (
            not local
            or host not in hosts
            or (origin is not None and origin != browser_origin(host)
                and not is_google_oauth_callback(request)
                and not is_dashboard_document_navigation(request))
            or (request.headers.get("sec-fetch-site") in {"cross-site", "same-site"}
                and not is_google_oauth_callback(request)
                and not is_dashboard_document_navigation(request))
            or (
                request.url.path == "/api/v1/session"
                and request.method in {"POST", "DELETE"}
                and (
                    origin != browser_origin(host)
                    or request.headers.get("sec-fetch-site", "same-origin")
                    not in {"same-origin", "none"}
                )
            )
        ):
            response = JSONResponse(
                {"detail": "local same-origin access required"}, status_code=403
            )
        elif (
            not require_read_key
            and request.url.path == "/api/v1/session"
        ):
            # The old session endpoints are not needed in local auto-unlock
            # mode. Keep them available only in explicit protected mode.
            response = JSONResponse(
                {"detail": "pairing disabled in local auto-unlock mode"},
                status_code=404,
            )
        elif (
            request.url.path.startswith("/api/")
            and request.url.path != "/api/v1/health"
            and not (
                not require_read_key
                and public_local_read(request.url.path, request.method)
            )
            and not authorized_ui_trash(request)
            and not is_google_oauth_callback(request)
            and not (
                require_read_key
                and request.url.path == "/api/v1/session"
                and request.method == "POST"
            )
            and not (
                require_read_key
                and (
                    store.authenticate_browser_session(request.cookies.get("okal_session", ""))
                    or (
                        len(request.headers.getlist("authorization")) == 1
                        and request.headers.get("authorization", "").startswith("Bearer ")
                        and store.authenticate(request.headers.get("authorization", "")[7:])
                    )
                )
            )
        ):
            response = JSONResponse(
                {"detail": "valid read token required"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        elif any(
            k
            not in (
                {"limit", "cursor"}
                if request.url.path == "/api/v1/summaries"
                else {"state", "code", "scope", "authuser", "prompt",
                      "error", "error_description", "iss"}
                if is_google_oauth_callback(request)
                else {"days"} if request.url.path == "/api/v1/calendar/plan"
                else set()
            )
            for k in request.query_params
        ):
            if is_google_oauth_callback(request):
                response = FileResponse(
                    STATIC / ("mail-oauth-error.html"
                              if request.url.path == GMAIL_CALLBACK
                              else "calendar-oauth-error.html"),
                    media_type="text/html", status_code=400,
                )
            else:
                response = JSONResponse(
                    {"detail": "unsupported query parameter"}, status_code=400
                )
        else:
            response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": CSP,
                "X-Frame-Options": "DENY",
                "Cross-Origin-Resource-Policy": "same-origin",
                "Cross-Origin-Opener-Policy": "same-origin",
            }
        )
        return response

    @app.post("/api/v1/session")
    async def pair_browser(request: Request):
        """One-time local read-key exchange; cookie grants read scope only."""
        body = await request.body()
        if len(body) > 256:
            raise HTTPException(400, "invalid pairing request")
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict) or set(payload) != {"token"}:
                raise ValueError()
            key = payload["token"]
        except (ValueError, TypeError):
            raise HTTPException(400, "invalid pairing request") from None
        if not isinstance(key, str):
            raise HTTPException(400, "invalid pairing request")
        session = store.issue_browser_session(key)
        if session is None:
            raise HTTPException(401, "invalid or expired local read key")
        age = max(0, session["expires_at"] - int(store.clock()))
        response = JSONResponse({"status": "paired", "expires_at": session["expires_at"],
                                 "permissions": ["inbox:read"]})
        # Loopback HTTP, host-only, HttpOnly and SameSite Strict. No JS storage.
        response.set_cookie(
            "okal_session", session["token"], httponly=True,
            secure=request.headers.get("host") == "okal",
            samesite="strict", max_age=age, path="/api",
        )
        return response

    @app.delete("/api/v1/session")
    def unpair_browser(request: Request):
        store.revoke_browser_session(request.cookies.get("okal_session", ""))
        response = JSONResponse({"status": "session_revoked"})
        response.delete_cookie("okal_session", path="/api")
        return response

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "schema_version": 1}

    @app.get("/api/v1/capabilities")
    def capabilities():
        from .mail.status import snapshot

        mail_status = snapshot(store)
        configured = mail_status["configuration"] == "configured"
        scheduled = configured and mail_status["daily_at"] is not None
        setup_state = {
            "absent": "disabled",
            "configured": "configured_not_verified",
            "invalid": "invalid_configuration",
        }[mail_status["configuration"]]
        return {
            "schema_version": 1,
            "mode": "local-read-only",
            "read_key_required": require_read_key,
            "local_auto_unlock": not require_read_key,
            "permissions": ["inbox:read"],
            "external_writes": False,
            "ui_trash_available": (
                configured and _owner_trash_is_configured(store)
            ),
            "ui_trash_requires_explicit_confirmation": True,
            "providers": ["gmail-configured-not-verified"] if configured else [],
            "scheduler": scheduled,
            "mail_operator_cli": configured,
            "scheduler_status": setup_state,
            "remote_pairing": False,
            "voice": False,
            "mail": mail_status,
        }

    @app.get("/api/v1/mail/triage")
    def mail_triage():
        """Read-only bounded structured triage; never triggers Gmail or Ollama."""
        from .mail.private import config
        from .mail.history import recent_evidence, recent_quarantines

        try:
            cfg = config(store)
        except Exception:
            return {"items": [], "state": "not_configured"}
        with store.connect() as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mail_sync_insights'"
            ).fetchone()
        if not exists:
            return {"items": [], "state": "not_initialized"}
        items = []
        for row in recent_evidence(store, cfg.account, 60):
            m, i = row["metadata"], row["insight"]
            from .mail.owner_voice import owner_voice
            items.append({
                "id": m["id"], "subject": m["subject"], "sender": m["sender"],
                "received_ms": m["received_ms"], "labels": m["labels"],
                "category": i["category"],
                "summary": owner_voice(i["summary"], cfg.owner_name),
                "suggested_action": owner_voice(i["suggested_action"], cfg.owner_name),
                "has_unread_attachments": m["attachment_count"] > 0,
                "link": "https://mail.google.com/mail/?authuser="
                + quote(cfg.account, safe="")
                + "#all/" + m["id"], "created_at": row["created_at"],
            })
        manual_labels = {
            "unreadable_message": "محتوى غير قابل للقراءة / Unreadable message",
            "message_exceeds_size_budget": "رسالة كبيرة / Message too large",
            "mime_complexity_budget_exceeded": "تركيب MIME معقد / Complex MIME",
            "ambiguous_message_headers": "ترويسات غير واضحة / Ambiguous headers",
            "body_requires_attachment_fetch_manual_review": "محتوى مرفق لم يُقرأ / Attached body",
            "message_body_truncated_narrow_scope_or_review_manually": "محتوى طويل جدًا / Truncated text",
            "message_disappeared": "رسالة لم تعد متاحة / Message disappeared",
        }
        for record in recent_quarantines(store, cfg.account, 60):
            items.append({
                "id": record["message_id"],
                "subject": "مراجعة الرسالة الأصلية / Open original email",
                "sender": "Gmail", "received_ms": record["detected_at"] * 1000,
                "labels": [], "category": "manual_review",
                "summary": manual_labels.get(record["code"], "تعذر التحليل / Cannot analyze"),
                "suggested_action": "افتح Gmail وتحقق يدويًا / Review in Gmail",
                "has_unread_attachments": False,
                "link": "https://mail.google.com/mail/?authuser="
                + quote(cfg.account, safe="") + "#all/" + record["message_id"],
                "created_at": record["detected_at"],
            })
        return {"items": items, "state": "recorded_local_insights"}

    @app.get("/api/v1/mail/messages/{message_id}")
    def full_mail_message(message_id: str):
        """Explicit on-click Gmail read, never called by regular dashboard load."""
        from .mail.viewer import read_native
        from .mail.contracts import MailError

        try:
            return read_native(store, message_id)
        except MailError as exc:
            code = str(exc)
            raise HTTPException(
                404 if code.startswith("viewer_source_") else 422,
                code
            ) from None

    @app.post("/api/v1/mail/image-preference")
    async def set_mail_image_preference(request: Request):
        """Explicit owner choice, private SQLite only, never remote fetch."""
        from .mail.private import config
        from .mail.inbox_visibility import save_image_preference
        payload=await action_payload(request,{"allow_remote_images"})
        if type(payload["allow_remote_images"]) is not bool:
            raise HTTPException(400,"invalid_remote_image_preference")
        return save_image_preference(
            store,config(store).account,payload["allow_remote_images"]
        )

    @app.post("/api/v1/mail/viewed")
    async def mark_local_mail_viewed(request: Request):
        """One owner interaction acknowledges a successfully opened message.

        Local-only projection. Does NOT mark Gmail read, send or delete mail.
        """
        from .mail.private import config
        from .mail.contracts import MailError
        from .mail.inbox_visibility import mark_viewed
        payload = await action_payload(request, {"message_id"})
        mid = payload["message_id"]
        try:
            return mark_viewed(store,config(store).account,mid)
        except (ValueError,MailError) as exc:
            raise HTTPException(409,str(exc)) from None

    @app.post("/api/v1/mail/trash/preview")
    async def ui_trash_preview(request: Request):
        """Read exact Gmail subjects before user authorizes any Trash writes."""
        from .mail.contracts import MailError
        from .mail.private import config, locked
        from .mail.provider import Gmail
        from .mail.trash import preview
        payload_bytes = await request.body()
        if len(payload_bytes) > 2500:
            raise HTTPException(413, "trash_preview_too_large")
        try:
            payload = json.loads(payload_bytes)
            if not isinstance(payload, dict) or set(payload) != {"ids"}:
                raise ValueError()
            ids = payload["ids"]
            if not isinstance(ids, list):
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(400, "invalid_trash_preview") from None
        try:
            with locked(store):
                cfg = config(store)
                api = Gmail.open(store, cfg)
                try:
                    result = preview(store, cfg, api, ids)
                    # Preview result is read-only. The single-use ticket binds
                    # the exact ID order and Gmail metadata digest.
                    result["confirmation_token"] = approvals.issue(
                        ids, result["approval_digest"]
                    )
                    result["confirmation_expires_seconds"] = 120
                    return result
                finally:
                    api.close()
        except MailError as exc:
            code = str(exc)
            # Stable machine-readable codes, never token/provider exception text.
            status = (
                423 if code == "mail_operation_already_running"
                else 401 if code == "authorization_required"
                else 403 if code in {"scope_or_send_permission_mismatch",
                                    "wrong_google_account"}
                else 409
            )
            raise HTTPException(status, code) from None

    @app.post("/api/v1/mail/trash")
    async def ui_move_to_trash(request: Request):
        """Owner-confirmed recoverable Gmail Trash only. No permanent deletion."""
        from .mail.contracts import MailError
        from .mail.private import config, locked
        from .mail.provider import Gmail
        from .mail.trash import apply

        body = await request.body()
        if len(body) > 3000:
            raise HTTPException(413, "trash_request_too_large")
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict) or set(payload) != {
                "ids", "confirmed", "approval_digest", "confirmation_token"
            } or payload["confirmed"] is not True:
                raise ValueError()
            ids = payload["ids"]
            confirmation_token = payload["confirmation_token"]
            approved_digest = payload["approval_digest"]
            if not isinstance(approved_digest, str) or not re.fullmatch(
                r"[a-f0-9]{64}", approved_digest
            ):
                raise ValueError()
            if not isinstance(ids, list) or not 1 <= len(ids) <= 20:
                raise ValueError()
            if (not isinstance(confirmation_token, str)
                    or not 40 <= len(confirmation_token) <= 90):
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(400, "invalid_trash_request") from None

        try:
            with locked(store):
                cfg = config(store)
                if not cfg.trash_enabled:
                    raise MailError("trash_permission_disabled_reauthorize")
                api = Gmail.open(store, cfg, trashing=True)
                try:
                    # No password. User must have clicked the button on a
                    # valid, same-origin preview. Consume BEFORE any write
                    # attempt; an uncertain result cannot be replayed.
                    if not approvals.consume(
                        ids, approved_digest, confirmation_token
                    ):
                        raise MailError("trash_confirmation_expired_or_invalid")
                    return apply(store, cfg, api, ids, approved_digest)
                finally:
                    api.close()
        except MailError as exc:
            code = str(exc)
            status = (
                403 if code.startswith("trash_permission_disabled")
                else 401 if code == "authorization_required"
                else 423 if code == "mail_operation_already_running"
                else 409
            )
            raise HTTPException(status, code) from None

    async def action_payload(request, required):
        body = await request.body()
        if len(body) > 3000:
            raise HTTPException(413, "mail_agent_request_too_large")
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError):
            raise HTTPException(400, "mail_agent_invalid_json") from None
        if not isinstance(payload, dict) or set(payload) != set(required):
            raise HTTPException(400, "mail_agent_invalid_fields")
        return payload

    def action_failure(exc):
        code = str(exc)
        return HTTPException(
            423 if code == "mail_operation_already_running"
            else 401 if code == "authorization_required"
            else 403 if code in {"gmail_modify_scope_required",
                                "scope_or_send_permission_mismatch"}
            else 409, code,
        )

    @app.post("/api/v1/mail/actions/preview")
    async def mail_action_preview(request: Request):
        """Read native Gmail metadata; issue one-use action-bound approval."""
        from .mail.contracts import MailError
        from .mail.private import config, locked
        from .mail.provider import Gmail
        from .mail.operations import preview

        payload = await action_payload(request, {"ids", "action"})
        try:
            with locked(store):
                cfg = config(store)
                api = Gmail.open(store, cfg)
                try:
                    result = preview(store, cfg, api,
                                     payload["ids"], payload["action"])
                    result["confirmation_token"] = approvals.issue(
                        [result["action"], *payload["ids"]],
                        result["approval_digest"]
                    )
                    result["expires_seconds"] = 120
                    return result
                finally:
                    api.close()
        except MailError as exc:
            raise action_failure(exc) from None

    @app.post("/api/v1/mail/actions/commit")
    async def mail_action_commit(request: Request):
        from .mail.contracts import MailError
        from .mail.private import config, locked
        from .mail.provider import Gmail
        from .mail.operations import apply

        payload = await action_payload(request,
            {"ids","action","approval_digest","confirmation_token","confirmed"})
        ids = payload["ids"]
        action = payload["action"]
        digest = payload["approval_digest"]
        ticket = payload["confirmation_token"]
        if (payload["confirmed"] is not True or not isinstance(ids, list)
            or not isinstance(action, str)
            or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}",digest)
            or not isinstance(ticket, str) or not 40 <= len(ticket) <= 90):
            raise HTTPException(400, "mail_action_invalid_approval")
        try:
            with locked(store):
                cfg = config(store)
                if not cfg.trash_enabled:
                    raise MailError("gmail_modify_scope_required")
                api = Gmail.open(store, cfg, trashing=True)
                try:
                    if not approvals.consume([action, *ids], digest, ticket):
                        raise MailError("mail_action_confirmation_expired")
                    return apply(store, cfg, api, ids, action, digest)
                finally:
                    api.close()
        except MailError as exc:
            raise action_failure(exc) from None

    @app.post("/api/v1/mail/tasks/from-message")
    async def mail_to_local_task(request: Request):
        """Explicit one-click local task: idempotent, no external writes."""
        from .mail.private import config
        from .mail.contracts import MailError
        from .tasks import TaskBoard

        body = await request.body()
        if len(body)>3000:
            raise HTTPException(413,"task_request_too_large")
        try:
            payload=json.loads(body)
            if (not isinstance(payload,dict) or
                    "message_id" not in payload or
                    not set(payload)<={
                        "message_id","title","due","reminder_minutes"}):
                raise ValueError()
        except (ValueError,TypeError):
            raise HTTPException(400,"invalid_task_request") from None
        mid = payload["message_id"]
        if not isinstance(mid, str) or not re.fullmatch(r"[a-fA-F0-9]{1,64}",mid):
            raise HTTPException(400, "invalid_message_id")
        try:
            from .task_planner import TaskPlanner
            cfg = config(store)
            return TaskPlanner(store).from_mail(
                cfg.account,mid,title=payload.get("title"),
                due=payload.get("due"),
                reminder_minutes=payload.get("reminder_minutes")
            )
        except (ValueError, MailError) as exc:
            raise action_failure(exc) from None

    @app.post("/api/v1/mail/reply-drafts/generate")
    async def generate_local_mail_reply(request: Request):
        """Explicit, pinned local Ollama; saves draft to SQLite, NEVER sends."""
        from .mail.private import config, locked
        from .mail.contracts import MailError
        from .mail.provider import Gmail
        from .mail.inference import LocalModel
        from .mail.viewer import allowed_source
        from .mail.workflows import reply_draft
        from .mail.state import MailState
        payload = await action_payload(request, {"message_id","language"})
        mid, language = payload["message_id"], payload["language"]
        if (not isinstance(mid,str) or not re.fullmatch(r"[a-fA-F0-9]{1,64}",mid)
                or not isinstance(language,str) or language not in {"ar","en"}):
            raise HTTPException(400,"invalid_reply_request")
        try:
            with locked(store):
                cfg = config(store)
                if allowed_source(store,cfg.account.casefold(),mid) is None:
                    raise MailError("reply_manual_review_required")
                api = Gmail.open(store,cfg)
                model = LocalModel(cfg)
                try:
                    language_instruction = (
                        "Draft a concise professional Egyptian Arabic reply. "
                        "Do not invent any commitments, dates or prices. "
                        "No send; owner will inspect and edit."
                        if language == "ar" else
                        "Draft a concise professional English reply. "
                        "Do not invent commitments, dates or prices. "
                        "No send; owner will inspect and edit."
                    )
                    draft_id = reply_draft(store,cfg,api,model,mid,language_instruction)
                    row = MailState(store).draft(draft_id)
                    saved = json.loads(row["payload"])
                    return {
                        "status":"draft_saved_local_only","draft_id":draft_id,
                        "recipient":saved["recipient"],
                        "subject":saved["subject"],"body":saved["body"],
                        "sent":False,"owner_review_required":True,
                    }
                finally:
                    model.close()
                    api.close()
        except MailError as exc:
            raise action_failure(exc) from None

    @app.post("/api/v1/mail/reply-drafts/revise")
    async def revise_local_mail_reply(request: Request):
        """Owner edits a new local draft; original and previous draft preserved."""
        from .mail.contracts import Draft, MailError
        from .mail.private import config
        from .mail.state import MailState
        payload = await action_payload(request, {"draft_id","body"})
        key, text = payload["draft_id"], payload["body"]
        if (not isinstance(key,str) or not re.fullmatch(r"[a-f0-9]{32}",key)
                or not isinstance(text,str) or not 1 <= len(text) <= 8000):
            raise HTTPException(400,"invalid_reply_revision")
        try:
            cfg = config(store)
            state = MailState(store)
            old = state.draft(key)
            if old["account"] != cfg.account.casefold():
                raise MailError("wrong_draft_account")
            previous = Draft.model_validate_json(old["payload"])
            new_draft = previous.model_copy(update={"body":text})
            new_draft = Draft.model_validate(new_draft.model_dump())
            updated = state.new_draft(cfg.account,new_draft)
            return {"status":"revised_draft_saved_local_only","draft_id":updated,
                    "sent":False}
        except (MailError,ValueError) as exc:
            raise action_failure(exc) from None

    @app.post("/api/v1/mail/reply-drafts/preview-send")
    async def preview_owner_send(request: Request):
        """Read exact local draft; preview is NOT a Gmail send."""
        from .mail.private import config
        from .mail.contracts import MailError, Draft
        from .mail.state import MailState

        payload = await action_payload(request, {"draft_id"})
        key = payload["draft_id"]
        if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{32}",key):
            raise HTTPException(400, "invalid_send_draft_id")
        try:
            cfg = config(store)
            if not cfg.trash_enabled:
                raise MailError("gmail_modify_scope_required")
            state = MailState(store)
            old = state.draft(key)
            if old["account"] != cfg.account.casefold():
                raise MailError("wrong_draft_account")
            exact = state.preview(key)
            draft = Draft.model_validate(exact["draft"])
            # All recipient and body fields are validated from trusted
            # owner-owned drafts, never from a supplied browser send body.
            nonce = approvals.issue(["send",key], exact["approval_digest"])
            return {
                "draft_id":key, "recipient":draft.recipient,
                "subject":draft.subject,"body":draft.body,
                "approval_digest":exact["approval_digest"],
                "confirmation_token":nonce,"expires_seconds":120,
                "external_writes":False, "owner_review_required":True,
                "warning":"This will SEND an email. Verify recipient, claims and commitments. No attachments/reply-all.",
            }
        except (MailError,ValueError) as exc:
            raise action_failure(exc) from None

    @app.post("/api/v1/mail/reply-drafts/confirm-send")
    async def confirm_owner_send(request: Request):
        """Two-step owner-approved Gmail send; never retry an uncertain result."""
        from .mail.private import config, locked
        from .mail.contracts import MailError
        from .mail.provider import Gmail
        from .mail.workflows import send_reviewed

        payload = await action_payload(request,
            {"draft_id","approval_digest","confirmation_token","confirmed"})
        key, digest, ticket = (payload["draft_id"],
                              payload["approval_digest"],
                              payload["confirmation_token"])
        if (payload["confirmed"] is not True
            or not isinstance(key,str) or not re.fullmatch(r"[a-f0-9]{32}",key)
            or not isinstance(digest,str) or not re.fullmatch(r"[a-f0-9]{64}",digest)
            or not isinstance(ticket,str) or not 40 <= len(ticket) <= 90):
            raise HTTPException(400, "invalid_send_confirmation")
        try:
            with locked(store):
                cfg = config(store)
                if not cfg.trash_enabled:
                    raise MailError("gmail_modify_scope_required")
                # The Google gmail.modify scope includes Gmail send, but do
                # not turn on autonomous/CLI send in persistent config.
                api = Gmail.open(store,cfg,trashing=True)
                try:
                    if not approvals.consume(["send",key],digest,ticket):
                        raise MailError("mail_send_confirmation_expired")
                    verified_cfg = cfg.model_copy(update={"send_enabled":True})
                    return send_reviewed(store,verified_cfg,api,key,digest)
                finally:
                    api.close()
        except MailError as exc:
            raise action_failure(exc) from None

    @app.get("/api/v1/mail/assistant")
    def mail_assistant():
        """Rule-driven queue from saved evidence only; no provider/model calls."""
        from .mail.assistant import proposals
        from .mail.private import config
        from .mail.contracts import MailError

        try:
            cfg = config(store)
        except (MailError, OSError, ValueError):
            return {"state": "not_configured", "items": [], "counts": {},
                    "external_writes": False}
        try:
            return proposals(store, cfg.account, limit=60)
        except (MailError, ValueError):
            # Do not render potentially unsafe/malformed local rules as success.
            raise HTTPException(422, "local assistant rules or saved evidence invalid") from None

    @app.get("/api/v1/morning")
    def morning():
        """Read-only cached AI morning view; NEVER invokes Ollama on HTTP GET."""
        from .morning_ai import view

        return view(store)

    @app.get("/api/v1/tasks")
    def local_tasks():
        """Read-only task board, with locally scheduled reminder status."""
        from .task_planner import TaskPlanner
        return TaskPlanner(store).list("open",100)

    @app.get("/api/v1/tasks/history")
    def local_task_history():
        """Read-only local complete/dismissed task list, for reopen buttons."""
        from .task_planner import TaskPlanner
        return TaskPlanner(store).list("all",100)

    @app.get("/api/v1/planner")
    def local_agenda():
        """Local Cairo-tz agenda. Never claims Google Calendar coverage."""
        from .task_planner import TaskPlanner
        return TaskPlanner(store).agenda(7)

    @app.get("/api/v1/calendar/agenda")
    def local_calendar_agenda():
        """Cached calendar projection only; never contacts providers."""
        from .calendar_core import CalendarCore
        return CalendarCore(store).agenda()

    @app.get("/api/v1/mail/oauth/status")
    def gmail_oauth_status():
        """Read local Gmail OAuth metadata only, no Google API calls."""
        from .mail.web_oauth import status
        return status(store)

    @app.post("/api/v1/mail/oauth/start")
    async def start_gmail_connect(request: Request):
        """Same-origin user gesture authorizes existing Gmail scope profile."""
        from .mail.contracts import MailError
        await action_payload(request, set())
        try:
            return gmail_oauth.start(store, oauth_loopback_host(request))
        except MailError as exc:
            raise HTTPException(409, str(exc)) from None
        except (OSError, ValueError):
            raise HTTPException(409, "gmail_setup_required") from None

    @app.get("/api/v1/mail/oauth/callback")
    def finish_gmail_connect(request: Request):
        """Validate Google response and existing mailbox before token commit."""
        from .mail.contracts import MailError
        params = request.query_params
        if (len(params.getlist("state")) != 1
                or len(params.getlist("code")) > 1
                or len(params.getlist("iss")) > 1
                or ("iss" in params and
                    params.get("iss") != "https://accounts.google.com")):
            return FileResponse(
                STATIC / "mail-oauth-error.html",
                media_type="text/html", status_code=400,
            )
        try:
            gmail_oauth.finish(
                store, params.get("state"), params.get("code"),
                params.get("error")
            )
        except (MailError, OSError, ValueError):
            # No provider exception, auth code, state or token in response.
            return FileResponse(
                STATIC / "mail-oauth-error.html",
                media_type="text/html", status_code=400,
            )
        return FileResponse(
            STATIC / "mail-oauth-complete.html", media_type="text/html"
        )

    @app.post("/api/v1/calendar/oauth/start")
    async def start_calendar_connect(request: Request):
        """Explicit same-origin owner click starts Google consent in browser."""
        from .calendar_google import CalendarGoogleError
        await action_payload(request, set())
        try:
            return calendar_oauth.start(store, oauth_loopback_host(request))
        except CalendarGoogleError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get("/api/v1/calendar/oauth/callback")
    def finish_calendar_connect(request: Request, background_tasks: BackgroundTasks):
        """Google redirect: one-use state, PKCE, separate Calendar credentials."""
        from .calendar_google import CalendarGoogleError
        params = request.query_params
        state = params.get("state")
        code = params.get("code")
        if (len(params.getlist("state")) != 1
                or len(params.getlist("code")) > 1
                or len(params.getlist("iss")) > 1
                or ("iss" in params and
                    params.get("iss") != "https://accounts.google.com")):
            return FileResponse(
                STATIC / "calendar-oauth-error.html",
                media_type="text/html", status_code=400,
            )
        try:
            calendar_oauth.finish(store, state, code, params.get("error"))
        except CalendarGoogleError:
            # No codes, state, credentials, exceptions or provider text in HTML.
            return FileResponse(
                STATIC / "calendar-oauth-error.html",
                media_type="text/html", status_code=400,
            )
        from .calendar_google import sync_authorized_account
        background_tasks.add_task(sync_authorized_account, store, "default")
        # Do not 303 directly to dashboard: Firefox may carry cross-site
        # Fetch Metadata through the redirect chain and reject the HTML.
        # Send an inert local document then navigate within the same origin.
        return FileResponse(
            STATIC / "calendar-oauth-complete.html", media_type="text/html"
        )


    @app.get("/api/v1/google-tasks/status")
    def local_google_tasks_status():
        from .google_tasks import status
        from .calendar_web_oauth import client_available
        return {"sync": status(store), "oauth_client_ready":client_available(store)}

    @app.get("/api/v1/google-tasks/cached")
    def local_google_tasks_cached():
        from .google_tasks import cached
        return cached(store)

    @app.post("/api/v1/google-tasks/oauth/start")
    async def start_google_tasks_oauth(request: Request):
        await action_payload(request, set())
        try:
            return tasks_oauth.start(store, oauth_loopback_host(request))
        except ValueError:
            raise HTTPException(409, "tasks_oauth_unavailable") from None

    @app.get("/api/v1/google-tasks/oauth/callback")
    def finish_google_tasks_oauth(request: Request, background_tasks: BackgroundTasks):
        params = request.query_params
        if (len(params.getlist("state")) != 1
                or len(params.getlist("code")) > 1
                or len(params.getlist("iss")) > 1
                or ("iss" in params and
                    params.get("iss") != "https://accounts.google.com")):
            return FileResponse(STATIC / "calendar-oauth-error.html",
                                media_type="text/html", status_code=400)
        try:
            tasks_oauth.finish(
                store, params.get("state"), params.get("code"),
                params.get("error"),
            )
        except ValueError:
            return FileResponse(STATIC / "calendar-oauth-error.html",
                                media_type="text/html", status_code=400)
        from .google_tasks import sync
        # Explicit initial callback is the ONLY background fetch added here.
        # Later updates use the operator CLI; dashboard GET is purely cached.
        background_tasks.add_task(sync, store)
        return FileResponse(STATIC / "tasks-oauth-complete.html",
                            media_type="text/html")

    @app.get("/api/v1/calendar/status")
    def local_calendar_status():
        """Cached sync status only; no provider calls or OAuth information."""
        from .calendar_google import configured_accounts, status
        from .calendar_web_oauth import client_available
        return {"accounts": [
            status(store, account) for account in configured_accounts(store)
        ], "reuse_gmail_oauth_client_available": client_available(store),
            "external_reads": False, "external_writes": False}

    @app.get("/api/v1/calendar/availability")
    def local_calendar_availability():
        """Known local busy blocks, not a free-slot guarantee."""
        from .calendar_core import CalendarCore
        return CalendarCore(store).availability()

    @app.get("/api/v1/calendar/plan")
    def local_unified_calendar_plan(days: int = Query(default=7, ge=1, le=7)):
        """Read cached calendar + confirmed tasks; no provider I/O or AI actions."""
        from .calendar_planning import unified_plan
        if days not in (1, 7):
            raise HTTPException(422, "invalid_unified_plan_window")
        return unified_plan(store, days=days)

    @app.post("/api/v1/calendar/day-plan/ai-suggest")
    async def local_ai_day_plan_suggestions(request: Request):
        """Explicit owner click only, localhost Ollama, no plan confirmation."""
        from .day_plan_ai import PlannerAIError, suggest
        payload = await action_payload(request, {"task_ids"})
        try:
            return suggest(store, payload["task_ids"])
        except PlannerAIError as error:
            code=str(error)
            # Never leak raw model/provider responses or private task titles.
            raise HTTPException(
                503 if code=="local_ai_unavailable" else 422,
                code if code in {
                    "local_ai_unavailable","invalid_ai_task_selection",
                    "ai_task_not_open","incomplete_task_source",
                    "invalid_local_ai_model","invalid_local_ai_estimates",
                    "local_ai_request_too_large","local_ai_response_too_large"
                } else "invalid_local_ai_estimates"
            ) from None

    @app.post("/api/v1/calendar/day-plan/preview")
    async def preview_local_day_plan(request: Request):
        """Explicit owner time estimates; no provider/LLM I/O or durable plan."""
        payload = await action_payload(
            request, {"date", "work_start", "work_end", "tasks"}
        )
        try:
            return day_plans.preview(payload)
        except (ValueError, TypeError):
            raise HTTPException(422, "invalid_local_day_plan") from None

    @app.post("/api/v1/calendar/day-plan/confirm")
    async def confirm_local_day_plan(request: Request):
        """Single-use owner confirmation saves private SQLite blocks ONLY."""
        payload = await action_payload(
            request, {"confirmation_token", "confirmed"}
        )
        try:
            return day_plans.confirm(
                payload["confirmation_token"], payload["confirmed"]
            )
        except (ValueError, TypeError):
            raise HTTPException(409, "local_day_plan_preview_expired_or_changed") from None

    @app.get("/api/v1/calendar/day-plan/saved")
    def read_local_saved_day_plans():
        """Private locally approved plan history, no Google write semantics."""
        return day_plans.saved()

    @app.post("/api/v1/tasks/create")
    async def local_task_create(request: Request):
        from .task_planner import TaskPlanner
        payload = await action_payload(
            request, {"title","notes","due","reminder_minutes"}
        )
        try:
            return TaskPlanner(store).create(
                payload["title"],payload["notes"],payload["due"],
                payload["reminder_minutes"]
            )
        except (ValueError,TypeError) as exc:
            raise HTTPException(422,str(exc)) from None

    @app.post("/api/v1/tasks/edit")
    async def local_task_edit(request: Request):
        from .task_planner import TaskPlanner
        payload = await action_payload(
            request, {"task_id","title","notes","due","reminder_minutes"}
        )
        try:
            return TaskPlanner(store).edit(
                payload["task_id"],payload["title"],payload["notes"],
                payload["due"],payload["reminder_minutes"]
            )
        except (ValueError,TypeError) as exc:
            raise HTTPException(422,str(exc)) from None

    @app.post("/api/v1/tasks/transition")
    async def local_task_transition(request: Request):
        from .task_planner import TaskPlanner
        payload = await action_payload(request,{"task_id","status"})
        try:
            return TaskPlanner(store).transition(
                payload["task_id"],payload["status"]
            )
        except (ValueError,TypeError) as exc:
            raise HTTPException(422,str(exc)) from None

    @app.get("/api/v1/summaries")
    def summaries(
        limit: int = Query(20, ge=1, le=100),
        cursor: str | None = Query(None, max_length=160),
    ):
        try:
            return store.list_summaries(limit, cursor)
        except InvalidCursor as exc:
            raise HTTPException(400, "invalid cursor") from exc

    @app.get("/api/v1/runs/{run_id}")
    def run(run_id: str):
        result = store.get_run(run_id)
        if result is None:
            raise HTTPException(404, "run not found")
        return {"schema_version": 1, "run": result}

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/app.js")
    def script():
        return FileResponse(STATIC / "app.js", media_type="text/javascript")

    @app.get("/day-plan-ai.js")
    def day_plan_ai_script():
        return FileResponse(STATIC / "day-plan-ai.js",
                            media_type="text/javascript")

    @app.get("/fullcalendar-standard.min.js")
    def local_fullcalendar_vendor():
        """Self-hosted MIT asset, explicitly installed by the owner."""
        path = STATIC / "vendor" / "fullcalendar" / "index.global.min.js"
        if not path.is_file():
            raise HTTPException(404, "fullcalendar_vendor_install_required")
        return FileResponse(path, media_type="text/javascript")

    @app.get("/fullcalendar-ui.js")
    def local_fullcalendar_ui():
        return FileResponse(STATIC / "fullcalendar-ui.js",
                            media_type="text/javascript")

    @app.get("/day-plan.js")
    def local_day_plan_script():
        """Self-hosted browser action UI; no paid or external scripts."""
        return FileResponse(STATIC / "day-plan.js", media_type="text/javascript")

    @app.get("/google-tasks-ui.js")
    def google_tasks_local_ui_script():
        return FileResponse(STATIC / "google-tasks-ui.js",
                            media_type="text/javascript")

    @app.get("/mail-oauth-return.js")
    def mail_oauth_return_script():
        return FileResponse(
            STATIC / "mail-oauth-return.js", media_type="text/javascript"
        )

    @app.get("/calendar-oauth-return.js")
    def calendar_oauth_return_script():
        return FileResponse(
            STATIC / "calendar-oauth-return.js", media_type="text/javascript"
        )

    @app.get("/style.css")
    def styles():
        return FileResponse(STATIC / "style.css", media_type="text/css")

    @app.get("/vanilla-calendar.min.js")
    def local_calendar_library():
        """Pinned MIT dependency, self-hosted on localhost."""
        return FileResponse(
            STATIC / "vendor" / "vanilla-calendar.min.js",
            media_type="text/javascript",
        )

    @app.get("/vanilla-calendar.min.css")
    def local_calendar_library_styles():
        return FileResponse(
            STATIC / "vendor" / "vanilla-calendar.min.css",
            media_type="text/css",
        )

    return app
