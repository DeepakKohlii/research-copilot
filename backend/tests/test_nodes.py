"""Unit tests for the pure node helpers (no LLM/search needed)."""
from __future__ import annotations

from app.config import settings
from app.graph.nodes import RESEARCH_SECTIONS, CopilotNodes


def test_domain_extraction():
    assert CopilotNodes._domain("https://www.stripe.com/about") == "stripe.com"
    assert CopilotNodes._domain("Acme.com/pricing") == "acme.com"
    assert CopilotNodes._domain("") == ""


def test_parse_json_object_tolerates_fences_and_prose():
    assert CopilotNodes._parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert CopilotNodes._parse_json_object('Sure: {"a": 1} done') == {"a": 1}
    assert CopilotNodes._parse_json_object("not json at all") is None
    assert CopilotNodes._parse_json_object("") is None


def test_bullets_from_snippets_skips_empty_and_caps():
    results = [
        {"snippet": "one"},
        {"snippet": "   "},
        {"snippet": "two"},
        {"snippet": "three"},
        {"snippet": "four"},
    ]
    bullets = CopilotNodes._bullets_from_snippets(results)
    assert bullets == ["one", "two", "three"]  # empties skipped, capped at 3


def test_planner_emits_required_sections():
    nodes = CopilotNodes(None, None, settings)  # planner needs no providers
    plan = nodes.planner({"session_id": "s", "company": "Stripe"})["plan"]
    assert [p["key"] for p in plan] == [s["key"] for s in RESEARCH_SECTIONS]
    assert len(plan) == 5
