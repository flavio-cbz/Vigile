"""
Vigile — Chat API: chat sessions CRUD endpoints
"""

from __future__ import annotations

import json
import logging
import time
import uuid
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated  # type: ignore[attr-defined]
from typing import Any

from fastapi import Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from master.api.chat_router import router
from master.api.demo_data import (
    delete_demo_chat_session,
    get_demo_chat_session,
    get_demo_chat_sessions,
    is_demo,
    save_demo_chat_session,
)
from master.api.deps import DB, require_role

logger = logging.getLogger(__name__)


class _SessionSaveRequest(BaseModel):
    id: str | None = None
    node_id: str | None = None
    title: str
    history: list[dict[str, Any]] = []


@router.get(
    "/sessions",
    summary="List chat sessions (Operator+)",
)
async def list_sessions(
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    node_id: str | None = Query(default=None, description="Filter by node ID"),
) -> list[dict[str, Any]]:
    """List all chat sessions for the logged in user, optionally filtered by node_id."""
    if is_demo(claims):
        return get_demo_chat_sessions(claims["sub"])

    user_id = claims["sub"]
    params: tuple[str, ...]
    if node_id and node_id != "all":
        query = (
            "SELECT * FROM chat_sessions WHERE user_id = ? AND node_id = ? ORDER BY updated_at DESC"
        )
        params = (user_id, node_id)
    else:
        query = "SELECT * FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC"
        params = (user_id,)

    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()

    results = []
    for r in rows:
        d = dict(r)
        try:
            d["history"] = json.loads(d.pop("history_json"))
        except Exception:
            logger.debug("Failed to parse chat session history JSON in list_sessions, using empty list")
            d["history"] = []
        results.append(d)
    return results


@router.get(
    "/sessions/{session_id}",
    summary="Get chat session details (Operator+)",
)
async def get_session(
    session_id: Annotated[str, Path(description="Session UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
) -> dict[str, Any]:
    """Get the details and history of a specific chat session."""
    if is_demo(claims):
        sess = get_demo_chat_session(session_id)
        if sess is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return sess

    user_id = claims["sub"]
    async with db.execute(
        "SELECT * FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, user_id),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    d = dict(row)
    try:
        d["history"] = json.loads(d.pop("history_json"))
    except Exception:
        logger.debug("Failed to parse chat session history JSON in get_session, using empty list")
        d["history"] = []
    return d


@router.post(
    "/sessions",
    summary="Create or update a chat session (Operator+)",
)
async def save_session(
    body: _SessionSaveRequest,
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
) -> dict[str, Any]:
    """Create a new chat session or update an existing one's metadata and/or history."""
    if is_demo(claims):
        sess_id = body.id or str(uuid.uuid4())
        db_node_id = body.node_id
        if db_node_id == "all":
            db_node_id = None
        return save_demo_chat_session(
            session_id=sess_id,
            user_id=claims["sub"],
            node_id=db_node_id,
            title=body.title,
            history=body.history,
        )

    user_id = claims["sub"]
    sess_id = body.id or str(uuid.uuid4())
    node_id = body.node_id
    if node_id == "all":
        node_id = None

    now = time.time()
    history_str = json.dumps(body.history)

    async with db.execute(
        "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
        (sess_id, user_id),
    ) as cursor:
        exists = await cursor.fetchone() is not None

    if exists:
        await db.execute(
            """
            UPDATE chat_sessions SET
                node_id = ?, title = ?, history_json = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (node_id, body.title, history_str, now, sess_id, user_id),
        )
    else:
        await db.execute(
            """
            INSERT INTO chat_sessions (id, user_id, node_id, title, history_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (sess_id, user_id, node_id, body.title, history_str, now, now),
        )
    await db.commit()

    return {
        "id": sess_id,
        "user_id": user_id,
        "node_id": node_id,
        "title": body.title,
        "history": body.history,
        "created_at": now,
        "updated_at": now,
    }


@router.delete(
    "/sessions/{session_id}",
    summary="Delete a chat session (Operator+)",
)
async def delete_session(
    session_id: Annotated[str, Path(description="Session UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
) -> dict[str, Any]:
    """Delete a chat session."""
    if is_demo(claims):
        deleted = delete_demo_chat_session(session_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return {"success": True}

    user_id = claims["sub"]
    async with db.execute(
        "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, user_id),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    await db.execute(
        "DELETE FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, user_id),
    )
    await db.commit()
    return {"success": True}
