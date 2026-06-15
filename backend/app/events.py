from __future__ import annotations

import asyncio
from collections import defaultdict


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, session_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers[session_id].add(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue) -> None:
        self._subscribers[session_id].discard(q)
        if not self._subscribers[session_id]:
            self._subscribers.pop(session_id, None)

    async def publish(self, session_id: str, event: dict) -> None:
        for q in list(self._subscribers.get(session_id, ())):
            await q.put(event)


bus = EventBus()
