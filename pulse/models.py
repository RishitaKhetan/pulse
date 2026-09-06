import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class FunnelRequest(BaseModel):
    steps: list[str]


class Experiment(BaseModel):
    name: str
    variants: list[str] = ["control", "treatment"]
    goal_event: str
    status: str = "running"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("name")
    @classmethod
    def name_is_slug(cls, v: str) -> str:
        if not re.match(r"^[\w\-]+$", v):
            raise ValueError("name must only contain letters, numbers, underscores, and hyphens")
        return v

    @field_validator("variants")
    @classmethod
    def at_least_two_variants(cls, v: list[str]) -> list[str]:
        if len(v) < 2:
            raise ValueError("must have at least 2 variants")
        return v


class Event(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str | None = None
    session_id: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
