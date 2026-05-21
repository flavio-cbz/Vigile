import pytest
import aiosqlite
from master.core.node_manager import NodeManager, NodeState


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
        await node_manager.transition_state(db, node_id, NodeState.LOST, extra_fields={"invalid_field": "x"})
