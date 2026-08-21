from __future__ import annotations

"""
Tests for the Plex Integration Plugin.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
import httpx
from fastapi import HTTPException, Request

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
    auth_start_route,
    auth_cancel_route,
    auth_status_stream_route,
    _auth_flows,
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
async def test_detect_plex_instance_by_port_or_cmdline(db: aiosqlite.Connection):
    node_id = "test-plex-port-cmd"
    # Node with container on port 32400 (even without 'plex' in name)
    await db.execute(
        """
        INSERT INTO nodes (id, name, hostname, state, cached_containers_json, created_at, updated_at)
        VALUES (?, 'Test Node Port', 'test-host-port', 'CONNECTED', ?, ?, ?)
        """,
        (
            node_id,
            json.dumps([
                {
                    "name": "my-media-app",
                    "image": "custom/media",
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
    assert detection["container_name"] == "my-media-app"

@pytest.mark.asyncio
async def test_detect_route_configured_server_url(db: aiosqlite.Connection):
    node_id = "test-plex-remote"
    await db.execute(
        """
        INSERT INTO nodes (id, name, hostname, state, created_at, updated_at)
        VALUES (?, 'Test Remote Node', 'test-host-remote', 'CONNECTED', ?, ?)
        """,
        (node_id, time.time(), time.time()),
    )
    await db.execute(
        "INSERT INTO plugins (id, enabled, config_json) VALUES ('plex', 1, ?) "
        "ON CONFLICT(id) DO UPDATE SET config_json = excluded.config_json, enabled = excluded.enabled",
        (json.dumps({"plex_token": "mock-token", "plex_server_url": "http://192.168.1.100:32400", "plex_server_name": "Media-Server-1"}),),
    )
    await db.commit()

    detection = await detect_route(node_id, db=db)
    assert detection["detected"] is True
    assert detection["type"] == "remote"
    assert detection["configured"] is True
    assert detection["server_url"] == "http://192.168.1.100:32400"
    assert detection["server_name"] == "Media-Server-1"

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
        "INSERT INTO plugins (id, enabled, config_json) VALUES ('plex', 1, ?) "
        "ON CONFLICT(id) DO UPDATE SET config_json = excluded.config_json, enabled = excluded.enabled",
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
        "INSERT INTO plugins (id, enabled, config_json) VALUES ('plex', 1, ?) "
        "ON CONFLICT(id) DO UPDATE SET config_json = excluded.config_json, enabled = excluded.enabled",
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
async def test_sessions_route_502_carries_failure_reason(db: aiosqlite.Connection):
    """A Plex API failure must surface an actionable 502 detail (URL + cause),
    not a generic message — the frontend polls every 3s and needs to know why."""
    node_id = "test-plex-502"
    await db.execute(
        """
        INSERT INTO nodes (id, name, hostname, state, cached_containers_json, created_at, updated_at)
        VALUES (?, '502 Node', 'unreachable-lan-host', 'CONNECTED', ?, ?, ?)
        """,
        (
            node_id,
            json.dumps([{"name": "plex", "state": "running"}]),
            time.time(),
            time.time(),
        ),
    )
    await db.execute(
        "INSERT INTO plugins (id, enabled, config_json) VALUES ('plex', 1, ?) "
        "ON CONFLICT(id) DO UPDATE SET config_json = excluded.config_json, enabled = excluded.enabled",
        (json.dumps({"plex_token": "mock-token-xyz"}),),
    )
    await db.commit()

    # Connection failure: reason names the attempted URL
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("connexion impossible")):
        with pytest.raises(HTTPException) as exc_info:
            await sessions_route(node_id, db=db)
        assert exc_info.value.status_code == 502
        assert "unreachable-lan-host" in str(exc_info.value.detail)
        assert "ConnectError" in str(exc_info.value.detail)

    # Auth failure: HTTP status from Plex is reported
    mock_resp = AsyncMock()
    mock_resp.status_code = 401
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with pytest.raises(HTTPException) as exc_info:
            await sessions_route(node_id, db=db)
        assert exc_info.value.status_code == 502
        assert "401" in str(exc_info.value.detail)

@pytest.mark.asyncio
async def test_plex_oauth_pin_flow(db: aiosqlite.Connection):
    # 1. Legacy /auth/pin is gone (410) — the flow now lives in
    #    plex.auth.start / plex.auth.verify (T27-BE-2)
    with pytest.raises(HTTPException) as exc_info:
        await auth_pin_route(db=db)
    assert exc_info.value.status_code == 410

    # 2. Test auth_verify_route when pending
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json = lambda: {"authToken": None}

        verify_res = await auth_verify_route(VerifyPinRequest(pin_id=98765), db=db)
        assert verify_res["status"] == "pending"

    # 3. Test auth_verify_route when authorized — status only, NEVER the token
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
        assert verify_res["status"] == "success"
        assert "token" not in verify_res
        assert "config" not in verify_res

@pytest.mark.asyncio
async def test_plex_servers_and_custom_config(db: aiosqlite.Connection):
    # Setup token in DB
    await db.execute(
        "INSERT INTO plugins (id, enabled, config_json) VALUES ('plex', 1, ?) "
        "ON CONFLICT(id) DO UPDATE SET config_json = excluded.config_json, enabled = excluded.enabled",
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
async def test_plex_fastapi_mounted_routes(db: aiosqlite.Connection, security):
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

    token = security.create_access_token("test-user", "test_user", "admin")
    with patch("master.plugins.plex.httpx.AsyncClient", return_value=mock_client_cm):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Legacy /auth/pin is gone (410) — replaced by /plex.auth.start
            resp = await client.post("/api/plugins/plex/auth/pin")
            assert resp.status_code == 410

            # New start flow: 200 + auth_url + waiting
            resp = await client.post(
                "/api/plugins/plex/plex.auth.start",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "waiting"
            assert body["auth_url"].startswith("https://app.plex.tv/auth")

            # Cleanup: cancel the background poll task
            resp = await client.post(
                "/api/plugins/plex/plex.auth.cancel",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            assert resp.json() == {"status": "cancelled"}

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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Legacy /auth/pin is gone (410) — plugin routes still win over the static mount
        resp = await client.post("/api/plugins/plex/auth/pin")
        assert resp.status_code == 410

@pytest.mark.asyncio
async def test_plex_new_features(db: aiosqlite.Connection):
    from master.core.plugin_base import PluginContext
    from master.plugins.plex import PlexPlugin

    node_id = "test-plex-features"
    await db.execute(
        """
        INSERT INTO nodes (id, name, hostname, state, cached_containers_json, created_at, updated_at)
        VALUES (?, 'Test Features Node', 'test-host', 'CONNECTED', ?, ?, ?)
        """,
        (
            node_id,
            json.dumps([{"name": "plex", "state": "running"}]),
            time.time(),
            time.time(),
        ),
    )
    await db.execute(
        "INSERT INTO plugins (id, enabled, config_json) VALUES ('plex', 1, ?) "
        "ON CONFLICT(id) DO UPDATE SET config_json = excluded.config_json, enabled = excluded.enabled",
        (json.dumps({"plex_token": "mock-token-xyz"}),),
    )
    await db.commit()

    ctx = PluginContext(plugin_id="plex", config={}, db=db)
    plugin = PlexPlugin(ctx)

    # 1. Test transcodes_route
    mock_sessions = {
        "MediaContainer": {
            "Metadata": [
                {
                    "sessionKey": "100",
                    "title": "Avatar",
                    "User": {"title": "flavio"},
                    "Player": {"title": "TV"},
                    "TranscodeSession": {
                        "videoDecision": "transcode",
                        "audioDecision": "copy",
                        "speed": 1.5,
                    },
                }
            ]
        }
    }
    with patch("master.plugins.plex._query_plex_api", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = mock_sessions
        res = await plugin.transcodes_route(node_id, db=db)
        assert res["transcodes_count"] == 1
        assert res["transcodes"][0]["title"] == "Avatar"
        assert res["transcodes"][0]["speed"] == 1.5

    # 2. Test files_route
    mock_sections = {
        "MediaContainer": {
            "Directory": [
                {
                    "key": "1",
                    "title": "Films",
                    "type": "movie",
                    "Location": [{"path": "/media/movies"}],
                }
            ]
        }
    }
    mock_files_item = {
        "MediaContainer": {
            "totalSize": 1,
            "Metadata": [
                {
                    "title": "Inception",
                    "Media": [
                        {
                            "videoResolution": "1080p",
                            "container": "mkv",
                            "Part": [{"file": "/media/movies/inception.mkv", "size": 15000000000}],
                        }
                    ],
                }
            ],
        }
    }
    async def mock_files_query(url, path, token):
        if "/library/sections/1/" in path:
            return mock_files_item
        return mock_sections

    with patch("master.plugins.plex._query_plex_api", side_effect=mock_files_query):
        files_res = await plugin.files_route(node_id, db=db)
        assert len(files_res["libraries"]) == 1
        assert files_res["libraries"][0]["title"] == "Films"
        assert len(files_res["largest_files"]) == 1
        assert files_res["largest_files"][0]["title"] == "Inception"
        assert files_res["total_storage_bytes"] == 15000000000

    # 3. Test kill_session_route
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        kill_res = await plugin.kill_session_route(node_id, session_key="100", db=db)
        assert kill_res["status"] == "ok"
        assert kill_res["session_key"] == "100"

    # 4. Test scan_library_section_route
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        scan_res = await plugin.scan_library_section_route(node_id, section_id="1", db=db)
        assert scan_res["status"] == "ok"
        assert scan_res["section_id"] == "1"


def _make_auth_request(token: str | None) -> Request:
    headers = []
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/plugins/plex/plex.auth.start",
            "query_string": b"",
            "headers": headers,
            "client": ("test", 1234),
            "server": ("test", 80),
            "scheme": "http",
        },
        receive=lambda: asyncio.sleep(3600),
    )


async def _collect_data_lines(agen, predicate, timeout=2.0):
    async def _reader():
        async for chunk in agen:
            text = chunk.decode() if isinstance(chunk, bytes) else chunk
            for line in text.splitlines():
                if line.startswith("data: "):
                    payload = json.loads(line[6:])
                    if predicate(payload):
                        return payload
        raise AssertionError("predicate never matched")

    return await asyncio.wait_for(_reader(), timeout=timeout)


async def _collect_until_idle(agen, idle=0.3):
    lines = []
    async def _reader():
        async for chunk in agen:
            text = chunk.decode() if isinstance(chunk, bytes) else chunk
            lines.extend(text.splitlines())

    try:
        await asyncio.wait_for(_reader(), timeout=idle)
    except (asyncio.TimeoutError, TimeoutError):
        pass
    return lines


@pytest.mark.asyncio
async def test_plex_auth_start_requires_bearer(db: aiosqlite.Connection):
    req = _make_auth_request(None)
    with pytest.raises(HTTPException) as exc_info:
        await auth_start_route(req, db=db)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_plex_auth_start_cancel_flow(db: aiosqlite.Connection, security):
    token = security.create_access_token("test-user", "test_user", "admin")
    req = _make_auth_request(token)

    mock_resp = AsyncMock()
    mock_resp.status_code = 201
    mock_resp.json = lambda: {"id": 98765, "code": "code123"}
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)

    with patch("master.plugins.plex.httpx.AsyncClient", return_value=mock_client_cm):
        start_res = await auth_start_route(req, db=db)
        assert start_res["status"] == "waiting"
        assert start_res["auth_url"].startswith("https://app.plex.tv/auth")
        assert "test-user" in _auth_flows

        # 409 on concurrent start
        with pytest.raises(HTTPException) as exc_info:
            await auth_start_route(req, db=db)
        assert exc_info.value.status_code == 409

        # cancel stops the flow
        cancel_res = await auth_cancel_route(req, db=db)
        assert cancel_res == {"status": "cancelled"}
        assert "test-user" not in _auth_flows

        # idle on second cancel
        cancel_res2 = await auth_cancel_route(req, db=db)
        assert cancel_res2 == {"status": "idle"}


@pytest.mark.asyncio
async def test_plex_auth_status_sse_session_isolation(db: aiosqlite.Connection, security):
    from master.core.event_bus import get_event_bus

    bus = get_event_bus()
    token_a = security.create_access_token("user-a", "user_a", "admin")
    token_b = security.create_access_token("user-b", "user_b", "admin")

    def _make_req():
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/plugins/plex/auth/status/stream",
                "query_string": b"",
                "headers": [],
                "client": ("test", 1234),
                "server": ("test", 80),
                "scheme": "http",
            },
            receive=lambda: asyncio.sleep(3600),
        )

    agen_a = (await auth_status_stream_route(_make_req(), token=token_a, bus=bus)).body_iterator
    agen_b = (await auth_status_stream_route(_make_req(), token=token_b, bus=bus)).body_iterator
    try:
        await bus.publish("plex.auth.status:user-a", {"status": "success"})
        # user A receives its own topic event
        payload = await _collect_data_lines(agen_a, lambda p: p.get("status") == "success")
        assert payload["status"] == "success"
        # user B must NOT receive user A's event — idle window proves silence
        got = await _collect_until_idle(agen_b, idle=0.3)
        assert not any("success" in line for line in got)
    finally:
        await agen_a.aclose()
        await agen_b.aclose()


@pytest.mark.asyncio
async def test_plex_photo_proxy_ssrf_protection(db: aiosqlite.Connection):
    """Ensure Plex photo proxy blocks path traversal and SSRF prefixes."""
    from master.core.plugin_base import PluginContext
    from master.plugins.plex import PlexPlugin

    ctx = PluginContext(plugin_id="plex", config={}, db=db)
    plugin = PlexPlugin(ctx)

    # 1. Invalid prefixes or path traversal should raise 400
    with pytest.raises(HTTPException) as exc:
        await plugin.photo_proxy_route("node-1", path="/etc/passwd", db=db)
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await plugin.photo_proxy_route("node-1", path="/library/metadata/../../etc/shadow", db=db)
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await plugin.photo_proxy_route("node-1", path="http://evil.com/thumb", db=db)
    assert exc.value.status_code == 400




