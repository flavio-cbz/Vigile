from __future__ import annotations

"""
Vigile — Plex Integration Plugin (Package Format)

Monitors Plex Media Server activity and provides detailed diagnostics.
Migrated from plex_plugin.py to class-based PluginBase format.
"""

import json
import logging
import time
from typing import Any

from fastapi import Depends, HTTPException
import httpx
import aiosqlite

from master.db.database import get_db_conn
from master.core.node_manager import node_manager
from master.core.audit import log_action
from master.core.plugin_base import PluginBase, route, hook

logger = logging.getLogger(__name__)

# Default configurations
DEFAULT_PLEX_PORT = 32400
DEFAULT_CPU_THRESHOLD = 80


# ---------------------------------------------------------------------------
# Config schema (module-level for backward compatibility)
# ---------------------------------------------------------------------------

def get_config_schema() -> dict[str, Any]:
    return {
        "name": "Plex Media Server",
        "description": "Auto-detects Plex instances, reports active library streaming sessions, and automates load-heavy investigation.",
        "category": "Media",
        "schema": {
            "plex_token": {
                "type": "string",
                "title": "Plex Auth Token",
                "default": "",
                "description": "Auth token to communicate with Plex API (can be auto-configured via OAuth login).",
            },
            "plex_port_override": {
                "type": "integer",
                "title": "Plex Port Override",
                "default": 0,
                "description": "Override detected port (leave 0 for auto-detection or 32400 default).",
            },
            "cpu_threshold": {
                "type": "integer",
                "title": "CPU Threshold (%)",
                "default": DEFAULT_CPU_THRESHOLD,
                "description": "Alert diagnostic threshold.",
            },
        },
    }


# ---------------------------------------------------------------------------
# Core Logic & Helpers (module-level for reuse)
# ---------------------------------------------------------------------------

async def _get_plex_config(db: aiosqlite.Connection) -> dict:
    try:
        cursor = await db.execute("SELECT config_json FROM plugins WHERE id = 'plex'")
        row = await cursor.fetchone()
        if row and row[0]:
            return json.loads(row[0])
    except Exception as e:
        logger.error("Plex plugin: Failed to query config: %s", e)
    return {}


async def detect_plex_instance(node_id: str, db: aiosqlite.Connection) -> dict[str, Any]:
    """Inspects cached containers and services to detect if Plex is present."""
    node = await node_manager.get_node(db, node_id)
    if not node:
        return {"detected": False, "port": DEFAULT_PLEX_PORT, "type": None}

    # 1. Check Docker containers
    cached_containers = node.get("cached_containers_json")
    if cached_containers:
        try:
            containers = json.loads(cached_containers)
            for c in containers:
                c_name = c.get("name", "").lower()
                c_image = c.get("image", "").lower()
                if "plex" in c_name or "plex" in c_image:
                    port = DEFAULT_PLEX_PORT
                    ports = c.get("ports", [])
                    if isinstance(ports, list):
                        for p in ports:
                            if p.get("ContainerPort") == 32400:
                                port = p.get("HostPort", DEFAULT_PLEX_PORT)
                                break
                    return {
                        "detected": True,
                        "port": port,
                        "type": "docker",
                        "container_name": c.get("name"),
                        "status": c.get("state", "unknown"),
                    }
        except Exception:
            logger.exception("Plex plugin: failed to parse cached containers")

    # 2. Check Systemd services
    cached_services = node.get("cached_services_json")
    if cached_services:
        try:
            services = json.loads(cached_services)
            for s in services:
                s_name = s.get("service", "").lower()
                if "plex" in s_name:
                    return {
                        "detected": True,
                        "port": DEFAULT_PLEX_PORT,
                        "type": "native",
                        "service_name": s.get("service"),
                        "status": s.get("state", "unknown"),
                    }
        except Exception:
            logger.exception("Plex plugin: failed to parse cached services")

    # 3. Check native process (metrics processes)
    async with db.execute(
        "SELECT top_processes_json FROM metrics_snapshots WHERE node_id = ? ORDER BY collected_at DESC LIMIT 1",
        (node_id,),
    ) as cursor:
        row = await cursor.fetchone()
        if row and row[0]:
            try:
                processes = json.loads(row[0])
                for p in processes:
                    p_name = p.get("name", "").lower()
                    if "plex" in p_name:
                        return {
                            "detected": True,
                            "port": DEFAULT_PLEX_PORT,
                            "type": "native",
                            "status": "running",
                        }
            except Exception:
                logger.exception("Plex plugin: failed to parse metrics processes")

    return {"detected": False, "port": DEFAULT_PLEX_PORT, "type": None}


