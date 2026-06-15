"""ORM models. Three tables carry all app domain state:

- Session: one research run (the unit the UI lists and opens).
- Event:   an append-only log of node-level progress for a session. This is
           the source of truth the SSE stream replays from, and what gives the
           app recoverability across reconnects/restarts.
- ChatMessage: follow-up Q&A turns over a finished briefing.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company: Mapped[str] = mapped_column(String(255))
    objective: Mapped[str] = mapped_column(Text, default="")
    # queued | running | completed | failed
    status: Mapped[str] = mapped_column(String(20), default="queued")
    current_node: Mapped[str | None] = mapped_column(String(40), nullable=True)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    events: Mapped[list["Event"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Event(Base):
    __tablename__ = "events"

    # Autoincrement id doubles as a monotonic per-stream sequence number,
    # used to de-duplicate between SSE replay and live tail.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    type: Mapped[str] = mapped_column(String(40))  # node_started, node_completed, ...
    node: Mapped[str | None] = mapped_column(String(40), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    session: Mapped[Session] = relationship(back_populates="events")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
