"""API request/response models — the contract the React frontend codes against."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    company: str = Field(min_length=1, max_length=255)
    objective: str = Field(default="", max_length=2000)


class SessionOut(BaseModel):
    id: str
    company: str
    objective: str
    status: str
    current_node: str | None
    report: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SessionSummary(BaseModel):
    id: str
    company: str
    status: str
    current_node: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class EventOut(BaseModel):
    id: int
    type: str
    node: str | None
    data: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True
