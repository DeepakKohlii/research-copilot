from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as OrmSession

from ..config import settings
from ..db.database import SessionLocal, get_db
from ..db.repository import Repository
from ..logging_conf import get_logger
from ..ratelimit import rate_limit
from ..schemas.api import ChatMessageOut, ChatRequest
from ..services.llm import get_llm
from ..services.search import get_search

log = get_logger("api.chat")

_STOPWORDS = {
    "what", "whats", "which", "where", "when", "who", "whom", "whose", "why",
    "how", "does", "did", "are", "was", "were", "the", "this", "that", "these",
    "those", "their", "them", "they", "your", "you", "our", "for", "from",
    "with", "about", "any", "other", "way", "tell", "get", "give", "show",
    "have", "has", "can", "could", "would", "please", "company", "and",
    "more", "else", "again", "also", "detail", "details", "explain",
}

router = APIRouter(prefix="/api/sessions", tags=["chat"])

_CHAT_SYSTEM = (
    "You are a research assistant helping a salesperson prepare for a meeting. "
    "Answer the user's question about the company using, in order of preference: "
    "(1) the briefing, (2) the live web results provided, (3) your own general "
    "knowledge. Prefer cited facts from the briefing or web results. If a precise "
    "figure isn't available, give your best-supported estimate or range and flag "
    "it as approximate — only say you don't know if you genuinely have nothing "
    "useful. Be concise and practical."
)


def _needs_live_search(question: str, context: str) -> bool:
    """Only hit the search API when the briefing likely doesn't already answer
    the question — i.e. most of the question's key terms are missing from the
    briefing context. Avoids a paid search on every covered follow-up."""
    if not settings.chat_live_search:
        return False
    ctx = context.lower()
    terms = [
        w.strip("?.,!'\"():;")
        for w in question.lower().split()
    ]
    terms = [w for w in terms if len(w) > 3 and w not in _STOPWORDS]
    if not terms:
        return False
    missing = [t for t in terms if t not in ctx]
    return len(missing) > len(terms) / 2


def _live_context(company: str, question: str) -> str:
    """Pull a few fresh web snippets for the question so the chat can answer
    things the briefing didn't cover (headcount, latest news, etc.)."""
    try:
        results = get_search().search(f"{company} {question}", deep=False)
    except Exception as exc:  # noqa: BLE001 — chat still works without live search
        log.warning("chat live search failed: %s", exc)
        return ""
    lines = [
        f"- {r.get('title', '')}: {r.get('snippet', '')} ({r.get('source', '')})"
        for r in results[:4]
        if r.get("snippet")
    ]
    return "\n".join(lines)


def _chat_prompt(context: str, history: str, web: str = "") -> str:
    web_block = f"\n\nLive web results:\n{web}" if web else ""
    return (
        f"Briefing context:\n{context}{web_block}\n\n"
        f"Conversation so far:\n{history}\n\n"
        "Answer the latest user question."
    )


@router.get("/{session_id}/chat", response_model=list[ChatMessageOut])
def get_chat(session_id: str, db: OrmSession = Depends(get_db)):
    repo = Repository(db)
    if repo.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return repo.list_chat(session_id)


@router.post(
    "/{session_id}/chat",
    response_model=ChatMessageOut,
    dependencies=[Depends(rate_limit)],
)
def post_chat(session_id: str, body: ChatRequest, db: OrmSession = Depends(get_db)):
    repo = Repository(db)
    session = repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.report:
        raise HTTPException(status_code=409, detail="Briefing not ready yet")

    repo.add_chat(session_id, "user", body.message)

    context = _build_context(session.report)
    web = (
        _live_context(session.company, body.message)
        if _needs_live_search(body.message, context)
        else ""
    )
    history = "\n".join(f"{m.role}: {m.content}" for m in repo.list_chat(session_id))
    answer = get_llm().complete(
        system=_CHAT_SYSTEM,
        prompt=_chat_prompt(context, history, web),
    )
    msg = repo.add_chat(session_id, "assistant", answer)
    return msg


@router.post("/{session_id}/chat/stream", dependencies=[Depends(rate_limit)])
def post_chat_stream(
    session_id: str, body: ChatRequest, db: OrmSession = Depends(get_db)
):
    repo = Repository(db)
    session = repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.report:
        raise HTTPException(status_code=409, detail="Briefing not ready yet")

    repo.add_chat(session_id, "user", body.message)
    context = _build_context(session.report)
    web = (
        _live_context(session.company, body.message)
        if _needs_live_search(body.message, context)
        else ""
    )
    history = "\n".join(f"{m.role}: {m.content}" for m in repo.list_chat(session_id))

    def generate():
        parts: list[str] = []
        try:
            for chunk in get_llm().stream(
                system=_CHAT_SYSTEM, prompt=_chat_prompt(context, history, web)
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
