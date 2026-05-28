import pytest
import aiosqlite
from fastapi import status, Request, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from httpx import AsyncClient, ASGITransport

from master.main import app
from master.api import deps
from master.core.security_manager import SecurityManager, get_security_instance
from master.core.node_manager import node_manager, NodeState


@pytest.fixture
def auth_headers(security: SecurityManager):
    def _make(role: str = "admin"):
        token = security.create_access_token("test-user", "test_user", role)
        return {"Authorization": f"Bearer {token}"}
    return _make


@pytest.fixture
async def test_client(db):
    app.dependency_overrides[deps.get_db] = lambda: db
    app.state.master_url = "http://test"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)


@pytest.fixture(autouse=True)
def reset_compromised(security):
    # Ensure audit_compromised is reset before and after each test
    security.audit_compromised = False
    yield
    security.audit_compromised = False


@pytest.mark.asyncio
async def test_lockdown_closes_active_connections():
    # Setup mock WebSocket
    class MockWebSocket:
        def __init__(self):
            self.closed = False
            self.code = None
            self.reason = None

        async def close(self, code: int, reason: str):
            self.closed = True
            self.code = code
            self.reason = reason

    ws = MockWebSocket()
    node_id = "test-node-lockdown"
    
    # Register connection in NodeManager
    await node_manager.register_connection(node_id, ws)
    assert await node_manager.is_connected(node_id)

    # Trigger lockdown
    await node_manager.lockdown()

    # Verify connection unregistered and closed with 4433
    assert not await node_manager.is_connected(node_id)
    assert ws.closed
    assert ws.code == 4433


@pytest.mark.asyncio
async def test_get_current_user_lockdown_rules(security, db):
    # Setup mock request
    class MockRequest:
        def __init__(self, method: str):
            self.method = method

    # Create credentials
    admin_token = security.create_access_token("admin-id", "admin_user", "admin")
    viewer_token = security.create_access_token("viewer-id", "viewer_user", "viewer")
    
    admin_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=admin_token)
    viewer_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=viewer_token)

    # 1. Normal state - should pass
    security.audit_compromised = False

    claims = await deps.get_current_user(MockRequest("GET"), admin_creds, security, db)
    assert claims["role"] == "admin"

    # 2. Compromised state
    security.audit_compromised = True

    # Operator/admin GET request should fail
    with pytest.raises(HTTPException) as excinfo:
        await deps.get_current_user(MockRequest("GET"), admin_creds, security, db)
    assert excinfo.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    # Any mutating/write request (POST) should fail (even for viewer)
    with pytest.raises(HTTPException) as excinfo:
        await deps.get_current_user(MockRequest("POST"), viewer_creds, security, db)
    assert excinfo.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    # Viewer GET request should succeed (as it is not an operator nor state-changing)
    viewer_claims = await deps.get_current_user(MockRequest("GET"), viewer_creds, security, db)
    assert viewer_claims["role"] == "viewer"


@pytest.mark.asyncio
async def test_require_role_lockdown(security):
    security.audit_compromised = True
    admin_token = security.create_access_token("admin-id", "admin_user", "admin")
    admin_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=admin_token)

    dep = deps.require_role("admin")
    with pytest.raises(HTTPException) as excinfo:
        dep(admin_creds)
    assert excinfo.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_api_endpoints_lockdown(test_client, auth_headers):
    # Setup test node
    # When compromised, GET endpoints requiring admin/operator (like verify-chain) must fail with 503
    get_security_instance().audit_compromised = True

    # Call verify-chain (requires admin) -> 503
    response = await test_client.get("/api/nodes/verify-chain", headers=auth_headers("admin"))
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    # Call list nodes (requires operator) -> 503
    response = await test_client.get("/api/nodes", headers=auth_headers("operator"))
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