async def _get_plex_client_and_url(node_id: str, db: aiosqlite.Connection, config: dict) -> tuple[str, str] | None:
    """Resolves local Plex URL and token. Returns (url, token) or None."""
    token = config.get("plex_token", "")
    if not token:
        return None

    node = await node_manager.get_node(db, node_id)
    if not node:
        return None

    detection = await detect_plex_instance(node_id, db)
    port = config.get("plex_port_override") or detection.get("port") or DEFAULT_PLEX_PORT

    hostname = node.get("hostname")
    if hostname:
        return f"http://{hostname}:{port}", token
    return f"http://localhost:{port}", token


async def _query_plex_api(url: str, path: str, token: str) -> dict | None:
    """Helper to perform requests on Plex local API."""
    headers = {"Accept": "application/json"}
    params = {"X-Plex-Token": token}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{url.rstrip('/')}{path}", headers=headers, params=params)
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.warning("Plex API connection failed to %s: %s", url, e)
    return None


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------

class PlexPlugin(PluginBase):
    """Plex Media Server integration plugin."""

    plugin_id = "plex"

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    @hook("on_status_report")
    async def on_status_report(self, node_id: str, snapshot: dict, db=None) -> None:
        if not db:
            return

        cpu = snapshot.get("cpu_percent", 0.0)
        config = await _get_plex_config(db)
        threshold = config.get("cpu_threshold", DEFAULT_CPU_THRESHOLD)

        # 1. Only run diagnostic on high load
        if cpu < threshold:
            return

        # 2. Check if Plex is configured and active
        client_info = await _get_plex_client_and_url(node_id, db, config)
        if not client_info:
            return

        url, token = client_info

        # 3. Query active Plex sessions
        sessions_data = await _query_plex_api(url, "/status/sessions", token)
        if not sessions_data:
            return

        metadata = sessions_data.get("MediaContainer", {}).get("Metadata", [])
        if not metadata:
            return

        # 4. Format sessions for diagnostic logging
        parsed_sessions = []
        for item in metadata:
            title = item.get("title")
            if item.get("type") == "episode":
                grandparent = item.get("grandparentTitle", "")
                title = f"{grandparent} - {title}"

            transcode = item.get("TranscodeSession", {})
            parsed_sessions.append({
                "user": item.get("User", {}).get("title", "Unknown"),
                "title": title,
                "type": item.get("type", "unknown"),
                "state": item.get("Player", {}).get("state", "unknown"),
                "transcode": bool(transcode),
                "video_decision": transcode.get("videoDecision", "copy"),
            })

        # 5. Check if we already logged a high load diagnostic within the last 5 minutes
        try:
            five_mins_ago = time.time() - 300
            cursor = await db.execute(
                "SELECT created_at FROM audit_log WHERE node_id = ? AND action = 'PLEX_HIGH_LOAD_DIAGNOSTIC' AND created_at > ? LIMIT 1",
                (node_id, five_mins_ago),
            )
            existing = await cursor.fetchone()
            if existing:
                return  # Skip duplicate diagnostic log
        except Exception:
            logger.debug("Plex plugin: failed to check for duplicate diagnostic log entry")

        # 6. Log the diagnostic action into audit trail
        try:
            await log_action(
                db,
                user_id="plex_plugin",
                action="PLEX_HIGH_LOAD_DIAGNOSTIC",
                node_id=node_id,
                details={
                    "cpu_percent": cpu,
                    "sessions_count": len(parsed_sessions),
                    "active_sessions": parsed_sessions,
                }
            )
        except Exception as e:
            logger.error("Plex plugin: Failed to log audit diagnostic: %s", e)

    @hook("get_heavy_process_patterns")
    def get_heavy_process_patterns(self) -> list[dict[str, Any]]:
        return [
            {
                "container_pattern": r"plex|jellyfin|emby",
                "category": "media",
                "label": "Transcodage Multimédia",
                "cpu_threshold_percent": 50.0,
            },
            {
                "service_pattern": r"plex",
                "category": "media",
                "label": "Transcodage Plex Media Server",
                "cpu_threshold_percent": 50.0,
            },
        ]

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @route("/{node_id}/detect", method="GET", roles=["operator", "viewer"])
    async def detect_route(self, node_id: str, db: aiosqlite.Connection = Depends(get_db_conn)) -> dict:
        """Auto-detect Plex presence and configuration state."""
        config = await _get_plex_config(db)
        detection = await detect_plex_instance(node_id, db)
        configured = bool(config.get("plex_token"))
        return {
            "node_id": node_id,
            "detected": detection["detected"],
            "type": detection["type"],
            "port": detection["port"],
            "status": detection.get("status"),
            "configured": configured,
        }

    @route("/{node_id}/sessions", method="GET", roles=["operator", "viewer"])
    async def sessions_route(self, node_id: str, db: aiosqlite.Connection = Depends(get_db_conn)) -> dict:
        """Returns currently active streaming sessions."""
        config = await _get_plex_config(db)
        client_info = await _get_plex_client_and_url(node_id, db, config)
        if not client_info:
            raise HTTPException(status_code=400, detail="Plex is not configured or not active on this node.")

        url, token = client_info
        data = await _query_plex_api(url, "/status/sessions", token)
        if not data:
            raise HTTPException(status_code=502, detail="Failed to fetch sessions from Plex API.")

        metadata = data.get("MediaContainer", {}).get("Metadata", [])
        sessions = []
        for item in metadata:
            transcode = item.get("TranscodeSession", {})
            sessions.append({
                "user": item.get("User", {}).get("title", "Unknown"),
                "title": item.get("title"),
                "grandparent_title": item.get("grandparentTitle"),
                "type": item.get("type"),
                "state": item.get("Player", {}).get("state"),
                "device": item.get("Player", {}).get("device"),
                "transcode": bool(transcode),
                "video_decision": transcode.get("videoDecision"),
                "speed": transcode.get("speed"),
            })

        return {"sessions": sessions, "count": len(sessions)}

    @route("/{node_id}/library", method="GET", roles=["operator", "viewer"])
    async def library_route(self, node_id: str, db: aiosqlite.Connection = Depends(get_db_conn)) -> dict:
        """Returns media libraries and section detail counts."""
        config = await _get_plex_config(db)
        client_info = await _get_plex_client_and_url(node_id, db, config)
        if not client_info:
            raise HTTPException(status_code=400, detail="Plex is not configured or not active on this node.")

        url, token = client_info
        data = await _query_plex_api(url, "/library/sections", token)
        if not data:
            raise HTTPException(status_code=502, detail="Failed to fetch library sections from Plex API.")

        directory = data.get("MediaContainer", {}).get("Directory", [])
        libraries = []
        for item in directory:
            libraries.append({
                "key": item.get("key"),
                "title": item.get("title"),
                "type": item.get("type"),
                "agent": item.get("agent"),
                "scanner": item.get("scanner"),
            })

        return {"libraries": libraries, "count": len(libraries)}

    @route("/{node_id}/users", method="GET", roles=["operator", "viewer"])
    async def users_route(self, node_id: str, db: aiosqlite.Connection = Depends(get_db_conn)) -> dict:
        """Returns list of Plex home/shared users."""
        config = await _get_plex_config(db)
        client_info = await _get_plex_client_and_url(node_id, db, config)
        if not client_info:
            raise HTTPException(status_code=400, detail="Plex is not configured or not active on this node.")

        url, token = client_info
        data = await _query_plex_api(url, "/accounts", token)
        if not data:
            raise HTTPException(status_code=502, detail="Failed to fetch accounts from Plex API.")

        accounts = data.get("MediaContainer", {}).get("Account", [])
        users = []
        for item in accounts:
            users.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "default_subtitle_language": item.get("defaultSubtitleLanguage"),
            })
        return {"users": users, "count": len(users)}


