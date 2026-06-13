import unittest.mock as mock

import pytest
from httpx import AsyncClient

from master.api import deps
from master.core.action_proposal import ActionProposal
from master.core.node_manager import NodeState, node_manager
from master.core.security_manager import SecurityManager
from master.main import app


@pytest.fixture
def auth_headers(security: SecurityManager):
    def _make(role: str = "admin"):
        token = security.create_access_token("test-user", "test_user", role)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
async def client(db):
    from httpx import ASGITransport, AsyncClient

    app.dependency_overrides[deps.get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)


async def _setup_node(db, name="chat-node") -> str:
    node_id = await node_manager.create_node(db, name=name)
    await node_manager.transition_state(db, node_id, NodeState.ENROLLING)
    await node_manager.transition_state(db, node_id, NodeState.CONNECTED)
    return node_id


async def _insert_proposal(db, proposal):
    """Insert a proposal with node_id that exists."""
    data = proposal.to_db_dict()
    await db.execute(
        """INSERT INTO action_proposals (id, node_id, action, params_json,
           reasoning, risk_level, status, created_by, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["id"],
            data["node_id"],
            data["action"],
            data["params_json"],
            data["reasoning"],
            data["risk_level"],
            data["status"],
            data["created_by"],
            data["created_at"],
            data["updated_at"],
        ),
    )
    await db.commit()


@pytest.mark.asyncio
async def test_chat_unauthorized(client):
    """No auth token → 401."""
    resp = await client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_viewer_forbidden(client, auth_headers):
    """Viewer role → 403."""
    resp = await client.post("/api/chat", headers=auth_headers("viewer"), json={"message": "hi"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_chat_empty_message(client, auth_headers):
    """Empty message → 400."""
    resp = await client.post("/api/chat", headers=auth_headers("admin"), json={"message": ""})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_chat_streams_sse(client, auth_headers):
    """Chat endpoint returns SSE stream with tokens."""
    mock_llm = mock.AsyncMock()

    async def mock_stream(*args, **kwargs):
        yield {"type": "token", "content": "Hello from AI"}
        yield {"type": "done"}

    mock_llm.stream = mock_stream
    app.dependency_overrides[deps.get_llm_client] = lambda: mock_llm
    try:
        resp = await client.post(
            "/api/chat", headers=auth_headers("admin"), json={"message": "Hello", "node_id": None}
        )
        assert resp.status_code == 200
        text = resp.text
        assert text.startswith("data:")
        assert '"token"' in text
        assert "Hello from AI" in text
    finally:
        app.dependency_overrides.pop(deps.get_llm_client, None)


@pytest.mark.asyncio
async def test_chat_streams_error(client, auth_headers):
    """Chat endpoint returns error event on LLM failure."""
    mock_llm = mock.AsyncMock()

    async def mock_stream(*args, **kwargs):
        yield {"type": "error", "detail": "LLM is down"}
        yield {"type": "done"}

    mock_llm.stream = mock_stream
    app.dependency_overrides[deps.get_llm_client] = lambda: mock_llm
    try:
        resp = await client.post(
            "/api/chat", headers=auth_headers("admin"), json={"message": "Hi", "node_id": None}
        )
        assert resp.status_code == 200
        assert '"LLM is down"' in resp.text
    finally:
        app.dependency_overrides.pop(deps.get_llm_client, None)


@pytest.mark.asyncio
async def test_proposals_list(db, client, auth_headers):
    """GET /api/chat/proposals returns proposals."""
    node_id = await node_manager.create_node(db, name="test-proposal")
    p = ActionProposal(
        node_id=node_id, action="RESTART_CONTAINER", params={"id": "web"}, reasoning="down"
    )
    await _insert_proposal(db, p)
    resp = await client.get("/api/chat/proposals", headers=auth_headers("admin"))
    assert resp.status_code == 200
    proposals = resp.json()
    assert isinstance(proposals, list)
    assert len(proposals) >= 1


@pytest.mark.asyncio
async def test_proposals_get(db, client, auth_headers):
    """GET /api/chat/proposals/{id} returns one proposal."""
    node_id = await node_manager.create_node(db, name="test-proposal-get")
    p = ActionProposal(
        node_id=node_id, action="RESTART_CONTAINER", params={"id": "web"}, reasoning="down"
    )
    await _insert_proposal(db, p)
    resp = await client.get(f"/api/chat/proposals/{p.id}", headers=auth_headers("admin"))
    assert resp.status_code == 200
    d = resp.json()
    assert d["id"] == p.id
    assert d["action"] == "RESTART_CONTAINER"


@pytest.mark.asyncio
async def test_proposals_get_not_found(client, auth_headers):
    """GET /api/chat/proposals/{id} returns 404 on missing."""
    resp = await client.get("/api/chat/proposals/nonexistent", headers=auth_headers("admin"))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_proposal(db, client, auth_headers):
    """POST /api/chat/proposals/{id}/approve approves and executes."""
    node_id = await _setup_node(db, "test-approve")
    p = ActionProposal(node_id=node_id, action="GET_STATS")
    await _insert_proposal(db, p)

    # Mock send_intent to return success
    orig = node_manager.send_intent

    async def mock_send(*args, **kwargs):
        return {"success": True, "output": "CPU: 10%"}

    node_manager.send_intent = mock_send
    try:
        resp = await client.post(
            f"/api/chat/proposals/{p.id}/approve", headers=auth_headers("admin")
        )
        assert resp.status_code == 200
        d = resp.json()
        assert d["status"] == "EXECUTED"
        assert d["approved_by"] == "test-user"
        assert d["executed_at"] is not None
        assert d.get("result") is not None
    finally:
        node_manager.send_intent = orig


@pytest.mark.asyncio
async def test_approve_proposal_not_pending(db, client, auth_headers):
    """Cannot approve a non-PENDING proposal."""
    node_id = await _setup_node(db, "test-already-approved")
    p = ActionProposal(node_id=node_id, action="GET_STATS")
    p.approve("user-1")
    await _insert_proposal(db, p)

    # Also update the approved_by field since _insert_proposal doesn't set it
    await db.execute(
        "UPDATE action_proposals SET approved_by = ? WHERE id = ?", (p.approved_by, p.id)
    )
    await db.commit()

    resp = await client.post(f"/api/chat/proposals/{p.id}/approve", headers=auth_headers("admin"))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_reject_proposal(db, client, auth_headers):
    """POST /api/chat/proposals/{id}/reject rejects proposal."""
    node_id = await _setup_node(db, "test-reject")
    p = ActionProposal(node_id=node_id, action="GET_STATS")
    await _insert_proposal(db, p)

    resp = await client.post(
        f"/api/chat/proposals/{p.id}/reject",
        headers=auth_headers("admin"),
        json={"reason": "not needed"},
    )
    assert resp.status_code == 200
    d = resp.json()
    assert d["status"] == "REJECTED"
    assert d["rejected_by"] == "test-user"
    assert d["rejection_reason"] == "not needed"
