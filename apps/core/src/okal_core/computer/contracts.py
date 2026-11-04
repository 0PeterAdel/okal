"""Versioned action contracts; no executable shell or dynamic tool loading."""

from dataclasses import dataclass
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Grant(Strict):
    root: str = Field(min_length=1, max_length=1024)
    write: bool = False


class Command(Strict):
    argv: list[str] = Field(min_length=1, max_length=20)
    description: str = Field(min_length=1, max_length=180)


class Policy(Strict):
    mode: Literal["read_only", "assisted", "autonomous"] = "read_only"
    tools: list[str] = Field(default_factory=list, max_length=40)
    roots: list[Grant] = Field(default_factory=list, max_length=20)
    browser_origins: list[str] = Field(default_factory=list, max_length=20)
    commands: dict[str, Command] = Field(default_factory=dict, max_length=20)
    accounts: list[str] = Field(default_factory=list, max_length=10)
    applications: list[str] = Field(default_factory=list, max_length=20)


class Step(Strict):
    tool: str = Field(min_length=1, max_length=50)
    arguments: dict = Field(default_factory=dict)


class Plan(Strict):
    understanding: str = Field(min_length=1, max_length=500)
    steps: list[Step] = Field(min_length=1, max_length=10)


class Result(Strict):
    verified: bool
    summary: str = Field(max_length=1000)
    evidence: dict = Field(default_factory=dict)
    changes: list[dict] = Field(default_factory=list, max_length=200)
    limited: bool = False
    recovery: list[dict] = Field(default_factory=list, max_length=200)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: type[Strict]
    risk: Literal["read", "local_write", "consequential"]
    handler: object
    preview: object
    timeout: int = 30
    recovery: str = "No automatic rollback; inspect the receipt."

    def manifest(self):
        return dict(
            name=self.name,
            description=self.description,
            risk=self.risk,
            input_schema=self.schema.model_json_schema(),
            output_schema=Result.model_json_schema(),
            permission=self.name,
            timeout_seconds=self.timeout,
            preconditions="Owner-granted tool/scope, current policy revision, unexpired exact plan, unchanged preview resources.",
            resource_limits={
                "max_file_bytes": 8388608,
                "max_plan_steps": 10,
                "max_directory_entries": 200,
                "max_browser_requests": 80,
                "max_subprocess_output_bytes": 131072,
            },
            cancellation="Cooperative; checked at bounded I/O boundaries. Started writes are never blindly retried.",
            verification="Observed postconditions required for a successful receipt.",
            recovery=self.recovery,
        )


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


class Denied(ValueError):
    pass


class Cancelled(ValueError):
    pass
