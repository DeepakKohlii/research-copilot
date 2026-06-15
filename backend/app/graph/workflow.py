"""Graph assembly. Wires the nodes into the Planner -> Research -> Analysis ->
Quality check -> Report shape, with a conditional edge back to Research.

The checkpointer is a factory so the durability tier is a config choice:
MemorySaver for dev, and a persistent saver (SqliteSaver / PostgresSaver from
langgraph-checkpoint-*) in production for true cross-restart resume. App-level
recoverability (event replay) does not depend on this — see runner.py.
"""
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
    g.add_node("research", nodes.research)
    g.add_node("analysis", nodes.analysis)
    g.add_node("quality_check", nodes.quality_check)
    g.add_node("report", nodes.report)

    g.set_entry_point("planner")
    g.add_edge("planner", "research")
    g.add_edge("research", "analysis")
    g.add_edge("analysis", "quality_check")
    g.add_conditional_edges(
        "quality_check",
        nodes.route_after_quality,
        {"research": "research", "report": "report"},
    )
    g.add_edge("report", END)

    return g.compile(checkpointer=checkpointer or build_checkpointer())
