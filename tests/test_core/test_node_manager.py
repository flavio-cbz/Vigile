import asyncio
import time
import unittest.mock as mock
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from master.core.node_manager import ActiveConnection, NodeManager, NodeState


class DummyWebSocket:
    def __init__(self):
        self.sent_messages = []
        self.closed = False
        self.close_code = None
        self.close_reason = None

    async def send_json(self, data: dict):
        self.sent_messages.append(data)

    async def close(self, code: int = 1000, reason: str = ""):
        self.closed = True
        self.close_code = code
        self.close_reason = reason


@pytest.mark.asyncio
async def test_node_manager_lifecycle(db: aiosqlite.Connection, node_manager: NodeManager):
    # Create a node
    node_id = await node_manager.create_node(db, name="test-node-01", ip_prefix="10.0.")
    assert len(node_id) == 36

    # Fetch it
    node = await node_manager.get_node(db, node_id)
    assert node is not None
    assert node["state"] == "PENDING"
    assert node["name"] == "test-node-01"

    # Valid transition PENDING → ENROLLING
    await node_manager.transition_state(db, node_id, NodeState.ENROLLING)
    node = await node_manager.get_node(db, node_id)
    assert node["state"] == "ENROLLING"

    # Invalid transition ENROLLING → LOST (not allowed directly)
    with pytest.raises(ValueError):
        await node_manager.transition_state(db, node_id, NodeState.LOST)

    # Valid: ENROLLING → CONNECTED
    await node_manager.transition_state(db, node_id, NodeState.CONNECTED)
    node = await node_manager.get_node(db, node_id)
    assert node["state"] == "CONNECTED"

    # Test RECONNECTING → CONNECTED (reconnection path)
    await node_manager.transition_state(db, node_id, NodeState.RECONNECTING)
    await node_manager.transition_state(db, node_id, NodeState.CONNECTED)
    node = await node_manager.get_node(db, node_id)
    assert node["state"] == "CONNECTED"

    # list_nodes
    nodes = await node_manager.list_nodes(db)
    assert isinstance(nodes, list) and len(nodes) >= 1

    # list_nodes with state filter
    pending_nodes = await node_manager.list_nodes(db, state="PENDING")
    assert all(n["state"] == "PENDING" for n in pending_nodes)

    # is_connected (no real WS)
    assert not await node_manager.is_connected(node_id)

    # Test invalid field in extra_fields
    with pytest.raises(ValueError):
        await node_manager.transition_state(
            db, node_id, NodeState.LOST, extra_fields={"invalid_field": "x"}
        )


@pytest.mark.asyncio
async def test_node_manager_connections(node_manager: NodeManager):
    node_id = "test-node-conn-1"
    ws1 = DummyWebSocket()
    ws2 = DummyWebSocket()

    # Register first connection
    conn1 = await node_manager.register_connection(node_id, ws1)
    assert isinstance(conn1, ActiveConnection)
    assert conn1.node_id == node_id
    assert conn1.websocket == ws1
    assert await node_manager.is_connected(node_id)
    assert node_manager.connected_node_ids() == [node_id]

    # Re-register (replaces connection)
    conn2 = await node_manager.register_connection(node_id, ws2)
    assert conn2.websocket == ws2
    assert ws1.closed
    assert ws1.close_code == 4400
    assert not ws2.closed

    # Get connection
    fetched = await node_manager.get_connection(node_id)
    assert fetched == conn2

    # Touch heartbeat
    initial_hb = conn2.last_heartbeat
    await asyncio.sleep(0.01)
    await node_manager.touch_heartbeat(node_id)
    assert conn2.last_heartbeat > initial_hb
    assert conn2.heartbeat_age() >= 0

    # Unregister connection
    await node_manager.unregister_connection(node_id)
    assert not await node_manager.is_connected(node_id)
    assert node_manager.connected_node_ids() == []


