import json
import time

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from master.api import deps
from master.core.security_manager import SecurityManager
from master.main import app


@pytest.fixture
def auth_headers(security: SecurityManager):
    def _make(role: str = "admin"):
        token = security.create_access_token("demo-user", "guest", role)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
async def client(db):
    app.dependency_overrides[deps.get_db] = lambda: db
    app.state.master_url = "http://test"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)


@pytest.fixture(autouse=True)
def clear_rate_limiter():
    from master.core.rate_limiter import rate_limiter

    rate_limiter._buckets.clear()


# ─── Auth ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demo_login_success(client: AsyncClient):
    response = await client.post(
        "/api/auth/login",
        json={"username": "guest", "password": "guest"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_demo_login_wrong_password(client: AsyncClient):
    response = await client.post(
        "/api/auth/login",
        json={"username": "guest", "password": "wrong"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_demo_refresh_token(client: AsyncClient):
    login_resp = await client.post(
        "/api/auth/login",
        json={"username": "guest", "password": "guest"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert data["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_demo_change_password_blocked(client: AsyncClient):
    login_resp = await client.post(
        "/api/auth/login",
        json={"username": "guest", "password": "guest"},
    )
    access_token = login_resp.json()["access_token"]

    headers = {"Authorization": f"Bearer {access_token}"}
    response = await client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"old_password": "guest", "new_password": "newpass123"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_demo_me(client: AsyncClient):
    login_resp = await client.post(
        "/api/auth/login",
        json={"username": "guest", "password": "guest"},
    )
    access_token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    response = await client.get("/api/auth/me", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["username"] == "guest"
    assert data["role"] == "admin"


# ─── Nodes ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demo_list_nodes(client: AsyncClient, auth_headers):
    response = await client.get("/api/nodes", headers=auth_headers("admin"))
    assert response.status_code == status.HTTP_200_OK
    nodes = response.json()
    assert len(nodes) >= 6
    node_ids = {n["id"] for n in nodes}
    assert "demo-node-01" in node_ids
    assert "demo-node-02" in node_ids
    assert "demo-node-03" in node_ids
    assert "demo-node-04" in node_ids
    assert "demo-node-05" in node_ids
    assert "demo-node-06" in node_ids
    assert "demo-node-04" in node_ids
    assert "demo-node-05" in node_ids
    assert "demo-node-06" in node_ids


@pytest.mark.asyncio
async def test_demo_get_node(client: AsyncClient, auth_headers):
    response = await client.get("/api/nodes/demo-node-01", headers=auth_headers("admin"))
    assert response.status_code == status.HTTP_200_OK
    node = response.json()
    assert node["id"] == "demo-node-01"
    assert node["name"] == "prod-web-01"
    assert node["online"] is True


@pytest.mark.asyncio
async def test_demo_get_node_404(client: AsyncClient, auth_headers):
    response = await client.get("/api/nodes/nonexistent", headers=auth_headers("admin"))
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_demo_node_stats(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/nodes/demo-node-01/stats?limit=3",
        headers=auth_headers("admin"),
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["node_id"] == "demo-node-01"
    assert len(data["snapshots"]) == 3
    assert data["snapshots"][0]["cpu_percent"] is not None
    assert data["snapshots"][0]["mem_percent"] is not None


@pytest.mark.asyncio
async def test_demo_node_logs(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/nodes/demo-node-01/logs?lines=5",
        headers=auth_headers("admin"),
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["node_id"] == "demo-node-01"
    assert len(data["output"]) > 0


@pytest.mark.asyncio
async def test_demo_delete_node(client: AsyncClient, auth_headers):
    response = await client.delete(
        "/api/nodes/demo-node-01",
        headers=auth_headers("admin"),
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_demo_generate_join(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/nodes/generate-join",
        headers=auth_headers("admin"),
        json={"name": "demo-node"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert "node_id" in data
    assert "token" in data
    assert data["expires_in"] == 1800
    assert "curl" in data["curl_command"]


@pytest.mark.asyncio
async def test_demo_verify_chain(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/nodes/verify-chain",
        headers=auth_headers("admin"),
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["verified"] is True


# ─── Services & Containers ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demo_services(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/nodes/demo-node-01/services",
        headers=auth_headers("admin"),
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["node_id"] == "demo-node-01"
    assert len(data["services"]) > 0


@pytest.mark.asyncio
async def test_demo_service_status(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/nodes/demo-node-01/services/nginx.service",
        headers=auth_headers("admin"),
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["service"] == "nginx.service"
    assert data["active"] == "active"


@pytest.mark.asyncio
async def test_demo_restart_service(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/nodes/demo-node-01/services/nginx.service/restart",
        headers=auth_headers("admin"),
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "Simulated restart" in data["output"]


@pytest.mark.asyncio
async def test_demo_containers(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/nodes/demo-node-01/containers",
        headers=auth_headers("admin"),
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["containers"]) == 2
    names = [c["name"] for c in data["containers"]]
    assert "web-app" in names
    assert "reverse-proxy" in names


@pytest.mark.asyncio
async def test_demo_restart_container(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/nodes/demo-node-01/containers/a1b2c3d4e5f6/restart",
        headers=auth_headers("admin"),
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "Simulated restart" in data["output"]


# ─── Chat & Proposals ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demo_chat_stream(client: AsyncClient, auth_headers):
    async with client.stream(
        "POST",
        "/api/chat",
        headers=auth_headers("admin"),
        json={"message": "status"},
    ) as response:
        assert response.status_code == status.HTTP_200_OK
        tokens = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                if payload["type"] == "token":
                    tokens.append(payload["content"])
                elif payload["type"] == "done":
                    break
        assert len(tokens) > 0


@pytest.mark.asyncio
async def test_demo_chat_with_session(client: AsyncClient, auth_headers):
    import uuid

    session_id = str(uuid.uuid4())
    async with client.stream(
        "POST",
        "/api/chat",
        headers=auth_headers("admin"),
        json={"message": "status", "session_id": session_id},
    ) as response:
        assert response.status_code == status.HTTP_200_OK
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                if payload["type"] == "done":
                    break

    sess_resp = await client.get(
        f"/api/chat/sessions/{session_id}",
        headers=auth_headers("admin"),
    )
    assert sess_resp.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_demo_proposals(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/chat/proposals",
        headers=auth_headers("admin"),
    )
    assert response.status_code == status.HTTP_200_OK
    proposals = response.json()
    assert len(proposals) >= 8
    assert any(p["status"] == "PENDING" for p in proposals)
    assert any(p["status"] == "APPROVED" for p in proposals)
    assert any(p["status"] == "EXECUTED" for p in proposals)
    assert any(p["status"] == "REJECTED" for p in proposals)
    assert any(p["status"] == "FAILED" for p in proposals)


@pytest.mark.asyncio
async def test_demo_proposal_approve(client: AsyncClient, auth_headers):
    list_resp = await client.get(
        "/api/chat/proposals",
        headers=auth_headers("admin"),
    )
    proposals = list_resp.json()
    proposal_id = proposals[0]["id"]

    response = await client.post(
        f"/api/chat/proposals/{proposal_id}/approve",
        headers=auth_headers("admin"),
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "EXECUTED"
    assert data["approved_by"] == "demo-user"

    verify = await client.get(
        f"/api/chat/proposals/{proposal_id}",
        headers=auth_headers("admin"),
    )
    assert verify.json()["status"] == "EXECUTED"


@pytest.mark.asyncio
async def test_demo_proposal_reject(client: AsyncClient, auth_headers):
    list_resp = await client.get(
        "/api/chat/proposals",
        headers=auth_headers("admin"),
    )
    proposals = list_resp.json()
    proposal_id = proposals[1]["id"]

    response = await client.post(
        f"/api/chat/proposals/{proposal_id}/reject",
        headers=auth_headers("admin"),
        json={"reason": "Not needed"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "REJECTED"
    assert data["rejected_by"] == "demo-user"


@pytest.mark.asyncio
async def test_demo_proposal_not_found(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/chat/proposals/nonexistent-id/approve",
        headers=auth_headers("admin"),
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_demo_proposal_already_approved(client: AsyncClient, auth_headers):
    list_resp = await client.get(
        "/api/chat/proposals",
        headers=auth_headers("admin"),
    )
    proposals = list_resp.json()
    proposal_id = proposals[0]["id"]

    await client.post(
        f"/api/chat/proposals/{proposal_id}/approve",
        headers=auth_headers("admin"),
    )

    response = await client.post(
        f"/api/chat/proposals/{proposal_id}/approve",
        headers=auth_headers("admin"),
    )
    assert response.status_code == status.HTTP_409_CONFLICT


# ─── Chat Sessions CRUD ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demo_chat_sessions_crud(client: AsyncClient, auth_headers):
    import uuid

    session_id = str(uuid.uuid4())

    create_resp = await client.post(
        "/api/chat/sessions",
        headers=auth_headers("admin"),
        json={
            "id": session_id,
            "title": "Test Demo Session",
            "history": [{"role": "user", "content": "hello"}],
        },
    )
    assert create_resp.status_code == status.HTTP_200_OK
    assert create_resp.json()["id"] == session_id

    list_resp = await client.get(
        "/api/chat/sessions",
        headers=auth_headers("admin"),
    )
    assert list_resp.status_code == status.HTTP_200_OK
    session_ids = {s["id"] for s in list_resp.json()}
    assert session_id in session_ids

    get_resp = await client.get(
        f"/api/chat/sessions/{session_id}",
        headers=auth_headers("admin"),
    )
    assert get_resp.status_code == status.HTTP_200_OK
    assert get_resp.json()["title"] == "Test Demo Session"

    delete_resp = await client.delete(
        f"/api/chat/sessions/{session_id}",
        headers=auth_headers("admin"),
    )
    assert delete_resp.status_code == status.HTTP_200_OK
    assert delete_resp.json()["success"] is True

    get_deleted = await client.get(
        f"/api/chat/sessions/{session_id}",
        headers=auth_headers("admin"),
    )
    assert get_deleted.status_code == status.HTTP_404_NOT_FOUND


# ─── Audit ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demo_audit(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/audit",
        headers=auth_headers("admin"),
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["entries"]) > 0
    # First entry should be the most recent (ORDER BY sequence DESC)
    assert isinstance(data["entries"][0]["action"], str)


# ─── Regression: demo seeder user must also serve mock data ──────────────────


def test_is_demo_recognizes_both_guest_and_demo_usernames():
    from master.api.demo_data import is_demo

    assert is_demo({"username": "guest", "sub": "demo-user"}) is True
    assert is_demo({"username": "demo", "sub": "real-user-id"}) is True
    assert is_demo({"username": "operator", "sub": "other-id"}) is False
    assert is_demo({}) is False
    assert is_demo({"username": "Demo"}) is False


@pytest.mark.asyncio
async def test_demo_user_via_jwt_sees_mock_nodes(client: AsyncClient, security: SecurityManager):
    token = security.create_access_token(user_id="demo-user", username="demo", role="admin")
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get("/api/nodes", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    nodes = response.json()
    assert len(nodes) == 6
    node_ids = {n["id"] for n in nodes}
    assert "demo-node-01" in node_ids
    assert "demo-node-06" in node_ids


@pytest.mark.asyncio
async def test_demo_user_via_jwt_sees_mock_audit(client: AsyncClient, security: SecurityManager):
    token = security.create_access_token(user_id="demo-user", username="demo", role="admin")
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get("/api/audit", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] >= 30
    # First entry should be the most recent (ORDER BY sequence DESC)
    assert isinstance(data["entries"][0]["action"], str)
    assert len(data["entries"][0]["action"]) > 0
