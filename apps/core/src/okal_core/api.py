"""Loopback-only, read-only API. No model, scheduler or provider is loaded."""

import ipaddress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from .store import InvalidCursor, Store

STATIC = Path(__file__).parent / "static"
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)


def create_app(store: Store, port: int = 8766) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
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
        ):
            response = JSONResponse(
                {"detail": "local same-origin access required"}, status_code=403
            )
        elif (
            request.url.path.startswith("/api/")
            and request.url.path != "/api/v1/health"
            and (
                len(request.headers.getlist("authorization")) != 1
                or not request.headers.get("authorization", "").startswith("Bearer ")
                or not store.authenticate(request.headers.get("authorization", "")[7:])
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

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "schema_version": 1}

    @app.get("/api/v1/capabilities")
    def capabilities():
        return {
            "schema_version": 1,
            "mode": "local-read-only",
            "permissions": ["inbox:read"],
            "external_writes": False,
            "providers": [],
            "scheduler": False,
            "remote_pairing": False,
            "voice": False,
        }

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
