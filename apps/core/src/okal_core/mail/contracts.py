"""Explicit bounds and validated model output; never executable model tools."""

import re
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MailError(ValueError):
    """Safe operator-facing error code (no provider response/body/secret)."""


def address(value: str) -> str:
    if (
        not isinstance(value, str)
        or not re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}",
            value,
        )
        or len(value) > 254
    ):
        raise MailError("single_plain_email_address_required")
    return value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Config(Strict):
    account: str
    model: str = Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9_./:-]+$")
    model_digest: str = Field(pattern=r"^(sha256:)?[a-f0-9]{64}$")
    local_only_confirmed: bool = False
    timezone: str = "Africa/Cairo"
    max_messages: int = Field(default=30, ge=1, le=100)
    retention_days: int = Field(default=30, ge=1, le=365)
    daily_at: str | None = None
    send_enabled: bool = False
    sync_enabled: bool = False

    @field_validator("account")
    @classmethod
    def valid_account(cls, v):
        return address(v)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, v):
        ZoneInfo(v)
        return v

    @field_validator("daily_at")
    @classmethod
    def valid_time(cls, v):
        if v is not None and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("HH:MM required")
        return v


class Message(Strict):
    id: str = Field(pattern=r"^[a-fA-F0-9]{1,64}$")
    thread_id: str = Field(pattern=r"^[a-fA-F0-9]{1,64}$")
    received_ms: int = Field(ge=0)
    sender: str = Field(max_length=1000)
    recipient: str = Field(default="", max_length=1000)
    cc: str = Field(default="", max_length=1000)
    bcc: str = Field(default="", max_length=1000)
    reply_to: str = Field(max_length=1000)
    subject: str = Field(max_length=500)
    body: str = Field(max_length=8000)
    rfc_id: str = Field(max_length=500)
    labels: list[str]
    truncated: bool = False
    attachment_count: int = Field(default=0, ge=0)


class Insight(Strict):
    source_id: str
    category: Literal["action", "information", "low_priority"]
    summary: str = Field(min_length=1, max_length=240)
    suggested_action: str = Field(max_length=160)


class Reply(Strict):
    body: str = Field(min_length=1, max_length=8000)


class Draft(Strict):
    recipient: str
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=8000)
    thread_id: str | None = None
    in_reply_to: str | None = None

    @field_validator("recipient")
    @classmethod
    def valid_recipient(cls, v):
        return address(v)

    @field_validator("subject", "in_reply_to")
    @classmethod
    def safe_header(cls, v):
        if v is not None and (
            any(ord(c) < 32 or ord(c) == 127 for c in v) or len(v) > 500
        ):
            raise ValueError("invalid header")
        return v

    @field_validator("thread_id")
    @classmethod
    def safe_thread(cls, v):
        if v is not None and not re.fullmatch(r"[a-fA-F0-9]{1,64}", v):
            raise ValueError("invalid thread")
        return v
