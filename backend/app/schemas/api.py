from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import BaseModel, Field, PlainSerializer


def _as_utc_iso(dt: datetime) -> str:
    # Timestamps are stored as naive UTC; tag them UTC on the way out so the
    # browser parses them as an absolute instant and renders in the user's local
    # zone (e.g. IST) — instead of mistaking UTC for local time.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


# datetime that always serialises as an explicit-UTC ISO 8601 string.
UtcDatetime = Annotated[datetime, PlainSerializer(_as_utc_iso, return_type=str)]


class CreateSessionRequest(BaseModel):
    company: str = Field(min_length=1, max_length=255)
    website: str = Field(default="", max_length=500)
    objective: str = Field(default="", max_length=2000)


class SessionOut(BaseModel):
    id: str
    company: str
    website: str
    objective: str
    status: str
    current_node: str | None
    report: dict[str, Any] | None
    error: str | None
    created_at: UtcDatetime
    updated_at: UtcDatetime

    class Config:
        from_attributes = True


class SessionSummary(BaseModel):
    id: str
    company: str
    website: str
    objective: str
    status: str
    current_node: str | None
    created_at: UtcDatetime

    class Config:
        from_attributes = True


class EventOut(BaseModel):
    id: int
    type: str
    node: str | None
    data: dict[str, Any]
    created_at: UtcDatetime

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: UtcDatetime

    class Config:
        from_attributes = True
