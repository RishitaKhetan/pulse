from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class FunnelRequest(BaseModel):
    steps: list[str]


class Event(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str | None = None
    session_id: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
