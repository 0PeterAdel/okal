"""Actions and grants are owner-browser-only; bearer read scopes never suffice."""

import asyncio
import json

from fastapi import Request, HTTPException
from pydantic import Field

from ..store import Conflict
from .contracts import Strict, Plan, Denied
from .engine import Engine

PATHS = {
    "/api/v1/actions/" + name
    for name in (
        "capabilities",
        "policy",
        "propose",
        "get",
        "history",
        "execute",
        "cancel",
        "recover",
        "resume",
    )
}


class Empty(Strict):
    pass


class Configure(Strict):
    policy: dict
    revision: int


class Propose(Strict):
    conversation_id: str
    request_id: str
    instruction: str = Field(min_length=1, max_length=900)
    plan: Plan | None = None


class Reference(Strict):
    run_id: str


class Execute(Reference):
    approval_digest: str | None = None


class History(Strict):
    conversation_id: str


def register(app, store, authorized):
    engine = Engine(store)
    routes = {
        "capabilities": (Empty, engine.capabilities),
        "policy": (Configure, engine.configure),
        "propose": (Propose, engine.propose),
        "get": (Reference, engine.get),
        "history": (History, engine.history),
        "execute": (Execute, engine.start),
        "cancel": (Reference, engine.cancel),
        "recover": (Execute, engine.recover),
        "resume": (Execute, engine.resume),
    }

    def endpoint(schema, operation):
        async def handle(request: Request):
            if not authorized(request):
                raise HTTPException(403, "owner_browser_session_required")
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 100000:
                    raise HTTPException(413, "action_payload_limit")
            try:
                payload = schema.model_validate(json.loads(body))
                # Keep nested Plan typed; model_dump would erase its contract.
                arguments = {
                    name: getattr(payload, name) for name in type(payload).model_fields
                }
                return await asyncio.to_thread(operation, **arguments)
            except Denied as exc:
                raise HTTPException(403, str(exc)) from None
            except Conflict as exc:
                raise HTTPException(409, str(exc)) from None
            except (ValueError, TypeError, OSError):
                raise HTTPException(422, "action_invalid_or_unavailable") from None

        return handle

    for name, (schema, operation) in routes.items():
        app.add_api_route(
            "/api/v1/actions/" + name, endpoint(schema, operation), methods=["POST"]
        )
    app.state.computer = engine
