#!/usr/bin/env python3
"""
Vigile — Chat API Unit Tests
Tests the /api/chat and /api/chat/proposals endpoints.
"""
import asyncio
import json
import os
import sys
import tempfile

import pathlib
PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent.parent)
sys.path.insert(0, PROJECT_ROOT)

tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_PATH"] = os.path.join(tmpdir, "test_chat.db")
os.environ["MASTER_KEY_PATH"] = os.path.join(tmpdir, "master_chat.key")
os.environ["SERVER_SECRET_KEY"] = "test_secret_chat"
os.environ["JWT_SECRET_KEY"] = "test_jwt_chat"
os.environ["LLM_BASE_URL"] = "http://test-llm:8000/v1"
os.environ["LLM_API_KEY"] = "test-key"
os.environ["LLM_MODEL"] = "test-model"

PASS = "\033[92m\u2713\033[0m"
FAIL = "\033[91m\u2717\033[0m"
results = []

def check(name, condition, detail=""):
    icon = PASS if condition else FAIL
    print(f"  {icon} {name}" + (f" ({detail})" if detail else ""))
    results.append((name, condition))
    return condition

import unittest.mock as mock

from master.db.database import init_db, close_db, reset_db
from master.db.migrations import run_migrations
from master.core.node_manager import node_manager, NodeState
from master.main import app
from master.api import deps
from master.core.security_manager import init_security, get_security_instance
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

init_security(
    server_secret=os.environ["SERVER_SECRET_KEY"],
    jwt_secret=os.environ["JWT_SECRET_KEY"],
    master_private_key=Ed25519PrivateKey.generate(),
)
security = get_security_instance()


def _make_token(role: str = "admin") -> str:
    return security.create_access_token("test-user", "test_user", role)


async def _setup_node(db, name="chat-node") -> str:
    node_id = await node_manager.create_node(db, name=name)
    await node_manager.transition_state(db, node_id, NodeState.ENROLLING)
    await node_manager.transition_state(db, node_id, NodeState.CONNECTED)
    return node_id


async def _run_test(description, test_fn):
    await reset_db()
    db = await init_db()
    await run_migrations(db)
    app.dependency_overrides[deps.get_db] = lambda: db
    try:
        await test_fn(db)
    finally:
        app.dependency_overrides.pop(deps.get_db, None)
        await close_db()
        await reset_db()


async def _request(method, path, token=None, json_body=None):
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, headers=headers, json=json_body)


print("\n\U0001f4ac Chat API Tests")


async def test_chat_unauthorized():
    """No auth token → 401."""
    async def _test(db):
        resp = await _request("POST", "/api/chat", json_body={"message": "hi"})
        check("chat no auth: 401", resp.status_code == 401)
    await _run_test("unauthorized", _test)


async def test_chat_viewer_forbidden():
    """Viewer role → 403."""
    async def _test(db):
        token = _make_token("viewer")
        resp = await _request("POST", "/api/chat", token, {"message": "hi"})
        check("chat viewer: 403", resp.status_code == 403)
    await _run_test("viewer forbidden", _test)


async def test_chat_empty_message():
    """Empty message → 400."""
    async def _test(db):
        token = _make_token()
        resp = await _request("POST", "/api/chat", token, {"message": ""})
        check("chat empty: 400", resp.status_code == 400)
    await _run_test("empty message", _test)


async def test_chat_streams_sse():
    """Chat endpoint returns SSE stream with tokens."""
    async def _test(db):
        # Mock the LLMClient dependency to avoid actual HTTP calls
        mock_llm = mock.AsyncMock()
        async def mock_stream(*args, **kwargs):
            yield {"type": "token", "content": "Hello from AI"}
            yield {"type": "done"}
        mock_llm.stream = mock_stream
        app.dependency_overrides[deps.get_llm_client] = lambda: mock_llm
        try:
            token = _make_token()
            resp = await _request("POST", "/api/chat", token,
                                  {"message": "Hello", "node_id": None})
            check("chat stream: 200", resp.status_code == 200)
            text = resp.text
            check("chat stream: has SSE data", text.startswith("data:"))
            check("chat stream: has token event", '"token"' in text)
            check("chat stream: has Hello", "Hello from AI" in text)
        finally:
            app.dependency_overrides.pop(deps.get_llm_client, None)
    await _run_test("chat sse", _test)


async def test_chat_streams_error():
    """Chat endpoint returns error event on LLM failure."""
    async def _test(db):
        mock_llm = mock.AsyncMock()
        async def mock_stream(*args, **kwargs):
            yield {"type": "error", "detail": "LLM is down"}
            yield {"type": "done"}
        mock_llm.stream = mock_stream
        app.dependency_overrides[deps.get_llm_client] = lambda: mock_llm
        try:
            token = _make_token()
            resp = await _request("POST", "/api/chat", token,
                                  {"message": "Hi", "node_id": None})
            check("chat error: 200", resp.status_code == 200)
            check("chat error: has error event", '"LLM is down"' in resp.text)
        finally:
            app.dependency_overrides.pop(deps.get_llm_client, None)
    await _run_test("chat error", _test)