@pytest.mark.asyncio
async def test_node_manager_intents(node_manager: NodeManager):
    node_id = "test-node-intents"
    ws = DummyWebSocket()
    await node_manager.register_connection(node_id, ws)

    intent = {"action": "TEST", "params": {"x": 1}}

    # Run send_intent in background
    task = asyncio.create_task(node_manager.send_intent(node_id, intent, timeout=1.0))
    await asyncio.sleep(0.05)  # Let it send

    assert len(ws.sent_messages) == 1
    sent = ws.sent_messages[0]
    assert sent["action"] == "TEST"
    assert sent["type"] == "INTENT"
    intent_id = sent["intent_id"]

    # Resolve intent
    await node_manager.resolve_intent(intent_id, {"success": True, "output": "cool"})
    result = await task
    assert result == {"success": True, "output": "cool"}

    # Test send_intent on disconnected node
    with pytest.raises(RuntimeError):
        await node_manager.send_intent("missing-node", {"action": "TEST"})

    # Test send_intent timeout
    await node_manager.register_connection(node_id, ws)
    with pytest.raises(TimeoutError):
        await node_manager.send_intent(node_id, {"action": "TEST"}, timeout=0.01)


@pytest.mark.asyncio
async def test_node_manager_revocation(db: aiosqlite.Connection, node_manager: NodeManager):
    node_id = await node_manager.create_node(db, name="revoked-node")
    ws = DummyWebSocket()
    await node_manager.register_connection(node_id, ws)

    # Insert a dummy worker token so we can check if it gets revoked
    await db.execute(
        "INSERT INTO worker_tokens (id, node_id, token_hash, issued_at, rotation_due, expires_at, revoked) VALUES (?, ?, ?, ?, ?, ?, 0)",
        ("token_id_1", node_id, "dummy_hash", time.time(), time.time() + 3600, time.time() + 7200),
    )
    await db.commit()

    await node_manager.revoke_node(db, node_id, revoked_by="admin")

    # Verify node state in DB
    node = await node_manager.get_node(db, node_id)
    assert node["state"] == "REVOKED"

    # Verify connection dropped
    assert ws.closed
    assert ws.close_code == 4403
    assert not await node_manager.is_connected(node_id)

    # Verify token revoked in DB
    async with db.execute(
        "SELECT revoked, revoked_by FROM worker_tokens WHERE node_id = ?", (node_id,)
    ) as cur:
        row = await cur.fetchone()
        assert row["revoked"] == 1
        assert row["revoked_by"] == "admin"


@pytest.mark.asyncio
async def test_node_manager_heartbeat_monitor(db: aiosqlite.Connection, node_manager: NodeManager):
    # Set up global DB connection mock/hack if needed
    import master.core.node_manager as nm

    original_get_db = nm.get_db_conn
    nm.get_db_conn = lambda: db

    try:
        node_id_1 = await node_manager.create_node(db, name="node-1")
        node_id_2 = await node_manager.create_node(db, name="node-2")

        # Set transition limits
        await node_manager.transition_state(db, node_id_1, NodeState.ENROLLING)
        await node_manager.transition_state(db, node_id_1, NodeState.CONNECTED)
        await node_manager.transition_state(db, node_id_2, NodeState.ENROLLING)
        await node_manager.transition_state(db, node_id_2, NodeState.CONNECTED)

        ws1 = DummyWebSocket()
        ws2 = DummyWebSocket()
        conn1 = await node_manager.register_connection(node_id_1, ws1)
        conn2 = await node_manager.register_connection(node_id_2, ws2)

        # Make conn1 age past lost_threshold
        conn1.last_heartbeat = time.time() - 500

        # Execute check heartbeats
        await node_manager._check_heartbeats(lost_threshold=300, stale_threshold=86400)

        # node-1 should be LOST and disconnected
        assert not await node_manager.is_connected(node_id_1)
        node1 = await node_manager.get_node(db, node_id_1)
        assert node1["state"] == "LOST"

        # node-2 should still be CONNECTED
        assert await node_manager.is_connected(node_id_2)
        node2 = await node_manager.get_node(db, node_id_2)
        assert node2["state"] == "CONNECTED"

        # Now test LOST -> STALE transition
        # We manually update database last_heartbeat for node-1
        await db.execute(
            "UPDATE nodes SET last_heartbeat = ? WHERE id = ?", (time.time() - 90000, node_id_1)
        )
        await db.commit()

        # Run check heartbeats again with stale_threshold=80000
        await node_manager._check_heartbeats(lost_threshold=300, stale_threshold=80000)
        node1 = await node_manager.get_node(db, node_id_1)
        assert node1["state"] == "STALE"

    finally:
        nm.get_db_conn = original_get_db


