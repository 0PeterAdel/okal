"""Versioned contracts at the voice-to-kernel boundary."""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class ContractError(ValueError):
    """A provider returned data outside the governed contract."""


class VoicePhase(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    ROUTING = "routing"
    SPEAKING = "speaking"
    BLOCKED = "blocked"
    ERROR = "error"


class RouteKind(StrEnum):
    CONVERSATION = "conversation"
    TASK = "task"
    DICTATION = "dictation"
    CLARIFY = "clarify"
    BLOCKED = "blocked"


ALLOWED_LANGUAGES = frozenset({"ar", "en", "mixed", "unknown"})
ROUTE_KEYS = frozenset({"route", "language", "summary", "reply", "confidence"})


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """The router may classify and answer; it may never emit executable calls."""

    route: RouteKind
    language: str
    summary: str
    reply: str
    confidence: float

    @classmethod
    def from_json(cls, raw: str) -> "RouteDecision":
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ContractError("router output is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ContractError("router output must be a JSON object")
        keys = frozenset(payload)
        if keys != ROUTE_KEYS:
            missing = sorted(ROUTE_KEYS - keys)
            extra = sorted(keys - ROUTE_KEYS)
            raise ContractError(f"router keys differ; missing={missing}, extra={extra}")
        try:
            route = RouteKind(payload["route"])
        except (ValueError, TypeError) as exc:
            raise ContractError("router selected an unknown route") from exc
        language = payload["language"]
        if language not in ALLOWED_LANGUAGES:
            raise ContractError("router selected an unknown language")
        summary = _bounded_text(payload["summary"], "summary", 600)
        reply = _bounded_text(payload["reply"], "reply", 800, allow_empty=True)
        confidence = payload["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ContractError("confidence must be numeric")
        confidence = float(confidence)
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ContractError("confidence must be between 0 and 1")
        if route is RouteKind.CONVERSATION and not reply:
            raise ContractError("conversation route requires a reply")
        return cls(route, language, summary, reply, confidence)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class VoiceSnapshot:
    schema_version: str
    session_id: str
    phase: VoicePhase
    text: str
    language: str
    route: str
    updated_at: float

    @classmethod
    def new(
        cls,
        phase: VoicePhase,
        *,
        session_id: str = "",
        text: str = "",
        language: str = "unknown",
        route: str = "",
        now: float | None = None,
    ) -> "VoiceSnapshot":
        return cls(
            "okal.voice.state.v1",
            session_id,
            phase,
            _bounded_text(text, "text", 800, allow_empty=True),
            language if language in ALLOWED_LANGUAGES else "unknown",
            route,
            time.time() if now is None else now,
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "VoiceSnapshot":
        if payload.get("schema_version") != "okal.voice.state.v1":
            raise ContractError("unsupported voice state schema")
        try:
            phase = VoicePhase(payload["phase"])
            updated_at = float(payload["updated_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError("invalid voice state") from exc
        return cls.new(
            phase,
            session_id=str(payload.get("session_id", "")),
            text=str(payload.get("text", "")),
            language=str(payload.get("language", "unknown")),
            route=str(payload.get("route", "")),
            now=updated_at,
        )

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["phase"] = self.phase.value
        return data

    def is_fresh(self, *, now: float | None = None, max_age: float = 900) -> bool:
        return (time.time() if now is None else now) - self.updated_at <= max_age


def _bounded_text(value: Any, name: str, limit: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{name} must be text")
    value = " ".join(value.strip().split())
    if not value and not allow_empty:
        raise ContractError(f"{name} cannot be empty")
    if len(value) > limit:
        raise ContractError(f"{name} exceeds {limit} characters")
    return value
