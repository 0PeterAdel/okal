"""Bounded persisted input; private account references never enter responses."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    workflow: Literal["mail", "planning", "social", "freelance", "demo"]
    account_ref: str = Field(min_length=1, max_length=100)
    occurrence: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=12000)
    data_kind: Literal["fixture", "live"]