@pytest.mark.asyncio
async def test_node_manager_startup_shutdown(node_manager: NodeManager):
    ws = DummyWebSocket()
    await node_manager.register_connection("n1", ws)

    # Start monitor
    await node_manager.start(heartbeat_interval=1, lost_threshold=5, stale_threshold=10)
    assert node_manager._monitor_task is not None
    assert not node_manager._monitor_task.done()

    # Stop monitor
    await node_manager.stop()
    assert node_manager._monitor_task.done()
    assert ws.closed
    assert ws.close_code == 1001
    assert node_manager.connected_node_ids() == []


@pytest.mark.asyncio
async def test_cleanup_stale_intents(node_manager: NodeManager):
    # Setup some futures
    loop = asyncio.get_running_loop()
    f1 = loop.create_future()
    f2 = loop.create_future()
    f2.set_result(True)

    node_manager._pending_intents["i1"] = f1
    node_manager._pending_intents["i2"] = f2

    count = node_manager._cleanup_stale_intents()
    assert count == 1
    assert "i1" in node_manager._pending_intents
    assert "i2" not in node_manager._pending_intents


@pytest.mark.asyncio
async def test_node_manager_websocket_close_exceptions(
    db: aiosqlite.Connection, node_manager: NodeManager
):
    node_id = "test-node-ws-exc"
    ws = DummyWebSocket()

    async def bad_close(*args, **kwargs):
        raise RuntimeError("Websocket close failed")

    ws.close = bad_close

    # Register first connection
    await node_manager.register_connection(node_id, ws)

    # Register second connection (replaces old one, old close will raise exception)
    ws2 = DummyWebSocket()
    await node_manager.register_connection(node_id, ws2)
    assert not ws2.closed

    # Register old connection again, and test exception on revoke_node
    await node_manager.register_connection(node_id, ws)
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) VALUES (?, 'name', 'CONNECTED', ?, ?)",
        (node_id, time.time(), time.time()),
    )
    await db.commit()
    await node_manager.revoke_node(db, node_id, revoked_by="admin")
    # Exception is caught and ignored, code doesn't crash

    # Register connection again, and test exception on stop()
    await node_manager.register_connection(node_id, ws)
    await node_manager.stop()
    # Exception is caught and ignored, code doesn't crash


