#!/usr/bin/env python3
"""
YouCloud AI Admin — API Integration Tests
Teste toutes les routes de l'API REST contre un serveur en cours d'exécution.
Assurez-vous que le serveur tourne sur http://localhost:8000.
"""

import asyncio
import httpx
import sys

BASE_URL = "http://127.0.0.1:8000"
PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"

results = []

def check(name: str, condition: bool, detail: str = ""):
    icon = PASS if condition else FAIL
    print(f"  {icon} {name}" + (f" ({detail})" if detail else ""))
    results.append((name, condition))
    return condition

async def run_tests():
    print(f"Testing API at {BASE_URL}...\n")
    
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 1. System Endpoints & Documentation
        print("🛠️  System & OpenAPI Docs")
        
        # Check Health
        r = await client.get("/health")
        check("GET /health", r.status_code == 200, f"HTTP {r.status_code}")
        
        # Check OpenAPI Schema (This powers Swagger and ReDoc)
        r = await client.get("/api/openapi.json")
        check("GET /api/openapi.json", r.status_code == 200, "Schema is required for Swagger/ReDoc")
        if r.status_code == 200:
            schema = r.json()
            check("OpenAPI Schema has paths", "paths" in schema and len(schema["paths"]) > 0)
            
        # 2. Authentication
        print("\n🔐 Authentication")
        
        # Login
        r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        check("POST /api/auth/login (admin/admin)", r.status_code == 200, f"HTTP {r.status_code}")
        
        if r.status_code != 200:
            print("❌ Cannot proceed without auth token. Aborting.")
            return

        tokens = r.json()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Get Current User
        r = await client.get("/api/auth/me", headers=headers)
        check("GET /api/auth/me", r.status_code == 200)
        if r.status_code == 200:
            check("User role is admin", r.json().get("role") == "admin")
            
        # Refresh Token
        r = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        check("POST /api/auth/refresh", r.status_code == 200)
        if r.status_code == 200:
            access_token = r.json()["access_token"]  # Use new token
            headers = {"Authorization": f"Bearer {access_token}"}

        # 3. Nodes Management
        print("\n🖥️  Nodes Management")
        
        # Generate Join Token
        r = await client.post("/api/nodes/generate-join", headers=headers, json={
            "name": "test-api-node",
            "ip_prefix": ""
        })
        check("POST /api/nodes/generate-join", r.status_code == 201, f"HTTP {r.status_code}")
        
        node_id = None
        if r.status_code == 201:
            data = r.json()
            node_id = data["node_id"]
            check("Response contains node_id and token", "node_id" in data and "token" in data)
            check("Curl command generated", "curl_command" in data)

        # List Nodes
        r = await client.get("/api/nodes", headers=headers)
        check("GET /api/nodes", r.status_code == 200)
        if r.status_code == 200:
            nodes = r.json()
            check("Nodes list is an array", isinstance(nodes, list))
            if node_id:
                found = any(n["id"] == node_id for n in nodes)
                check("Newly created node is in the list", found)

        # Get Single Node
        if node_id:
            r = await client.get(f"/api/nodes/{node_id}", headers=headers)
            check("GET /api/nodes/{node_id}", r.status_code == 200)
            if r.status_code == 200:
                check("Node state is PENDING", r.json()["state"] == "PENDING")

        # Get Kickstart Script (Public)
        r = await client.get("/api/nodes/kickstart.sh")
        check("GET /api/nodes/kickstart.sh (Public)", r.status_code == 200)
        if r.status_code == 200:
            check("Script is a bash script", r.text.startswith("#!/usr/bin/env bash"))

        # Revoke Node
        if node_id:
            r = await client.delete(f"/api/nodes/{node_id}", headers=headers)
            check("DELETE /api/nodes/{node_id}", r.status_code == 204)
            
            # Verify it's marked as revoked
            r = await client.get(f"/api/nodes/{node_id}", headers=headers)
            check("Node state is now REVOKED", r.status_code == 200 and r.json()["state"] == "REVOKED")

        # 4. Admin & Debug Endpoints
        print("\n📋 Admin & Audit Endpoints")
        
        r = await client.get("/api/admin/audit-verify", headers=headers)
        check("GET /api/admin/audit-verify", r.status_code == 200, "Should verify unbroken chain")
        
        r = await client.get("/api/admin/nodes/connections", headers=headers)
        check("GET /api/admin/nodes/connections", r.status_code == 200)
        
        r = await client.get("/api/admin/plugins", headers=headers)
        check("GET /api/admin/plugins", r.status_code == 200)

        # Print Summary
        print("\n" + "=" * 60)
        passed = sum(1 for _, ok in results if ok)
        total = len(results)
        if passed == total:
            print(f"🎉 All {total} API integration tests passed!")
        else:
            print(f"❌ {passed}/{total} passed. Some tests failed.")
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_tests())
