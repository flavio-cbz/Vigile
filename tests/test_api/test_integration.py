import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_integration_flow():
    """
    Vigile API Integration Tests.
    Verifies the entire API lifecycle against a running server.
    Ensure the dev server is running on http://127.0.0.1:8000.
    """
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 1. System Endpoints & Documentation
        r = await client.get("/health")
        assert r.status_code == 200, f"Health check failed: {r.status_code}"

        r = await client.get("/api/openapi.json")
        assert r.status_code == 200, f"OpenAPI schema failed: {r.status_code}"
        schema = r.json()
        assert "paths" in schema
        assert len(schema["paths"]) > 0

        # 2. Authentication Flow with Force Password Change Handling
        # We try to login with a new secure password first (in case it was already changed)
        secure_password = "demo_secure_password"
        username = "admin"
        r = await client.post("/api/auth/login", json={"username": username, "password": secure_password})
        
        if r.status_code != 200:
            # Try with the default "admin" password
            r = await client.post("/api/auth/login", json={"username": username, "password": "admin"})
            if r.status_code != 200:
                # If that failed, fall back to "demo" username
                username = "demo"
                r = await client.post("/api/auth/login", json={"username": username, "password": secure_password})
                if r.status_code != 200:
                    r = await client.post("/api/auth/login", json={"username": username, "password": "demo"})
            
            assert r.status_code == 200, f"Login failed for both admin and demo: {r.status_code}"
            
            tokens = r.json()
            access_token = tokens["access_token"]
            headers = {"Authorization": f"Bearer {access_token}"}
            
            # Check if must_change_password is required
            r_me = await client.get("/api/auth/me", headers=headers)
            if r_me.status_code == 403:
                assert r_me.json().get("code") == "MUST_CHANGE_PASSWORD"
                
                # Perform force change-password
                old_password = "demo" if username == "demo" else "admin"
                r_change = await client.post(
                    "/api/auth/change-password",
                    headers=headers,
                    json={"old_password": old_password, "new_password": secure_password}
                )
                assert r_change.status_code == 204, f"Password change failed: {r_change.status_code}"
                
                # Re-authenticate with new password
                r_login = await client.post("/api/auth/login", json={"username": username, "password": secure_password})
                assert r_login.status_code == 200, f"Login with new password failed: {r_login.status_code}"
                tokens = r_login.json()
            else:
                assert r_me.status_code == 200, f"Expected 200 or 403, got {r_me.status_code}"
        else:
            tokens = r.json()

        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        # Verify current user
        r = await client.get("/api/auth/me", headers=headers)
        assert r.status_code == 200
        assert r.json().get("role") == "admin"

        # Refresh token rotation
        r = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert r.status_code == 200
        tokens = r.json()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        # 3. Nodes Management
        # Generate Join Token
        r = await client.post("/api/nodes/generate-join", headers=headers, json={
            "name": "test-api-node",
            "ip_prefix": ""
        })
        assert r.status_code == 201, f"Join token generation failed: {r.status_code}"
        data = r.json()
        node_id = data["node_id"]
        assert "node_id" in data
        assert "token" in data
        assert "curl_command" in data

        # List Nodes
        r = await client.get("/api/nodes", headers=headers)
        assert r.status_code == 200
        nodes = r.json()
        assert isinstance(nodes, list)
        found = any(n["id"] == node_id for n in nodes)
        assert found, "Newly created node not found in nodes list"

        # Get Single Node
        r = await client.get(f"/api/nodes/{node_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["state"] == "PENDING"

        # Get Kickstart Script (Public)
        r = await client.get("/api/nodes/kickstart.sh")
        assert r.status_code == 200
        assert r.text.startswith("#!/usr/env bash") or r.text.startswith("#!/usr/bin/env bash")

        # Revoke Node
        r = await client.delete(f"/api/nodes/{node_id}", headers=headers)
        assert r.status_code == 204

        # Verify Revoked State
        r = await client.get(f"/api/nodes/{node_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["state"] == "REVOKED"

        # 4. Admin, Audit, and Debug Endpoints
        r = await client.get("/api/admin/audit-verify", headers=headers)
        assert r.status_code == 200

        r = await client.get("/api/admin/nodes/connections", headers=headers)
        assert r.status_code == 200

        r = await client.get("/api/admin/plugins", headers=headers)
        assert r.status_code == 200

        # Paginated Audit log API
        r = await client.get("/api/audit?limit=10&offset=0", headers=headers)
        assert r.status_code == 200
        audit_res = r.json()
        assert "entries" in audit_res
        assert "total" in audit_res