@pytest.mark.asyncio
async def test_node_manager_transition_nonexistent_node(
    db: aiosqlite.Connection, node_manager: NodeManager
):
    with pytest.raises(ValueError) as excinfo:
        await node_manager.transition_state(db, "nonexistent-node-id", NodeState.LOST)
    assert "node not found" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_node_manager_unregister_cancels_pending_intents(node_manager: NodeManager):
    node_id = "test-node-cancel-intents"
    ws = DummyWebSocket()
    await node_manager.register_connection(node_id, ws)

    intent = {"action": "TEST"}
    task = asyncio.create_task(node_manager.send_intent(node_id, intent, timeout=10.0))
    await asyncio.sleep(0.01)

    # Now unregister connection, which should cancel the pending intent future
    await node_manager.unregister_connection(node_id)
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_node_manager_monitor_loop_and_exceptions(
    db: aiosqlite.Connection, node_manager: NodeManager
):
    import master.core.node_manager as nm

    original_get_db = nm.get_db_conn
    nm.get_db_conn = lambda: db

    try:
        # Mock _check_heartbeats to raise an exception once to cover exception branch in monitor loop
        calls = 0
        original_check_hb = node_manager._check_heartbeats

        async def mock_check_heartbeats(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("Db error in heartbeat checker")
            return await original_check_hb(*args, **kwargs)

        node_manager._check_heartbeats = mock_check_heartbeats

        # Setup a pending intent future to test intent cleanup within monitor loop
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        future.set_result(True)
        node_manager._pending_intents["stale_int_id"] = future

        # Mock asyncio.sleep to run virtualized tiny sleep durations instantly
        sleep_count = 0
        original_sleep = asyncio.sleep

        async def mock_sleep(delay):
            nonlocal sleep_count
            if delay < 0.01:
                sleep_count += 1
                await original_sleep(0)
            else:
                await original_sleep(delay)

        with mock.patch("asyncio.sleep", mock_sleep):
            # Start the monitor with extremely small interval to quickly complete 10+ cycles
            await node_manager.start(
                heartbeat_interval=0.0001, lost_threshold=5, stale_threshold=10
            )

            # Wait deterministically until calls reaches at least 12
            for _ in range(50):
                if calls >= 12:
                    break
                await original_sleep(0.01)

            await node_manager.stop()

        # The future should be cleaned up by the loop's stale intents cleanup
        assert "stale_int_id" not in node_manager._pending_intents
        assert calls >= 10

        # Test exception transitions inside _check_heartbeats
        node_id_1 = await node_manager.create_node(db, name="node-err-1")
        await node_manager.transition_state(db, node_id_1, NodeState.ENROLLING)
        await node_manager.transition_state(db, node_id_1, NodeState.CONNECTED)

        ws1 = DummyWebSocket()
        conn1 = await node_manager.register_connection(node_id_1, ws1)
        conn1.last_heartbeat = time.time() - 500

        # Mock transition_state to raise exception during transition to LOST
        async def bad_transition(*args, **kwargs):
            raise RuntimeError("Database constraint failed")

        node_manager.transition_state = bad_transition
        # Executing check heartbeats should not crash, it will log the exception
        await original_check_hb(lost_threshold=300, stale_threshold=86400)

        # Do the same for STALE transition exception
        # We manually insert a node in LOST state in the database
        node_id_2 = "node-err-2"
        await db.execute(
            "INSERT INTO nodes (id, name, state, created_at, updated_at, last_heartbeat) VALUES (?, 'node-err-2', 'LOST', ?, ?, ?)",
            (node_id_2, time.time(), time.time(), time.time() - 90000),
        )
        await db.commit()

        # Executing check heartbeats should log the transition to STALE exception and not crash
        await original_check_hb(lost_threshold=300, stale_threshold=80000)

    finally:
        nm.get_db_conn = original_get_db


@pytest.mark.asyncio
async def test_re_enrollment_transitions(db: aiosqlite.Connection, node_manager: NodeManager):
    node_id = await node_manager.create_node(db, name="reenroll-node")

    # 1. PENDING -> ENROLLING -> CONNECTED
    await node_manager.transition_state(db, node_id, NodeState.ENROLLING)
    await node_manager.transition_state(db, node_id, NodeState.CONNECTED)

    # 2. CONNECTED -> LOST -> ENROLLING (Re-enrollment)
    await node_manager.transition_state(db, node_id, NodeState.LOST)
    await node_manager.transition_state(db, node_id, NodeState.ENROLLING)
    await node_manager.transition_state(db, node_id, NodeState.CONNECTED)

    # 3. CONNECTED -> LOST -> STALE -> ENROLLING (Re-enrollment)
    await node_manager.transition_state(db, node_id, NodeState.LOST)
    await node_manager.transition_state(db, node_id, NodeState.STALE)
    await node_manager.transition_state(db, node_id, NodeState.ENROLLING)
    await node_manager.transition_state(db, node_id, NodeState.CONNECTED)

    # 4. CONNECTED -> RECONNECTING -> ENROLLING (Re-enrollment)
    await node_manager.transition_state(db, node_id, NodeState.RECONNECTING)
    await node_manager.transition_state(db, node_id, NodeState.ENROLLING)


@pytest.mark.asyncio
async def test_send_intent_finally_cleanup_on_cancel(node_manager: NodeManager):
    node_id = "test-node-finally-cancel"
    ws = DummyWebSocket()
    await node_manager.register_connection(node_id, ws)

    intent = {"action": "TEST"}
    task = asyncio.create_task(node_manager.send_intent(node_id, intent, timeout=10.0))
    await asyncio.sleep(0.01)

    # Assert intent is registered
    intent_id = list(node_manager._pending_intents.keys())[0]
    assert intent_id in node_manager._pending_intents
    assert intent_id in node_manager._intent_nodes

    # Cancel the task
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Assert dictionary is cleaned up after cancellation due to finally block
    assert intent_id not in node_manager._pending_intents
    assert intent_id not in node_manager._intent_nodes
