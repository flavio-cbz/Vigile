import os
os.environ["LLM_BASE_URL"] = "http://test-llm:8000/v1"
os.environ["LLM_API_KEY"] = "test-key"
os.environ["LLM_MODEL"] = "test-model"
os.environ["TESTING"] = "true"

import pytest
import aiosqlite
import tempfile
import shutil
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from master.core.security_manager import SecurityManager
from master.core.node_manager import NodeManager
from master.core.plugin_manager import PluginManager
from master.db.database import init_db, close_db, reset_db
from master.db.migrations import run_migrations


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
async def db(temp_dir):
    db_path = os.path.join(temp_dir, "test.db")
    await reset_db()
    conn = await init_db(db_path)
    await run_migrations(conn)
    yield conn
    await close_db()
    await reset_db()


@pytest.fixture(autouse=True)
def security() -> SecurityManager:
    import master.core.security_manager as sm
    if sm._security_instance is None:
        sm.init_security(
            server_secret="test_secret",
            jwt_secret="test_jwt",
            master_private_key=Ed25519PrivateKey.generate(),
        )
    return sm.get_security_instance()


@pytest.fixture
def node_manager() -> NodeManager:
    return NodeManager()


@pytest.fixture
def plugin_manager() -> PluginManager:
    return PluginManager()