async def _insert_proposal(db, proposal):
    """Insert a proposal with node_id that exists."""
    data = proposal.to_db_dict()
    await db.execute(
        """INSERT INTO action_proposals (id, node_id, action, params_json,
           reasoning, risk_level, status, created_by, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (data["id"], data["node_id"], data["action"], data["params_json"],
         data["reasoning"], data["risk_level"], data["status"],
         data["created_by"], data["created_at"], data["updated_at"]),
    )
    await db.commit()


async def test_proposals_list():
    """GET /api/chat/proposals returns proposals."""
    async def _test(db):
        node_id = await node_manager.create_node(db, name="test-proposal")
        from master.core.action_proposal import ActionProposal
        p = ActionProposal(node_id=node_id, action="RESTART_CONTAINER",
                           params={"id": "web"}, reasoning="down")
        await _insert_proposal(db, p)
        token = _make_token()
        resp = await _request("GET", "/api/chat/proposals", token)
        check("proposals list: 200", resp.status_code == 200)
        proposals = resp.json()
        check("proposals list: is list", isinstance(proposals, list))
        check("proposals list: has item", len(proposals) >= 1)
    await _run_test("proposals list", _test)


async def test_proposals_get():
    """GET /api/chat/proposals/{id} returns one proposal."""
    async def _test(db):
        node_id = await node_manager.create_node(db, name="test-proposal-get")
        from master.core.action_proposal import ActionProposal
        p = ActionProposal(node_id=node_id, action="RESTART_CONTAINER",
                           params={"id": "web"}, reasoning="down")
        await _insert_proposal(db, p)
        token = _make_token()
        resp = await _request("GET", f"/api/chat/proposals/{p.id}", token)
        check("proposals get: 200", resp.status_code == 200)
        d = resp.json()
        check("proposals get: id matches", d["id"] == p.id)
        check("proposals get: action matches", d["action"] == "RESTART_CONTAINER")
    await _run_test("proposals get", _test)


async def test_proposals_get_not_found():
    """GET /api/chat/proposals/{id} returns 404 on missing."""
    async def _test(db):
        token = _make_token()
        resp = await _request("GET", "/api/chat/proposals/nonexistent", token)
        check("proposals get 404: 404", resp.status_code == 404)
    await _run_test("proposals get 404", _test)


async def test_approve_proposal():
    """POST /api/chat/proposals/{id}/approve approves and executes."""
    async def _test(db):
        node_id = await _setup_node(db, "test-approve")
        from master.core.action_proposal import ActionProposal
        p = ActionProposal(node_id=node_id, action="GET_STATS")
        await _insert_proposal(db, p)
        # Mock send_intent to return success
        orig = node_manager.send_intent
        async def mock_send(*args, **kwargs):
            return {"success": True, "output": "CPU: 10%"}
        node_manager.send_intent = mock_send
        try:
            token = _make_token("admin")
            resp = await _request(
                "POST", f"/api/chat/proposals/{p.id}/approve", token
            )
            check("approve: 200", resp.status_code == 200)
            d = resp.json()
            check("approve: status EXECUTED", d["status"] == "EXECUTED")
            check("approve: approved_by set", d["approved_by"] == "test-user")
            check("approve: executed_at set", d["executed_at"] is not None)
            check("approve: result has output", d.get("result_json") is not None)
        finally:
            node_manager.send_intent = orig
    await _run_test("approve proposal", _test)


async def test_approve_proposal_not_pending():
    """Cannot approve a non-PENDING proposal."""
    async def _test(db):
        node_id = await _setup_node(db, "test-already-approved")
        from master.core.action_proposal import ActionProposal
        p = ActionProposal(node_id=node_id, action="GET_STATS")
        p.approve("user-1")
        await _insert_proposal(db, p)
        # Also update the approved_by field since _insert_proposal doesn't set it
        await db.execute("UPDATE action_proposals SET approved_by = ? WHERE id = ?",
                        (p.approved_by, p.id))
        await db.commit()
        token = _make_token("admin")
        resp = await _request("POST", f"/api/chat/proposals/{p.id}/approve", token)
        check("approve non-pending: 409", resp.status_code == 409)
    await _run_test("approve non-pending", _test)


async def test_reject_proposal():
    """POST /api/chat/proposals/{id}/reject rejects proposal."""
    async def _test(db):
        node_id = await _setup_node(db, "test-reject")
        from master.core.action_proposal import ActionProposal
        p = ActionProposal(node_id=node_id, action="GET_STATS")
        await _insert_proposal(db, p)
        token = _make_token("admin")
        resp = await _request("POST", f"/api/chat/proposals/{p.id}/reject", token,
                             {"reason": "not needed"})
        check("reject: 200", resp.status_code == 200)
        d = resp.json()
        check("reject: status REJECTED", d["status"] == "REJECTED")
        check("reject: rejected_by set", d["rejected_by"] == "test-user")
        check("reject: reason set", d["rejection_reason"] == "not needed")
    await _run_test("reject proposal", _test)


print("\n\U0001f4ac Chat API Tests")
asyncio.run(test_chat_unauthorized())
asyncio.run(test_chat_viewer_forbidden())
asyncio.run(test_chat_empty_message())
asyncio.run(test_chat_streams_sse())
asyncio.run(test_chat_streams_error())
asyncio.run(test_proposals_list())
asyncio.run(test_proposals_get())
asyncio.run(test_proposals_get_not_found())
asyncio.run(test_approve_proposal())
asyncio.run(test_approve_proposal_not_pending())
asyncio.run(test_reject_proposal())

print("\n" + "=" * 60)
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
total = len(results)
print(f"Results: {passed}/{total} passed", end="")
if failed:
    print(f"  ({failed} FAILED)")
    for name, ok in results:
        if not ok:
            print(f"  {FAIL} {name}")
    sys.exit(1)
else:
    print(" \U0001f389")

import shutil
shutil.rmtree(tmpdir, ignore_errors=True)
