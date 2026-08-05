from __future__ import annotations

"""
Tests for the Plex Integration Plugin.
"""

import json
import time
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
import httpx

from master.plugins.plex import (
    detect_plex_instance,
    _on_status_report,
    _get_plex_client_and_url,
    detect_route,
    sessions_route,
    library_route,
    users_route,
    auth_pin_route,
    auth_verify_route,
    servers_route,
    save_server_config_route,
    VerifyPinRequest,
)

@pytest.mark.asyncio
async def test_detect_plex_instance_docker(db: aiosqlite.Connection):
    node_id = "test-plex-node"
    # Insert node with running Plex docker container
    await db.execute(
        """
        INSERT INTO nodes (id, name, hostname, state, cached_containers_json, created_at, updated_at)
        VALUES (?, 'Test Node Plex', 'test-host', 'CONNECTED', ?, ?, ?)
        """,
        (
            node_id,
            json.dumps([
                {
                    "name": "plex-media-server",
                    "image": "plexinc/pms-docker",
                    "state": "running",
                    "ports": [{"ContainerPort": 32400, "HostPort": 32400}]
                }
            ]),
            time.time(),
            time.time(),
        ),
    )
    await db.commit()

    detection = await detect_plex_instance(node_id, db)
    assert detection["detected"] is True
    assert detection["type"] == "docker"
    assert detection["port"] == 32400
    assert detection["container_name"] == "plex-media-server"

@pytest.mark.asyncio
async def test_detect_plex_instance_native(db: aiosqlite.Connection):
    node_id = "test-plex-native"
    # Insert node with Plex in systemd services
    await db.execute(
        """
        INSERT INTO nodes (id, name, hostname, state, cached_services_json, created_at, updated_at)
        VALUES (?, 'Test Node Native', 'test-host-native', 'CONNECTED', ?, ?, ?)
        """,
        (
            node_id,
            json.dumps([
                {
                    "service": "plexmediaserver.service",
                    "state": "active",
                }
            ]),
            time.time(),
            time.time(),
        ),
    )
    await db.commit()

    detection = await detect_plex_instance(node_id, db)
    assert detection["detected"] is True
    assert detection["type"] == "native"
    assert detection["port"] == 32400
    assert detection["service_name"] == "plexmediaserver.service"

