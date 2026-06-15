from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from ..config import settings
from .models import Base

_connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def _ensure_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    from sqlalchemy import text

    wanted = {"website": "VARCHAR(500) DEFAULT ''"}
    with engine.begin() as conn:
        existing = {
            row[1] for row in conn.execute(text("PRAGMA table_info(sessions)"))
        }
        for col, ddl in wanted.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE sessions ADD COLUMN {col} {ddl}"))


def get_db() -> Iterator[OrmSession]:
    """FastAPI dependency: one DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
