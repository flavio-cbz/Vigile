import asyncio
import hashlib
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from master.api import deps
from master.config import settings
from master.main import app


@pytest.fixture
async def client(db):
    from httpx import ASGITransport, AsyncClient

    app.dependency_overrides[deps.get_db] = lambda: db
    app.state.master_url = "http://test"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)


@pytest.mark.asyncio
async def test_offline_mode_serves_local_binary(temp_dir, client, monkeypatch):
    """When OFFLINE_MODE=true, the endpoint serves from worker_binary_local_dir."""
    monkeypatch.setattr(settings, "offline_mode", True)
    monkeypatch.setattr(settings, "worker_binary_local_dir", temp_dir)

    os_arch_dir = Path(temp_dir) / "linux" / "amd64"
    os_arch_dir.mkdir(parents=True)

    fake_binary = b"\x7fELF\x00fake-worker-binary-content-for-offline-test"
    fake_sha256 = hashlib.sha256(fake_binary).hexdigest()

    (os_arch_dir / "worker").write_bytes(fake_binary)
    (os_arch_dir / "worker.sha256").write_text(fake_sha256 + "  worker\n")

    # Test binary download
    resp = await client.get("/api/nodes/binary/linux/amd64/worker")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.content == fake_binary
    assert resp.headers["content-type"] == "application/octet-stream"

    resp = await client.get("/api/nodes/binary/linux/amd64/worker.sha256")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.text.strip() == f"{fake_sha256}  worker"


@pytest.mark.asyncio
async def test_offline_mode_404_when_missing(temp_dir, client, monkeypatch):
    """When OFFLINE_MODE=true and no binary exists, return 404 with clear message."""
    empty_dir = Path(temp_dir) / "empty_binaries"
    empty_dir.mkdir()

    monkeypatch.setattr(settings, "offline_mode", True)
    monkeypatch.setattr(settings, "worker_binary_local_dir", str(empty_dir))

    resp = await client.get("/api/nodes/binary/linux/amd64/worker")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert "No local binary found" in resp.json()["detail"]

    resp = await client.get("/api/nodes/binary/linux/amd64/worker.sha256")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert "No local sha256 found" in resp.json()["detail"]


def test_kickstart_supports_custom_ca():
    """Verify the kickstart script template contains --ca-bundle, --cacert, CUSTOM_CA_BUNDLE, and --offline."""
    from master.api.nodes import KICKSTART_TEMPLATE

    assert "--ca-bundle" in KICKSTART_TEMPLATE, "Missing --ca-bundle argument parsing"
    assert "--cacert" in KICKSTART_TEMPLATE, "Missing --cacert usage in curl commands"
    assert "CUSTOM_CA_BUNDLE" in KICKSTART_TEMPLATE, "Missing CUSTOM_CA_BUNDLE env var fallback"
    assert "--offline" in KICKSTART_TEMPLATE, "Missing --offline flag in argument parsing"
    assert "curl $CURL_CA_OPTS" in KICKSTART_TEMPLATE, "Missing $CURL_CA_OPTS in curl invocations"


@pytest.mark.asyncio
async def test_auto_update_skipped_in_offline_mode(monkeypatch):
    """When OFFLINE_MODE=true, auto_update_workers_task does NOT fetch the manifest."""
    monkeypatch.setattr(settings, "offline_mode", True)
    monkeypatch.setattr(settings, "auto_update_workers", True)

    async_sleep = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", async_sleep)

    with patch("master.api.worker_binary._fetch_manifest", new_callable=AsyncMock) as mock_fetch:
        from master.main import auto_update_workers_task

        mock_db = AsyncMock()
        mock_nm = AsyncMock()

        task = asyncio.create_task(auto_update_workers_task(mock_db, mock_nm, settings))
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_offline_mode_online_mode_still_works(temp_dir, client, monkeypatch):
    """Online mode (offline_mode=false) should NOT serve from worker_binary_local_dir."""
    # Place a binary in the local dir — it should NOT be served when offline_mode is False
    os_arch_dir = Path(temp_dir) / "linux" / "amd64"
    os_arch_dir.mkdir(parents=True)
    (os_arch_dir / "worker").write_bytes(b"local-binary-should-not-be-served")
    (os_arch_dir / "worker.sha256").write_text("deadbeef  worker\n")

    monkeypatch.setattr(settings, "offline_mode", False)
    monkeypatch.setattr(settings, "worker_binary_local_dir", str(temp_dir))

    # When not in offline mode and the cache dir doesn't have a cached binary yet,
    # the endpoint will try to fetch from the manifest URL, which will fail since
    # there's no real manifest. We expect a 502 or similar, NOT a 404 (offline path)
    # and NOT the local binary content.
    resp = await client.get("/api/nodes/binary/linux/amd64/worker")
    # Should NOT be the local binary (which returns 200)
    assert resp.status_code != 200
    # Should not serve the local content
    if resp.content:
        assert resp.content != b"local-binary-should-not-be-served"
