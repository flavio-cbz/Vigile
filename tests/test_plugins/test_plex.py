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

from master.plugins.plex_plugin import (
    detect_plex_instance,
    _on_status_report,
    detect_route,
    sessions_route,
    library_route,
    users_route,
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
