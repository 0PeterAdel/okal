"""Owner-browser-only chat endpoints. Read-device credentials grant no access."""
import asyncio
import json
import sqlite3
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .intelligence import Intelligence, Missing, respond
from .store import Conflict

PREFIX = '/api/v1/chat/'
PATHS = {PREFIX + name for name in (
    'conversations', 'create', 'get', 'delete', 'turn', 'memories',
    'memory-save', 'memory-delete', 'settings', 'memory-health', 'memory-retry',
    'memory-backfill', 'memory-rebuild', 'memory-versions', 'memory-browse', 'memory-search',
    'projects', 'project-save', 'project-associate', 'conversation-state',
    'vault-preview', 'vault-import', 'vault-project-preview', 'vault-project-import')}


class Payload(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')


class ListConversations(Payload):
    before: str | None = None


class Create(Payload):
    title: str = Field(default='New conversation', max_length=100)


class Conversation(Payload):
    conversation_id: str


class Get(Conversation):
    before: int | None = None


class Turn(Conversation):
    request_id: str
    message: str = Field(min_length=1, max_length=900)
    retry: bool = False


class Memories(Payload):
    conversation_id: str | None = None
    project_id: str | None = None


class SaveMemory(Memories):
    key: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=600)
    kind: Literal['semantic', 'episodic', 'task', 'instruction', 'decision', 'goal', 'constraint', 'lesson'] = 'semantic'
    source_turn: str | None = None
    revision: int = Field(default=0, ge=0)
    days: int = Field(default=0, ge=0, le=365)


class Forget(Payload):
    memory_id: str


class Settings(Payload):
    days: int | None = Field(default=None, ge=0, le=365)


class ProjectSave(Payload):
    name: str = Field(min_length=1,max_length=100)
    description: str = Field(default='',max_length=600)
    project_id: str | None = None
    revision: int = Field(default=0,ge=0)


class Association(Conversation):
    project_id: str | None = None
    revision: int = Field(default=0,ge=0)


class MemoryBrowse(Payload):
    status: Literal['current','superseded','deleted','inferred','unverified'] = 'current'
    offset: int = Field(default=0,ge=0,le=1_000_000)


class Archive(Memories):
    query: str = Field(min_length=1,max_length=300)
    before: int | None = Field(default=None,ge=1)


class VaultImport(Forget):
    revision: int = Field(ge=1)


class ProjectReference(Payload):
    project_id: str


class ProjectImport(ProjectReference):
    revision: int = Field(ge=1)


def register(app, store, authorized):
    state = Intelligence(store)
    from .cognitive.retrieval import Retrieval
    from .cognitive.vault import Vault
    routes = {
        'conversations': (ListConversations, state.conversations),
        'create': (Create, state.create),
        'get': (Get, state.get),
        'delete': (Conversation, state.delete),
        'turn': (Turn, lambda **kw: respond(store, **kw)),
        'memories': (Memories, state.memories),
        'memory-save': (SaveMemory, state.save_memory),
        'memory-delete': (Forget, state.forget),
        'settings': (Settings, state.settings),
        'memory-health': (Payload, state.cognitive.health),
        'memory-retry': (Payload, state.cognitive.retry_failed),
        'memory-backfill': (Payload, state.cognitive.backfill),
        'memory-rebuild': (Payload, state.cognitive.request_rebuild),
        'memory-versions': (Forget, state.cognitive.versions),
        'memory-browse': (MemoryBrowse, state.cognitive.browse),
        'memory-search': (Archive, Retrieval(state.cognitive).archive),
        'projects': (Payload, state.cognitive.projects),
        'project-save': (ProjectSave, state.cognitive.save_project),
        'project-associate': (Association, state.cognitive.associate),
        'conversation-state': (Conversation, state.cognitive.conversation_state),
        'vault-preview': (Forget, lambda **kw: Vault(state.cognitive).preview(**kw)),
        'vault-import': (VaultImport, lambda **kw: Vault(state.cognitive).import_revision(**kw)),
        'vault-project-preview': (ProjectReference, lambda **kw: Vault(state.cognitive).preview_project(**kw)),
        'vault-project-import': (ProjectImport, lambda **kw: Vault(state.cognitive).import_project(**kw)),
    }

    def endpoint(schema, operation):
        async def handle(request: Request):
            if not authorized(request):
                raise HTTPException(403, 'owner_browser_session_required')
            # Stream with a cap; do not allocate an unbounded request body.
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 6000:
                    raise HTTPException(413, 'chat_request_too_large')
            try:
                payload = schema.model_validate(json.loads(body))
                return await asyncio.to_thread(operation, **payload.model_dump())
            except Missing:
                raise HTTPException(404, 'conversation_not_found') from None
            except Conflict as exc:
                raise HTTPException(409, str(exc)) from None
            except sqlite3.OperationalError:
                raise HTTPException(503, 'private_state_busy_retry') from None
            except OSError:
                raise HTTPException(503, 'private_memory_projection_unavailable') from None
            except (ValueError, TypeError):
                # Do not include validation input or exception strings: they
                # may contain the very secret that the validator rejected.
                raise HTTPException(422, 'invalid_or_sensitive_chat_input') from None
        return handle

    for name, (schema, operation) in routes.items():
        app.add_api_route(PREFIX + name, endpoint(schema, operation), methods=['POST'])