@pytest.mark.asyncio
async def test_on_status_report_high_load_logs_diagnostic(db: aiosqlite.Connection):
    node_id = "test-plex-high-load"
    now = time.time()
    
    # 1. Setup node, configuration, and genesis audit entry
    await db.execute(
        """
        INSERT INTO nodes (id, name, hostname, state, cached_containers_json, created_at, updated_at)
        VALUES (?, 'Test High Load Node', 'test-host', 'CONNECTED', ?, ?, ?)
        """,
        (
            node_id,
            json.dumps([{"name": "plex", "state": "running"}]),
            now,
            now,
        ),
    )
    await db.execute(
        "INSERT INTO plugins (id, enabled, config_json) VALUES ('plex', 1, ?)",
        (json.dumps({"plex_token": "mock-token-xyz", "cpu_threshold": 80}),),
    )
    await db.commit()

    # 2. Mock Plex API response for active sessions
    mock_sessions = {
        "MediaContainer": {
            "size": 1,
            "Metadata": [
                {
                    "title": "Inception",
                    "type": "movie",
                    "User": {"title": "flavio"},
                    "Player": {"state": "playing", "device": "Web"},
                    "TranscodeSession": {
                        "videoDecision": "transcode"
                    }
                }
            ]
        }
    }

    # Use patch to mock httpx AsyncClient
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json = lambda: mock_sessions

        # Trigger high CPU status report (90%)
        snapshot = {"cpu_percent": 90.0}
        await _on_status_report(node_id, snapshot, db=db)

        # Check if audit log diagnostic entry was written
        async with db.execute(
            "SELECT action, details_json FROM audit_log WHERE action = 'PLEX_HIGH_LOAD_DIAGNOSTIC'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == "PLEX_HIGH_LOAD_DIAGNOSTIC"
            details = json.loads(row[1])
            assert details["cpu_percent"] == 90.0
            assert details["sessions_count"] == 1
            assert details["active_sessions"][0]["user"] == "flavio"
            assert details["active_sessions"][0]["title"] == "Inception"
            assert details["active_sessions"][0]["transcode"] is True

@pytest.mark.asyncio
async def test_plex_routes(db: aiosqlite.Connection):
    node_id = "test-plex-routes"
    await db.execute(
        """
        INSERT INTO nodes (id, name, hostname, state, cached_containers_json, created_at, updated_at)
        VALUES (?, 'Test Routes Node', 'test-host', 'CONNECTED', ?, ?, ?)
        """,
        (
            node_id,
            json.dumps([{"name": "plex", "state": "running"}]),
            time.time(),
            time.time(),
        ),
    )
    await db.execute(
        "INSERT INTO plugins (id, enabled, config_json) VALUES ('plex', 1, ?)",
        (json.dumps({"plex_token": "mock-token-xyz"}),),
    )
    await db.commit()

    # Test detect route
    detection = await detect_route(node_id, db=db)
    assert detection["detected"] is True
    assert detection["configured"] is True

    # Test sessions route with mocked API response
    mock_sessions = {
        "MediaContainer": {
            "Metadata": [
                {
                    "title": "Interstellar",
                    "type": "movie",
                    "User": {"title": "alex"},
                    "Player": {"state": "paused", "device": "TV"},
                }
            ]
        }
    }
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json = lambda: mock_sessions

        sessions = await sessions_route(node_id, db=db)
        assert sessions["count"] == 1
        assert sessions["sessions"][0]["title"] == "Interstellar"
        assert sessions["sessions"][0]["user"] == "alex"
        assert sessions["sessions"][0]["transcode"] is False

    # Test library route with mocked API response
    mock_library = {
        "MediaContainer": {
            "Directory": [
                {
                    "key": "1",
                    "title": "Films",
                    "type": "movie",
                }
            ]
        }
    }
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json = lambda: mock_library

        lib = await library_route(node_id, db=db)
        assert lib["count"] == 1
        assert lib["libraries"][0]["title"] == "Films"

    # Test users route with mocked API response
    mock_accounts = {
        "MediaContainer": {
            "Account": [
                {
                    "id": "123",
                    "name": "guest_user",
                }
            ]
        }
    }
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json = lambda: mock_accounts

        users = await users_route(node_id, db=db)
        assert users["count"] == 1
        assert users["users"][0]["name"] == "guest_user"

@pytest.mark.asyncio
async def test_plex_oauth_pin_flow(db: aiosqlite.Connection):
    # 1. Test auth_pin_route
    mock_pin_response = {
        "id": 98765,
        "code": "code123",
    }
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 201
        mock_post.return_value.json = lambda: mock_pin_response

        pin_res = await auth_pin_route(db=db)
        assert pin_res["id"] == 98765
        assert pin_res["code"] == "code123"
        assert "app.plex.tv/auth" in pin_res["auth_url"]

    # 2. Test auth_verify_route when pending
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json = lambda: {"authToken": None}

        verify_res = await auth_verify_route(VerifyPinRequest(pin_id=98765), db=db)
        assert verify_res["authenticated"] is False

    # 3. Test auth_verify_route when authorized
    mock_poll_authorized = {"authToken": "valid-token-abc"}
    mock_user_info = {"username": "plex_admin_user"}

    async def mock_get_router(url, headers=None, **kwargs):
        resp = AsyncMock()
        resp.status_code = 200
        if "pins" in url:
            resp.json = lambda: mock_poll_authorized
        elif "user" in url:
            resp.json = lambda: mock_user_info
        return resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get_router):
        verify_res = await auth_verify_route(VerifyPinRequest(pin_id=98765), db=db)
        assert verify_res["authenticated"] is True
        assert verify_res["token"] == "valid-token-abc"
        assert verify_res["user"] == "plex_admin_user"