# Backward compatibility functions for test_plex.py
async def _on_status_report(node_id: str, snapshot: dict, db=None) -> None:
    from master.core.plugin_base import PluginContext
    ctx = PluginContext(plugin_id="plex", config={}, db=db)
    plugin = PlexPlugin(ctx)
    await plugin.on_status_report(node_id, snapshot, db=db)

async def detect_route(node_id: str, db: aiosqlite.Connection) -> dict:
    from master.core.plugin_base import PluginContext
    ctx = PluginContext(plugin_id="plex", config={}, db=db)
    plugin = PlexPlugin(ctx)
    return await plugin.detect_route(node_id, db=db)

async def sessions_route(node_id: str, db: aiosqlite.Connection) -> dict:
    from master.core.plugin_base import PluginContext
    ctx = PluginContext(plugin_id="plex", config={}, db=db)
    plugin = PlexPlugin(ctx)
    return await plugin.sessions_route(node_id, db=db)

async def library_route(node_id: str, db: aiosqlite.Connection) -> dict:
    from master.core.plugin_base import PluginContext
    ctx = PluginContext(plugin_id="plex", config={}, db=db)
    plugin = PlexPlugin(ctx)
    return await plugin.library_route(node_id, db=db)

async def users_route(node_id: str, db: aiosqlite.Connection) -> dict:
    from master.core.plugin_base import PluginContext
    ctx = PluginContext(plugin_id="plex", config={}, db=db)
    plugin = PlexPlugin(ctx)
    return await plugin.users_route(node_id, db=db)
