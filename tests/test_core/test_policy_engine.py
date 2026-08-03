import json
import pytest
import aiosqlite
from master.core.security_manager import SecurityManager
from master.core.policy_engine import PolicyEngine
from master.db.models import ALL_TABLES, CREATE_INDEXES


@pytest.fixture
async def test_db():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    for ddl in ALL_TABLES:
        await db.execute(ddl)
    for idx in CREATE_INDEXES:
        await db.execute(idx)
    await db.commit()
    yield db
    await db.close()


@pytest.fixture
def security():
    return SecurityManager(server_secret="sec", jwt_secret="jwt")


@pytest.mark.asyncio
async def test_policy_engine_compile_bootstrap(test_db, security):
    pe = PolicyEngine(security)
    node_id = "node-test-1"

    bundle = await pe.compile_policy_bundle(test_db, node_id)
    assert bundle["node_id"] == node_id
    assert bundle["policy_version"] == 1
    assert len(bundle["rules"]) == 3  # Bootstrap rules
    assert "signature" in bundle
    assert len(bundle["signature"]) > 0


@pytest.mark.asyncio
async def test_policy_engine_compile_with_grants(test_db, security):
    pe = PolicyEngine(security)
    node_id = "node-test-2"

    # Insert a grant
    await test_db.execute(
        """
        INSERT INTO plugin_grants (id, plugin_id, node_id, action, target_kind, target_id, limits_json, granted_by, granted_at)
        VALUES ('g1', 'nginx', ?, 'RELOAD_SERVICE', 'systemd_service', 'nginx.service', '{"timeout_seconds": 15}', 'admin', 1000.0)
        """,
        (node_id,),
    )
    await test_db.commit()

    bundle = await pe.compile_policy_bundle(test_db, node_id)
    assert bundle["node_id"] == node_id
    assert bundle["policy_version"] == 1
    assert len(bundle["rules"]) == 1
    assert bundle["rules"][0]["action"] == "RELOAD_SERVICE"
    assert bundle["rules"][0]["target"] == {"kind": "systemd_service", "id": "nginx.service"}
