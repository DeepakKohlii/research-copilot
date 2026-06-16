"""Test fixtures: an isolated in-memory DB, a TestClient, and forced offline
mock providers so tests never make real LLM/search calls or touch prod data."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import ratelimit
from app.config import settings
from app.db.database import get_db
from app.db.models import Base
from app.main import app


@pytest.fixture(autouse=True)
def force_mock_providers(monkeypatch):
    """A developer's .env may carry real keys; pin every test to mock mode."""
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "search_provider", "mock")
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "tavily_api_key", None)
    monkeypatch.setattr(settings, "openai_base_url", "")


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    ratelimit.reset()
    ratelimit.rate_limit.limit = settings.rate_limit_per_minute
    yield TestClient(app)
    app.dependency_overrides.clear()
    ratelimit.reset()
