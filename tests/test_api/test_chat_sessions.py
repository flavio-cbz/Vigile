import json
import unittest.mock as mock

import pytest
from httpx import AsyncClient

from master.api import deps
from master.core.node_manager import NodeState, node_manager
from master.core.security_manager import SecurityManager
from master.main import app


@pytest.fixture
def auth_headers(security: SecurityManager) -> callable:
    def _make(role: str = "admin") -> dict[str, str]:
        token = security.create_access_token("test-user", "test_user", role)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture(autouse=True)
async def seed_test_user(db) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO users (id, username, password_hash, role, is_active, must_change_password, created_at, updated_at) "
        "VALUES ('test-user', 'test_user', 'hashed_pass', 'admin', 1, 0, 123456789.0, 123456789.0)"
    )
    await db.commit()


@pytest.fixture
async def client(db) -> AsyncClient:
    from httpx import ASGITransport, AsyncClient

    app.dependency_overrides[deps.get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)


async def _setup_node(db, name: str = "test-node") -> str:
    node_id = await node_manager.create_node(db, name=name)
    await node_manager.transition_state(db, node_id, NodeState.ENROLLING)
    await node_manager.transition_state(db, node_id, NodeState.CONNECTED)
    return node_id


@pytest.mark.asyncio
async def test_list_sessions_empty(client: AsyncClient, auth_headers: callable) -> None:
    """GET /api/chat/sessions returns empty list initially."""
    resp = await client.get("/api/chat/sessions", headers=auth_headers("operator"))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_and_get_session(client: AsyncClient, auth_headers: callable) -> None:
    """POST /api/chat/sessions creates a session, which can be retrieved."""
    payload = {
        "title": "First Conversation",
        "history": [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}],
    }
    resp = await client.post("/api/chat/sessions", headers=auth_headers("operator"), json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] is not None
    assert data["title"] == "First Conversation"
    assert data["history"] == payload["history"]
    assert data["node_id"] is None

    session_id = data["id"]
    # Get details
    resp_get = await client.get(
        f"/api/chat/sessions/{session_id}", headers=auth_headers("operator")
    )
    assert resp_get.status_code == 200
    data_get = resp_get.json()
    assert data_get["id"] == session_id
    assert data_get["title"] == "First Conversation"
    assert data_get["history"] == payload["history"]


@pytest.mark.asyncio
async def test_update_session(client: AsyncClient, auth_headers: callable) -> None:
    """POST /api/chat/sessions updates an existing session."""
    payload = {"title": "Initial Title", "history": []}
    resp = await client.post("/api/chat/sessions", headers=auth_headers("operator"), json=payload)
    session_id = resp.json()["id"]

    # Update
    update_payload = {
        "id": session_id,
        "title": "Updated Title",
        "history": [{"role": "user", "content": "test"}],
    }
    resp_update = await client.post(
        "/api/chat/sessions", headers=auth_headers("operator"), json=update_payload
    )
    assert resp_update.status_code == 200
    data = resp_update.json()
    assert data["id"] == session_id
    assert data["title"] == "Updated Title"
    assert data["history"] == update_payload["history"]

    # Check via GET
    resp_get = await client.get(
        f"/api/chat/sessions/{session_id}", headers=auth_headers("operator")
    )
    assert resp_get.json()["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_delete_session(client: AsyncClient, auth_headers: callable) -> None:
    """DELETE /api/chat/sessions/{session_id} deletes a session."""
    resp = await client.post(
        "/api/chat/sessions", headers=auth_headers("operator"), json={"title": "Delete me"}
    )
    session_id = resp.json()["id"]

    resp_del = await client.delete(
        f"/api/chat/sessions/{session_id}", headers=auth_headers("operator")
    )
    assert resp_del.status_code == 200
    assert resp_del.json() == {"success": True}

    # Verify 404
    resp_get = await client.get(
        f"/api/chat/sessions/{session_id}", headers=auth_headers("operator")
    )
    assert resp_get.status_code == 404


@pytest.mark.asyncio
async def test_list_sessions_filtering(db, client: AsyncClient, auth_headers: callable) -> None:
    """GET /api/chat/sessions allows filtering by node_id."""
    node_id_1 = await _setup_node(db, "node-1")
    node_id_2 = await _setup_node(db, "node-2")

    # Global session
    await client.post(
        "/api/chat/sessions",
        headers=auth_headers("operator"),
        json={"title": "Global session", "node_id": None},
    )
    # Node 1 session
    await client.post(
        "/api/chat/sessions",
        headers=auth_headers("operator"),
        json={"title": "Node 1 session", "node_id": node_id_1},
    )
    # Node 2 session
    await client.post(
        "/api/chat/sessions",
        headers=auth_headers("operator"),
        json={"title": "Node 2 session", "node_id": node_id_2},
    )

    # List all
    resp_all = await client.get("/api/chat/sessions", headers=auth_headers("operator"))
    assert len(resp_all.json()) == 3

    # Filter node 1
    resp_node1 = await client.get(
        f"/api/chat/sessions?node_id={node_id_1}", headers=auth_headers("operator")
    )
    assert len(resp_node1.json()) == 1
    assert resp_node1.json()[0]["title"] == "Node 1 session"


@pytest.mark.asyncio
async def test_chat_saves_and_loads_history_with_session(
    client: AsyncClient, auth_headers: callable
) -> None:
    """POST /api/chat saves history automatically and loads it on subsequent calls with session_id."""
    mock_llm = mock.AsyncMock()

    async def mock_stream(*args, **kwargs):
        yield {"type": "token", "content": "Response from assistant"}
        yield {"type": "done"}

    mock_llm.stream = mock_stream
    app.dependency_overrides[deps.get_llm_client] = lambda: mock_llm

    session_id = "test-session-uuid"
    try:
        # First message (creates session automatically if session_id is provided)
        resp1 = await client.post(
            "/api/chat",
            headers=auth_headers("operator"),
            json={"message": "My first query", "session_id": session_id},
        )
        assert resp1.status_code == 200
        assert "Response from assistant" in resp1.text

        # Get details from sessions endpoint
        resp_sess = await client.get(
            f"/api/chat/sessions/{session_id}", headers=auth_headers("operator")
        )
        assert resp_sess.status_code == 200
        sess_data = resp_sess.json()
        assert sess_data["title"].startswith("My first query")
        assert len(sess_data["history"]) == 2
        assert sess_data["history"][0] == {"role": "user", "content": "My first query"}
        assert sess_data["history"][1] == {
            "role": "assistant",
            "content": "Response from assistant",
        }

        # Second message (should load history from session)
        resp2 = await client.post(
            "/api/chat",
            headers=auth_headers("operator"),
            json={"message": "My second query", "session_id": session_id},
        )
        assert resp2.status_code == 200
        assert "Response from assistant" in resp2.text

        # Verify history grows
        resp_sess2 = await client.get(
            f"/api/chat/sessions/{session_id}", headers=auth_headers("operator")
        )
        assert len(resp_sess2.json()["history"]) == 4

    finally:
        app.dependency_overrides.pop(deps.get_llm_client, None)
