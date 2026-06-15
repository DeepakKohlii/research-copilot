from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import chat, runs, sessions
from .config import settings
from .db.database import init_db
from .logging_conf import get_logger

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info(
        "%s started (env=%s, llm=%s/%s)",
        settings.app_name,
        settings.environment,
        settings.resolved_llm_provider,
        settings.resolved_llm_model,
    )
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(runs.router)
app.include_router(chat.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_provider": settings.resolved_llm_provider,
        "llm_model": settings.resolved_llm_model,
    }


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
