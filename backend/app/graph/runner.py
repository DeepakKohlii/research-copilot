from __future__ import annotations

import asyncio

from ..db.database import SessionLocal
from ..db.repository import Repository
from ..events import bus
from .workflow import build_graph
from ..logging_conf import get_logger

log = get_logger("graph.runner")

# One compiled graph per process. Thread/session isolation is handled by the
# checkpointer via a per-session thread_id in the run config.
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def _emit(repo: Repository, session_id: str, type: str, node: str | None, data: dict):
    ev = repo.add_event(session_id, type=type, node=node, data=data)
    await bus.publish(
        session_id,
        {"id": ev.id, "type": type, "node": node, "data": data},
    )


async def run_session(session_id: str) -> None:
    """Entry point spawned as a background task by the run API."""
    db = SessionLocal()
    repo = Repository(db)
    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}

    session = repo.get_session(session_id)
    if session is None:
        log.warning("run_session: unknown session %s", session_id)
        db.close()
        return

    repo.update_session(session_id, status="running")
    await _emit(repo, session_id, "run_started", None, {"company": session.company})

    initial: dict = {
        "session_id": session_id,
        "company": session.company,
        "website": session.website or "",
        "objective": session.objective,
        "errors": [],
    }

    try:
        async for update in graph.astream(initial, config, stream_mode="updates"):
            # `updates` yields {node_name: partial_state} after each node runs.
            for node_name, partial in update.items():
                repo.update_session(session_id, current_node=node_name)
                snapshot = _summarise(node_name, partial)
                await _emit(repo, session_id, "node_completed", node_name, snapshot)

        final_state = graph.get_state(config).values
        report = final_state.get("report")
        repo.update_session(
            session_id, status="completed", current_node="report", report=report
        )
        await _emit(repo, session_id, "run_completed", None, {"confidence": report.get("confidence") if report else None})
        log.info("[%s] run completed", session_id)

    except Exception as exc:  # noqa: BLE001 - capture and surface to the UI
        log.exception("[%s] run failed", session_id)
        repo.update_session(session_id, status="failed", error=str(exc))
        await _emit(repo, session_id, "run_failed", None, {"error": str(exc)})
    finally:
        db.close()


def _summarise(node: str, partial: dict) -> dict:
    """Compact, UI-friendly snapshot of a node's output for the progress feed."""
    if node == "planner":
        return {"plan": partial.get("plan", [])}
    if node == "research":
        findings = partial.get("raw_findings", [])
        return {
            "pass": partial.get("research_passes"),
            "angles": len(findings),
            "total_findings": sum(len(f["results"]) for f in findings),
        }
    if node == "analysis":
        return {"angles_analysed": len(partial.get("analysis", {}))}
    if node == "quality_check":
        return {
            "quality_score": partial.get("quality_score"),
            "notes": partial.get("quality_notes"),
        }
    if node == "report":
        rep = partial.get("report", {})
        return {"sections": len(rep.get("sections", [])), "confidence": rep.get("confidence")}
    return {}


def schedule_run(session_id: str) -> None:
    asyncio.create_task(run_session(session_id))
