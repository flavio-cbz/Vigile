from __future__ import annotations

"""
Vigile — Server-Sent Events stream for node state changes.

Subscribes to the in-process EventBus and forwards each event to the operator
browser as a text/event-stream. Two topics are forwarded:
  - `node.state`  : state transitions (PENDING→CONNECTED→LOST, etc.)
  - `node.deleted` : hard-delete events (the node row has been removed)

EventSource in the browser auto-reconnects; we replay the cached ring buffer
on (re)connect for both topics.

Auth: EventSource cannot send custom headers, so the JWT is accepted via
the `?token=<jwt>` query parameter instead of the Authorization header.
The same access-token verifier used by the REST API is reused here.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from master.api.deps import get_bus
from master.core.event_bus import EventBus
from master.core.security_manager import (
    ExpiredTokenError,
    SecurityError,
    get_security_instance,
)

router = APIRouter(prefix="/api/nodes/events", tags=["nodes-events"])
logger = logging.getLogger(__name__)


_SSE_TOPICS: tuple[str, ...] = ("node.state", "node.deleted")


async def _sse_stream(bus: EventBus, request: Request) -> AsyncGenerator[str, None]:
    state_queue = bus.subscribe("node.state")
    deleted_queue = bus.subscribe("node.deleted")
    try:
        for topic in _SSE_TOPICS:
            for evt in bus.replay(topic):
                if await request.is_disconnected():
                    return
                yield f"event: {topic}\ndata: {json.dumps(evt['payload'])}\n\n"

        while True:
            if await request.is_disconnected():
                break
            try:
                evt = await asyncio.wait_for(_next_event(state_queue, deleted_queue), timeout=25.0)
                yield f"event: {evt['topic']}\ndata: {json.dumps(evt['payload'])}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        bus.unsubscribe("node.state", state_queue)
        bus.unsubscribe("node.deleted", deleted_queue)


async def _next_event(*queues: asyncio.Queue):
    """Wait on multiple queues concurrently; return whichever gets a message first."""
    tasks = [asyncio.create_task(q.get()) for q in queues]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in tasks:
            if not t.done():
                t.cancel()
        return done.pop().result()
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()


@router.get("/stream")
async def stream(
    request: Request,
    token: Optional[str] = Query(default=None),
    bus: EventBus = Depends(get_bus),
) -> StreamingResponse:
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing token query parameter (EventSource cannot send Authorization headers)",
        )
    try:
        get_security_instance().verify_access_token(token)
    except ExpiredTokenError:
        raise HTTPException(status_code=401, detail="Token has expired") from None
    except SecurityError:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from None

    return StreamingResponse(
        _sse_stream(bus, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
