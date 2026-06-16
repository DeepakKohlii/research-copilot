"""A tiny in-memory, per-IP rate limiter used as a FastAPI dependency.

The expensive endpoints (creating a session, starting a run, chatting) each cost
real LLM/search-API quota, so a public deployment needs a cap to stop a single
caller from draining it. This is intentionally simple — an in-process sliding
window — which is correct because the app runs as a single worker. A multi-worker
or multi-instance deployment would move this to Redis.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from .config import settings
from .logging_conf import get_logger

log = get_logger("ratelimit")

# ip -> timestamps (monotonic seconds) of recent hits
_hits: dict[str, deque[float]] = defaultdict(deque)


def reset() -> None:
    """Clear all counters (used by tests)."""
    _hits.clear()


def _client_ip(request: Request) -> str:
    # Behind Render/Vercel the real client is in X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    def __init__(self, limit: int, window: int = 60) -> None:
        self.limit = limit
        self.window = window

    def __call__(self, request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        ip = _client_ip(request)
        now = time.monotonic()
        cutoff = now - self.window
        hits = _hits[ip]
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= self.limit:
            log.warning("rate limit hit for %s (%d/%ds)", ip, self.limit, self.window)
            raise HTTPException(
                status_code=429,
                detail="Too many requests — please slow down and try again shortly.",
            )
        hits.append(now)


# Shared limiter for the expensive write endpoints.
rate_limit = RateLimiter(settings.rate_limit_per_minute)
