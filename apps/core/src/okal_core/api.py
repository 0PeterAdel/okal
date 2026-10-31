"""Loopback-only read API. Mail operator actions are CLI-only, never token tools."""

import ipaddress
from pathlib import Path
from urllib.parse import quote
import json

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from .store import InvalidCursor, Store

STATIC = Path(__file__).parent / "static"
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)


def create_app(store: Store, port: int = 8766, lifespan=None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

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
            or (origin is not None and origin != f"http://{host}")
            or request.headers.get("sec-fetch-site") == "cross-site"
            or (
                request.url.path == "/api/v1/session"
                and request.method in {"POST", "DELETE"}
                and (
                    origin != f"http://{host}"
                    or request.headers.get("sec-fetch-site", "same-origin")
                    not in {"same-origin", "none"}
                )
            )
        ):
            response = JSONResponse(
                {"detail": "local same-origin access required"}, status_code=403
            )
        elif (
            request.url.path.startswith("/api/")
            and request.url.path != "/api/v1/health"
            and not (
                request.url.path == "/api/v1/session"
                and request.method == "POST"
            )
            and not (
                store.authenticate_browser_session(request.cookies.get("okal_session", ""))
                or (
                    len(request.headers.getlist("authorization")) == 1
                    and request.headers.get("authorization", "").startswith("Bearer ")
                    and store.authenticate(request.headers.get("authorization", "")[7:])
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
                else set()
            )
            for k in request.query_params
        ):
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
            "permissions": ["inbox:read"],
            "external_writes": False,
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
            items.append({
                "id": m["id"], "subject": m["subject"], "sender": m["sender"],
                "received_ms": m["received_ms"], "labels": m["labels"],
                "category": i["category"], "summary": i["summary"],
                "suggested_action": i["suggested_action"],
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

    @app.get("/style.css")
    def styles():
        return FileResponse(STATIC / "style.css", media_type="text/css")

    return app
