from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from ..db.database import get_db
from ..db.repository import Repository
from ..schemas.api import CreateSessionRequest, SessionOut, SessionSummary

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionOut, status_code=201)
def create_session(body: CreateSessionRequest, db: OrmSession = Depends(get_db)):
    repo = Repository(db)
    session = repo.create_session(body.company, body.objective, body.website)
    return session


@router.get("", response_model=list[SessionSummary])
def list_sessions(db: OrmSession = Depends(get_db)):
    return Repository(db).list_sessions()


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: str, db: OrmSession = Depends(get_db)):
    session = Repository(db).get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
