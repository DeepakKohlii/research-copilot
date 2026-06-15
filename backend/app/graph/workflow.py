from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from ..config import settings
from ..services.llm import get_llm
from ..services.search import get_search
from .nodes import CopilotNodes
from .state import ResearchState


def build_checkpointer():
    # Dev default. For prod, return a persistent saver, e.g.:
    #   from langgraph.checkpoint.sqlite import SqliteSaver
    #   return SqliteSaver.from_conn_string("checkpoints.db")
    return MemorySaver()


def build_graph(checkpointer=None, nodes: CopilotNodes | None = None):
    nodes = nodes or CopilotNodes(get_llm(), get_search(), settings)
    g = StateGraph(ResearchState)

    g.add_node("planner", nodes.planner)
    # Research is a map-reduce: prep_research bumps the pass, then dispatch fans
    # out one parallel research_section per required section; their results merge
    # back into raw_findings (reducer) before analysis runs.
    g.add_node("prep_research", nodes.prep_research)
    g.add_node("research_section", nodes.research_section)
    g.add_node("analysis", nodes.analysis)
    g.add_node("quality_check", nodes.quality_check)
    g.add_node("report", nodes.report)

    g.set_entry_point("planner")
    g.add_edge("planner", "prep_research")
    g.add_conditional_edges(
        "prep_research", nodes.dispatch_research, ["research_section"]
    )
    g.add_edge("research_section", "analysis")
    g.add_edge("analysis", "quality_check")
    g.add_conditional_edges(
        "quality_check",
        nodes.route_after_quality,
        {"prep_research": "prep_research", "report": "report"},
    )
    g.add_edge("report", END)

    return g.compile(checkpointer=checkpointer or build_checkpointer())
