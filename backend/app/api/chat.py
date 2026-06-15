from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as OrmSession

from ..db.database import SessionLocal, get_db
from ..db.repository import Repository
from ..logging_conf import get_logger
from ..schemas.api import ChatMessageOut, ChatRequest
from ..services.llm import get_llm

log = get_logger("api.chat")

router = APIRouter(prefix="/api/sessions", tags=["chat"])

_CHAT_SYSTEM = "You answer follow-up questions using ONLY the provided briefing."


def _chat_prompt(context: str, history: str) -> str:
    return (
        f"Briefing context:\n{context}\n\nConversation so far:\n{history}\n\n"
        "Answer the latest user question."
    )


@router.get("/{session_id}/chat", response_model=list[ChatMessageOut])
def get_chat(session_id: str, db: OrmSession = Depends(get_db)):
    repo = Repository(db)
    if repo.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return repo.list_chat(session_id)


@router.post("/{session_id}/chat", response_model=ChatMessageOut)
def post_chat(session_id: str, body: ChatRequest, db: OrmSession = Depends(get_db)):
    repo = Repository(db)
    session = repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.report:
        raise HTTPException(status_code=409, detail="Briefing not ready yet")

    repo.add_chat(session_id, "user", body.message)

    context = _build_context(session.report)
    history = "\n".join(f"{m.role}: {m.content}" for m in repo.list_chat(session_id))
    answer = get_llm().complete(
        system=_CHAT_SYSTEM,
        prompt=_chat_prompt(context, history),
    )
    msg = repo.add_chat(session_id, "assistant", answer)
    return msg


@router.post("/{session_id}/chat/stream")
def post_chat_stream(
    session_id: str, body: ChatRequest, db: OrmSession = Depends(get_db)
):
    session = repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.report:
        raise HTTPException(status_code=409, detail="Briefing not ready yet")

    repo.add_chat(session_id, "user", body.message)
    context = _build_context(session.report)
    history = "\n".join(f"{m.role}: {m.content}" for m in repo.list_chat(session_id))

    def generate():
        parts: list[str] = []
        try:
            for chunk in get_llm().stream(
                system=_CHAT_SYSTEM, prompt=_chat_prompt(context, history)
            ):
                parts.append(chunk)
                yield chunk
        except Exception as exc:  # noqa: BLE001 — always close out with a saved turn
            log.warning("[%s] chat stream error: %s", session_id, exc)
        finally:
            text = "".join(parts).strip() or (
                "Sorry — I couldn't generate a response. Please try again."
            )
            save_db = SessionLocal()
            try:
                Repository(save_db).add_chat(session_id, "assistant", text)
            finally:
                save_db.close()

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


def _build_context(report: dict) -> str:
    lines = [f"Company: {report.get('company')}", report.get("executive_summary", "")]
    for sec in report.get("sections", []):
        lines.append(f"\n## {sec['title']}")
        lines.extend(f"- {p}" for p in sec.get("key_points", []))
    return "\n".join(lines)
