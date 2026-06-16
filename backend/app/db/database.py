from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from ..config import settings
from .models import Base

# Some hosts (Render/Heroku) hand out "postgres://"; SQLAlchemy wants
# "postgresql://". Normalise so the same DATABASE_URL works either way.
_db_url = settings.database_url
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)

_is_sqlite = _db_url.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

# pool_pre_ping avoids stale-connection errors on managed Postgres that drops
# idle connections; harmless for SQLite.
engine = create_engine(
    _db_url, connect_args=_connect_args, pool_pre_ping=True, future=True
)
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
