"""End-to-end tests of the LangGraph workflow with mock providers."""
from __future__ import annotations

import asyncio

from app.config import settings
from app.graph.nodes import CopilotNodes
from app.graph.workflow import build_graph
from app.services.llm import MockLLM
from app.services.search import MockSearch

REQUIRED_TITLES = [
    "Company overview",
    "Products & services",
    "Target customers",
    "Business signals",
    "Risks & challenges",
]


def _run(initial: dict) -> dict:
    nodes = CopilotNodes(MockLLM(), MockSearch(), settings)
    graph = build_graph(nodes=nodes)

    async def go():
        config = {"configurable": {"thread_id": initial["session_id"]}}
        seen: list[str] = []
        async for update in graph.astream(initial, config, stream_mode="updates"):
            seen.extend(update.keys())
        state = graph.get_state(config).values
        state["_seen_nodes"] = seen
        return state

    return asyncio.run(go())


def _initial(**kw):
    base = {
        "session_id": "t1",
        "company": "Stripe",
        "website": "stripe.com",
        "objective": "Sell analytics",
        "raw_findings": [],
        "errors": [],
    }
    base.update(kw)
    return base


def test_report_contains_all_required_sections():
    state = _run(_initial())
    report = state["report"]
    assert [s["title"] for s in report["sections"]] == REQUIRED_TITLES
    prep = report["meeting_prep"]
    assert prep["discovery_questions"]
    assert prep["outreach_strategy"]
    assert prep["unknowns"]
    assert "sources" in report
    assert "executive_summary" in report


def test_research_fans_out_one_branch_per_section():
    state = _run(_initial())
    # Mock data is thin, so the quality loop runs >= 1 pass of 5 parallel sections.
    passes = state["research_passes"]
    assert passes >= 1
    assert state["_seen_nodes"].count("research_section") == 5 * passes


def test_quality_loop_triggers_on_thin_data():
    # MockSearch returns 1 result/section on pass 1 → low coverage → loop back.
    state = _run(_initial())
    assert state["research_passes"] >= 2
    assert "prep_research" in state["_seen_nodes"]
