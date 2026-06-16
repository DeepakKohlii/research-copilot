"""API-level tests via TestClient (DB and providers are mocked in conftest)."""
from __future__ import annotations

from app import ratelimit
from app.db.repository import Repository


def test_create_and_get_session(client):
    r = client.post(
        "/api/sessions",
        json={"company": "Stripe", "website": "stripe.com", "objective": "Sell"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["company"] == "Stripe"
    assert data["website"] == "stripe.com"
    assert data["status"] == "queued"

    got = client.get(f"/api/sessions/{data['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == data["id"]
    # timestamps are serialised with an explicit UTC offset
    assert got.json()["created_at"].endswith("+00:00")


def test_create_requires_company(client):
    assert client.post("/api/sessions", json={"objective": "x"}).status_code == 422


def test_get_unknown_session_404(client):
    assert client.get("/api/sessions/nope").status_code == 404


def test_list_sessions(client):
    client.post("/api/sessions", json={"company": "A"})
    client.post("/api/sessions", json={"company": "B"})
    r = client.get("/api/sessions")
    assert r.status_code == 200
    assert len(r.json()) >= 2


def test_chat_blocked_until_report_ready(client):
    sid = client.post("/api/sessions", json={"company": "A"}).json()["id"]
    r = client.post(f"/api/sessions/{sid}/chat", json={"message": "hi"})
    assert r.status_code == 409  # briefing not ready


def test_chat_answers_when_ready(client, session_factory):
    sid = client.post("/api/sessions", json={"company": "Stripe"}).json()["id"]
    db = session_factory()
    Repository(db).update_session(
        sid,
        status="completed",
        report={
            "company": "Stripe",
            "executive_summary": "Stripe builds payments infrastructure.",
            "sections": [],
        },
    )
    db.close()

    r = client.post(f"/api/sessions/{sid}/chat", json={"message": "What do they do?"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "assistant"
    assert body["content"]


def test_rate_limit_returns_429(client):
    ratelimit.reset()
    ratelimit.rate_limit.limit = 3
    try:
        codes = [
            client.post("/api/sessions", json={"company": "X"}).status_code
            for _ in range(5)
        ]
    finally:
        ratelimit.rate_limit.limit = 20
        ratelimit.reset()
    assert codes[:3] == [201, 201, 201]
    assert codes[-1] == 429


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
