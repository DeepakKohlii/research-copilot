from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class ResearchState(TypedDict, total=False):
    # inputs
    session_id: str
    company: str
    website: str
    objective: str

    # planner output
    plan: list[dict[str, Any]]

    # research output — written by parallel `research_section` branches, so it
    # needs an `operator.add` reducer to merge their results instead of letting
    # concurrent writes overwrite each other. Each finding is tagged with its
    # pass number; downstream nodes use only the current pass's findings.
    raw_findings: Annotated[list[dict[str, Any]], operator.add]
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
