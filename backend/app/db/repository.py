"""Repository pattern: the only place that talks to the ORM. The rest of the
app depends on these methods, not on SQLAlchemy, so the storage backend can be
swapped without touching API or workflow code."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .models import ChatMessage, Event, Session


class Repository:
    def __init__(self, db: OrmSession):
        self.db = db

    # ---- sessions -------------------------------------------------------
    def create_session(self, company: str, objective: str) -> Session:
        obj = Session(
            id=str(uuid.uuid4()),
            company=company,
            objective=objective or "",
            status="queued",
        )
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def get_session(self, session_id: str) -> Session | None:
        return self.db.get(Session, session_id)

    def list_sessions(self, limit: int = 50) -> list[Session]:
        stmt = select(Session).order_by(Session.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt))

    def update_session(self, session_id: str, **fields) -> Session | None:
        obj = self.db.get(Session, session_id)
        if obj is None:
            return None
        for key, value in fields.items():
            setattr(obj, key, value)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    # ---- events ---------------------------------------------------------
    def add_event(
        self, session_id: str, type: str, node: str | None = None, data: dict | None = None
    ) -> Event:
        ev = Event(session_id=session_id, type=type, node=node, data=data or {})
        self.db.add(ev)
        self.db.commit()
        self.db.refresh(ev)
        return ev

    def list_events(self, session_id: str, after_id: int = 0) -> list[Event]:
        stmt = (
            select(Event)
            .where(Event.session_id == session_id, Event.id > after_id)
            .order_by(Event.id.asc())
        )
        return list(self.db.scalars(stmt))

    # ---- chat -----------------------------------------------------------
    def add_chat(self, session_id: str, role: str, content: str) -> ChatMessage:
        msg = ChatMessage(session_id=session_id, role=role, content=content)
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def list_chat(self, session_id: str) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id.asc())
        )
        return list(self.db.scalars(stmt))
