import time

import pytest
from fastapi import status
from httpx import AsyncClient

from master.api import deps
from master.core.audit import log_action
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


@pytest.fixture(autouse=True)
def clear_rate_limiter():
    from master.core.rate_limiter import rate_limiter

    rate_limiter._buckets.clear()


@pytest.mark.asyncio
async def test_list_audit_entries_empty(client: AsyncClient, auth_headers):
    # The migration seeds 1 genesis entry (SYSTEM_INIT)
    response = await client.get("/api/audit", headers=auth_headers("operator"))
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["entries"]) == 1
    assert data["entries"][0]["action"] == "SYSTEM_INIT"
    assert data["limit"] == 50
    assert data["offset"] == 0
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_list_audit_entries_auth_roles(client: AsyncClient, auth_headers):
    # Viewer role -> Forbidden
    response = await client.get("/api/audit", headers=auth_headers("viewer"))
    assert response.status_code == status.HTTP_403_FORBIDDEN

    # Unauthenticated -> Unauthorized (no credentials)
    response_unauth = await client.get("/api/audit")
    assert response_unauth.status_code == status.HTTP_401_UNAUTHORIZED

    # Operator role -> Success
    response_op = await client.get("/api/audit", headers=auth_headers("operator"))
    assert response_op.status_code == status.HTTP_200_OK

    # Admin role -> Success
    response_admin = await client.get("/api/audit", headers=auth_headers("admin"))
    assert response_admin.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_list_audit_entries_filtering_and_pagination(client: AsyncClient, db, auth_headers):
    # Insert some audit logs using log_action
    # Sequence is monotonic inside log_action (synchronized with lock)
    await log_action(
        db, user_id="user1", action="CREATE_NODE", node_id="node-a", details={"name": "A"}
    )
    await log_action(
        db, user_id="user2", action="UPDATE_NODE", node_id="node-b", details={"name": "B"}
    )
    await log_action(
        db, user_id="user1", action="DELETE_NODE", node_id="node-a", details={"name": "A-deleted"}
    )
    await db.commit()

    # 1. Fetch all (limit=50) - should get 4 entries (genesis + 3 new ones), ordered by sequence descending
    response = await client.get("/api/audit", headers=auth_headers("operator"))
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] == 4
    assert len(data["entries"]) == 4
    # Check sequence order (descending)
    assert (
        data["entries"][0]["sequence"]
        > data["entries"][1]["sequence"]
        > data["entries"][2]["sequence"]
        > data["entries"][3]["sequence"]
    )

    # Check fields in first entry
    first_entry = data["entries"][0]
    assert first_entry["user_id"] == "user1"
    assert first_entry["action"] == "DELETE_NODE"
    assert first_entry["node_id"] == "node-a"
    assert first_entry["details"] == {"name": "A-deleted"}
    assert first_entry["previous_hash"] is not None
    assert first_entry["entry_hash"] is not None

    # 2. Filter by node_id="node-a" -> should return 2 entries (DELETE_NODE, CREATE_NODE)
    response_node = await client.get("/api/audit?node_id=node-a", headers=auth_headers("operator"))
    assert response_node.status_code == status.HTTP_200_OK
    data_node = response_node.json()
    assert data_node["total"] == 2
    assert len(data_node["entries"]) == 2
    assert data_node["entries"][0]["action"] == "DELETE_NODE"
    assert data_node["entries"][1]["action"] == "CREATE_NODE"

    # 3. Filter by action="UPDATE_NODE" -> should return 1 entry
    response_action = await client.get(
        "/api/audit?action=UPDATE_NODE", headers=auth_headers("operator")
    )
    assert response_action.status_code == status.HTTP_200_OK
    data_action = response_action.json()
    assert data_action["total"] == 1
    assert len(data_action["entries"]) == 1
    assert data_action["entries"][0]["node_id"] == "node-b"

    # 4. Pagination: limit=2, offset=1 (should return UPDATE_NODE, CREATE_NODE)
    response_paginated = await client.get(
        "/api/audit?limit=2&offset=1", headers=auth_headers("operator")
    )
    assert response_paginated.status_code == status.HTTP_200_OK
    data_pag = response_paginated.json()
    assert data_pag["total"] == 4
    assert len(data_pag["entries"]) == 2
    assert data_pag["limit"] == 2
    assert data_pag["offset"] == 1
    assert data_pag["entries"][0]["action"] == "UPDATE_NODE"
    assert data_pag["entries"][1]["action"] == "CREATE_NODE"
