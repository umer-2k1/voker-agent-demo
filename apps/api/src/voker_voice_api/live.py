import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator


class SessionEventBroker:
    """In-process broker for MVP SSE updates; PostgreSQL remains the durable source."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[str]]] = defaultdict(set)

    async def publish(self, session_id: str, payload: str) -> None:
        for queue in tuple(self._subscribers[session_id]):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                continue

    async def subscribe(self, session_id: str) -> AsyncIterator[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._subscribers[session_id].add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers[session_id].discard(queue)
            if not self._subscribers[session_id]:
                self._subscribers.pop(session_id, None)


broker = SessionEventBroker()