@pytest.mark.asyncio
async def test_plex_servers_and_custom_config(db: aiosqlite.Connection):
    # Setup token in DB
    await db.execute(
        "INSERT INTO plugins (id, enabled, config_json) VALUES ('plex', 1, ?)",
        (json.dumps({"plex_token": "valid-token-abc"}),),
    )
    await db.commit()

    # 1. Test servers_route
    mock_resources = [
        {
            "name": "My NAS Plex",
            "product": "Plex Media Server",
            "productVersion": "1.32.0",
            "clientIdentifier": "nas-machine-id-123",
            "provides": "server",
            "owned": True,
            "connections": [
                {
                    "uri": "http://192.168.1.100:32400",
                    "address": "192.168.1.100",
                    "port": 32400,
                    "local": True,
                    "protocol": "http",
                }
            ],
        }
    ]
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json = lambda: mock_resources

        srv_res = await servers_route(db=db)
        assert srv_res["count"] == 1
        assert srv_res["servers"][0]["name"] == "My NAS Plex"
        assert srv_res["servers"][0]["connections"][0]["uri"] == "http://192.168.1.100:32400"

    # 2. Test save_server_config_route
    save_res = await save_server_config_route(
        payload={"server_url": "http://192.168.1.100:32400", "server_name": "My NAS Plex"},
        db=db,
    )
    assert save_res["status"] == "ok"
    assert save_res["config"]["plex_server_url"] == "http://192.168.1.100:32400"

    # 3. Test _get_plex_client_and_url returns configured server_url
    client_info = await _get_plex_client_and_url("any-node", db, save_res["config"])
    assert client_info is not None
    assert client_info[0] == "http://192.168.1.100:32400"
    assert client_info[1] == "valid-token-abc"

@pytest.mark.asyncio
async def test_plex_fastapi_mounted_routes(db: aiosqlite.Connection):
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from master.core.route_registrar import RouteRegistrar
    from master.core.plugin_base import PluginContext
    from master.plugins.plex import PlexPlugin

    app = FastAPI()
    registrar = RouteRegistrar(app)
    ctx = PluginContext(plugin_id="plex", config={}, db=db)
    plugin = PlexPlugin(ctx)
    registrar.mount("plex", plugin.routes, plugin)

    mock_resp = AsyncMock()
    mock_resp.status_code = 201
    mock_resp.json = lambda: {"id": 123, "code": "abcd"}

    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)

    with patch("master.plugins.plex.httpx.AsyncClient", return_value=mock_client_cm):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/plugins/plex/auth/pin")
            assert resp.status_code == 200
            assert resp.json()["code"] == "abcd"

@pytest.mark.asyncio
async def test_plex_fastapi_mounted_routes_with_staticfiles(db: aiosqlite.Connection, tmp_path):
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from httpx import AsyncClient, ASGITransport
    from master.core.route_registrar import RouteRegistrar
    from master.core.plugin_base import PluginContext
    from master.plugins.plex import PlexPlugin

    app = FastAPI()
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    registrar = RouteRegistrar(app)
    ctx = PluginContext(plugin_id="plex", config={}, db=db)
    plugin = PlexPlugin(ctx)
    registrar.mount("plex", plugin.routes, plugin)

    mock_resp = AsyncMock()
    mock_resp.status_code = 201
    mock_resp.json = lambda: {"id": 123, "code": "abcd"}

    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)

    with patch("master.plugins.plex.httpx.AsyncClient", return_value=mock_client_cm):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/plugins/plex/auth/pin")
            assert resp.status_code == 200
            assert resp.json()["code"] == "abcd"


