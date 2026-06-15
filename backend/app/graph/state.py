from __future__ import annotations

from typing import Any, TypedDict


class ResearchState(TypedDict, total=False):
    # inputs
    session_id: str
    company: str
    website: str
    objective: str

    # planner output
    plan: list[str]

    # research output
    raw_findings: list[dict[str, Any]]
    research_passes: int

    # analysis output
    analysis: dict[str, list[str]]

    # quality check output
    quality_score: float
    quality_notes: str

    # final output
    report: dict[str, Any]

    # bookkeeping
    current_node: str
    errors: list[dict[str, str]]
