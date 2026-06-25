"""
Vigile — In-process Event Bus

Minimal async pub/sub used to fan out state-change events to subscribed consumers
(notably the operator SSE endpoint). No external deps. Bounded queues per subscriber
to prevent memory leaks under backpressure.
"""

import asyncio
import logging
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

_MAX_QUEUE_SIZE = 200
_REPLAY_RING_SIZE = 200


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._replay: dict[str, deque[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            ring = self._replay.setdefault(topic, deque(maxlen=_REPLAY_RING_SIZE))
            ring.append({"topic": topic, "payload": payload})
            queues = list(self._subscribers.get(topic, []))
        for q in queues:
            try:
                q.put_nowait({"topic": topic, "payload": payload})
            except asyncio.QueueFull:
                logger.warning("EventBus subscriber queue full, dropping event for topic=%s", topic)

    def subscribe(self, topic: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE_SIZE)
        self._subscribers.setdefault(topic, []).append(queue)
        return queue

    def unsubscribe(self, topic: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(topic, [])
        try:
            subs.remove(queue)
        except ValueError:
            pass

    def replay(self, topic: str) -> list[dict[str, Any]]:
        return list(self._replay.get(topic, []))


event_bus = EventBus()


def get_event_bus() -> EventBus:
    return event_bus
