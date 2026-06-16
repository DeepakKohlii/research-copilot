from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession
from sse_starlette.sse import EventSourceResponse

from ..db.database import get_db
from ..db.repository import Repository
from ..events import bus
from ..graph.runner import schedule_run
from ..ratelimit import rate_limit

router = APIRouter(prefix="/api/sessions", tags=["runs"])

_TERMINAL = {"run_completed", "run_failed"}


@router.post("/{session_id}/run", status_code=202, dependencies=[Depends(rate_limit)])
async def start_run(session_id: str, db: OrmSession = Depends(get_db)):
    repo = Repository(db)
    session = repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status == "running":
        raise HTTPException(status_code=409, detail="Run already in progress")
    schedule_run(session_id)
    return {"session_id": session_id, "status": "running"}


@router.get("/{session_id}/stream")
async def stream(session_id: str, db: OrmSession = Depends(get_db)):
    repo = Repository(db)
    if repo.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")

    queue = bus.subscribe(session_id)

    async def event_generator():
        seen_max = 0
        try:
            # 1. Replay durable history.
            for ev in repo.list_events(session_id):
                seen_max = max(seen_max, ev.id)
                yield _sse(ev.id, ev.type, ev.node, ev.data)
                if ev.type in _TERMINAL:
                    return
            # 2. Live tail (skip anything already replayed).
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                if event["id"] <= seen_max:
                    continue
                seen_max = event["id"]
                yield _sse(event["id"], event["type"], event["node"], event["data"])
                if event["type"] in _TERMINAL:
                    return
        finally:
            bus.unsubscribe(session_id, queue)

    return EventSourceResponse(event_generator())


def _sse(event_id, type_, node, data):
    payload = {"id": event_id, "type": type_, "node": node, "data": data}
    return {"event": type_, "id": str(event_id), "data": json.dumps(payload)}
