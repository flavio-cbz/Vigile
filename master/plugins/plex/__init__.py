from __future__ import annotations

"""
Vigile — Plex Integration Plugin (Package Format)

Monitors Plex Media Server activity, logs watch history, provides detailed diagnostics,
exposes secure artwork proxying, and injects context into the AI Copilot.
"""

import json
import logging
import time
import uuid
from typing import Any, Optional

from fastapi import Depends, HTTPException, Query, Response
from pydantic import BaseModel
import httpx
import aiosqlite

from master.db.database import get_db_conn
from master.core.node_manager import node_manager
from master.core.audit import log_action
from master.core.plugin_base import PluginBase, route, hook
from master.api.schemas.plex import PlexSession, PlexWatchHistoryEntry, PlexStats

logger = logging.getLogger(__name__)

# Default configurations
DEFAULT_PLEX_PORT = 32400
DEFAULT_CPU_THRESHOLD = 80
DEFAULT_RETENTION_DAYS = 30

class VerifyPinRequest(BaseModel):
    pin_id: int

# Allowed path prefixes for image proxying
ALLOWED_ARTWORK_PREFIXES = (
    "/library/metadata/",
    "/photo/:/transcode",
    "/accounts/",
    "/sections/",
)


# ---------------------------------------------------------------------------
# Config schema (module-level for backward compatibility)
# ---------------------------------------------------------------------------

def get_config_schema() -> dict[str, Any]:
    return {
        "name": "Plex Media Server",
        "description": "Auto-detects Plex instances, reports active library streaming sessions, logs watch history, and automates load investigation.",
        "category": "Media",
        "schema": {
            "plex_token": {
                "type": "string",
                "title": "Plex Auth Token",
                "default": "",
                "description": "Auth token to communicate with Plex API.",
            },
            "plex_server_url": {
                "type": "string",
                "title": "Plex Server URL",
                "default": "",
                "description": "Selected Plex Server address (e.g. http://192.168.1.50:32400 or leave empty for auto-detection).",
            },
            "plex_server_name": {
                "type": "string",
                "title": "Plex Server Name",
                "default": "",
                "description": "Friendly name of the selected Plex server.",
            },
            "plex_port_override": {
                "type": "integer",
                "title": "Plex Port Override",
                "default": 0,
                "description": "Override detected port (leave 0 for 32400 default).",
            },
            "cpu_threshold": {
                "type": "integer",
                "title": "CPU Threshold (%)",
                "default": DEFAULT_CPU_THRESHOLD,
                "description": "Alert diagnostic threshold.",
            },
            "retention_days": {
                "type": "integer",
                "title": "History Retention (Days)",
                "default": DEFAULT_RETENTION_DAYS,
                "description": "Number of days to keep watch history in SQLite.",
            },
        },
    }


# ---------------------------------------------------------------------------
# Core Logic & Helpers
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


async def _save_plex_config(db: aiosqlite.Connection, updates: dict[str, Any]) -> dict[str, Any]:
    """Updates and saves Plex plugin config JSON in database."""
    config = await _get_plex_config(db)
    config.update(updates)
    config_json = json.dumps(config)
    await db.execute(
        "INSERT INTO plugins (id, enabled, config_json) VALUES ('plex', 1, ?) "
        "ON CONFLICT(id) DO UPDATE SET config_json = excluded.config_json",
        (config_json,),
    )
    await db.commit()
    return config


def _get_plex_client_id(config: dict) -> str:
    """Gets existing client identifier or generates a stable default."""
    client_id = config.get("plex_client_identifier")
    if not client_id:
        client_id = "vigile-master-" + str(uuid.uuid4())[:8]
    return client_id


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

    # 3. Check native process metrics
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

    # Use explicitly selected Plex server URL if set
    server_url = (config.get("plex_server_url") or "").strip()
    if server_url:
        return server_url.rstrip("/"), token

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
    """Helper to perform JSON requests on Plex API."""
    headers = {"Accept": "application/json"}
    params = {"X-Plex-Token": token}
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(f"{url.rstrip('/')}{path}", headers=headers, params=params)
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.warning("Plex API connection failed to %s: %s", url, e)
    return None


async def purge_old_watch_history(db: aiosqlite.Connection, retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
    """Purges entries from plex_watch_history older than retention_days."""
    cutoff = time.time() - (retention_days * 86400)
    cursor = await db.execute("DELETE FROM plex_watch_history WHERE viewed_at < ?", (cutoff,))
    deleted = cursor.rowcount
    await db.commit()
    return deleted


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

        if cpu < threshold:
            return

        client_info = await _get_plex_client_and_url(node_id, db, config)
        if not client_info:
            return

        url, token = client_info
        sessions_data = await _query_plex_api(url, "/status/sessions", token)
        if not sessions_data:
            return

        metadata = sessions_data.get("MediaContainer", {}).get("Metadata", [])
        if not metadata:
            return

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

        try:
            five_mins_ago = time.time() - 300
            cursor = await db.execute(
                "SELECT created_at FROM audit_log WHERE node_id = ? AND action = 'PLEX_HIGH_LOAD_DIAGNOSTIC' AND created_at > ? LIMIT 1",
                (node_id, five_mins_ago),
            )
            existing = await cursor.fetchone()
            if existing:
                return
        except Exception:
            logger.debug("Plex plugin: failed to check duplicate diagnostic entry")

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

    @hook("get_ai_context")
    async def get_ai_context(self, node_id: str, db: aiosqlite.Connection = None) -> dict[str, Any]:
        """Provides structured context for LLM Copilot."""
        if not db:
            return {}

        config = await _get_plex_config(db)
        client_info = await _get_plex_client_and_url(node_id, db, config)
        if not client_info:
            return {"plex_detected": False}

        url, token = client_info
        sessions_data = await _query_plex_api(url, "/status/sessions", token)
        active_count = 0
        details = []
        transcoding_count = 0

        if sessions_data:
            metadata = sessions_data.get("MediaContainer", {}).get("Metadata", [])
            active_count = len(metadata)
            for item in metadata:
                transcode = item.get("TranscodeSession", {})
                is_transcoding = bool(transcode)
                if is_transcoding:
                    transcoding_count += 1
                details.append({
                    "user": item.get("User", {}).get("title", "Unknown"),
                    "title": item.get("title"),
                    "grandparent": item.get("grandparentTitle"),
                    "device": item.get("Player", {}).get("device"),
                    "transcoding": is_transcoding,
                })

        return {
            "plex_detected": True,
            "plex_active_sessions": active_count,
            "plex_transcoding_active": transcoding_count > 0,
            "plex_sessions_detail": details[:5],
        }

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
        now = time.time()

        for item in metadata:
            transcode = item.get("TranscodeSession", {})
            user_info = item.get("User", {})
            player_info = item.get("Player", {})

            session_obj = PlexSession(
                session_key=item.get("sessionKey"),
                user=user_info.get("title", "Unknown"),
                user_thumb=user_info.get("thumb"),
                title=item.get("title", "Sans titre"),
                grandparent_title=item.get("grandparentTitle"),
                parent_title=item.get("parentTitle"),
                media_type=item.get("type", "unknown"),
                progress_percent=float(item.get("viewOffset", 0)) / max(float(item.get("duration", 1)), 1.0) * 100.0,
                state=player_info.get("state", "playing"),
                player_device=player_info.get("title", "Unknown Device"),
                player_platform=player_info.get("platform"),
                quality_profile="Transcode" if bool(transcode) else "Direct Play",
                bandwidth_kbps=item.get("Session", {}).get("bandwidth", 0),
                started_at=int(now),
                transcode=bool(transcode),
                video_decision=transcode.get("videoDecision"),
                audio_decision=transcode.get("audioDecision"),
                speed=float(transcode.get("speed")) if transcode.get("speed") else None,
                thumb=item.get("thumb"),
            )
            sessions.append(session_obj.model_dump())

        return {"sessions": sessions, "count": len(sessions)}

    @route("/{node_id}/photo", method="GET", roles=["operator", "viewer"])
    async def photo_proxy_route(
        self,
        node_id: str,
        path: str = Query(..., description="Relative Plex artwork path"),
        db: aiosqlite.Connection = Depends(get_db_conn),
    ) -> Response:
        """Secure Master photo proxy for Plex posters and artwork."""
        if not any(path.startswith(prefix) for prefix in ALLOWED_ARTWORK_PREFIXES):
            raise HTTPException(status_code=400, detail="Invalid artwork path prefix.")

        config = await _get_plex_config(db)
        client_info = await _get_plex_client_and_url(node_id, db, config)
        if not client_info:
            raise HTTPException(status_code=400, detail="Plex is not configured.")

        url, token = client_info
        full_url = f"{url.rstrip('/')}{path}"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(full_url, params={"X-Plex-Token": token})
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail="Failed to fetch image from Plex.")

                content_type = resp.headers.get("content-type", "image/jpeg")
                return Response(
                    content=resp.content,
                    media_type=content_type,
                    headers={"Cache-Control": "public, max-age=86400"},
                )
        except Exception as e:
            logger.error("Plex photo proxy error: %s", e)
            raise HTTPException(status_code=502, detail="Failed to reach local Plex server.")

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

    @route("/{node_id}/history", method="GET", roles=["operator", "viewer"])
    async def history_route(
        self,
        node_id: str,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        db: aiosqlite.Connection = Depends(get_db_conn),
    ) -> dict:
        """Returns paginated watch history from SQLite."""
        async with db.execute(
            "SELECT id, user, title, grandparent_title, media_type, viewed_at, duration_watched_s, progress_percent, device, quality "
            "FROM plex_watch_history WHERE node_id = ? ORDER BY viewed_at DESC LIMIT ? OFFSET ?",
            (node_id, limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()

        entries = []
        for row in rows:
            entries.append(
                PlexWatchHistoryEntry(
                    id=row[0],
                    node_id=node_id,
                    user=row[1],
                    title=row[2],
                    grandparent_title=row[3],
                    media_type=row[4],
                    viewed_at=int(row[5]),
                    duration_watched_s=row[6],
                    progress_percent=row[7],
                    device=row[8],
                    quality=row[9],
                ).model_dump()
            )

        async with db.execute("SELECT COUNT(*) FROM plex_watch_history WHERE node_id = ?", (node_id,)) as cursor:
            total_row = await cursor.fetchone()
            total = total_row[0] if total_row else 0

        return {"history": entries, "total": total, "limit": limit, "offset": offset}

    @route("/{node_id}/stats", method="GET", roles=["operator", "viewer"])
    async def stats_route(self, node_id: str, db: aiosqlite.Connection = Depends(get_db_conn)) -> dict:
        """Returns aggregated stats for Plex dashboard."""
        now_24h = time.time() - 86400
        async with db.execute(
            "SELECT COUNT(*) FROM plex_watch_history WHERE node_id = ? AND viewed_at > ?", (node_id, now_24h)
        ) as cursor:
            today_count = (await cursor.fetchone())[0]

        async with db.execute(
            "SELECT user, COUNT(*) as c FROM plex_watch_history WHERE node_id = ? GROUP BY user ORDER BY c DESC LIMIT 1",
            (node_id,),
        ) as cursor:
            top_user_row = await cursor.fetchone()
            top_user = top_user_row[0] if top_user_row else "N/A"

        config = await _get_plex_config(db)
        client_info = await _get_plex_client_and_url(node_id, db, config)
        sessions_active = 0
        if client_info:
            url, token = client_info
            data = await _query_plex_api(url, "/status/sessions", token)
            if data:
                sessions_active = len(data.get("MediaContainer", {}).get("Metadata", []))

        stats = PlexStats(
            sessions_active=sessions_active,
            sessions_today=today_count,
            most_watched_user=top_user,
        )
        return stats.model_dump()

    @route("/auth/pin", method="POST", roles=["admin", "operator"])
    async def auth_pin_route(self, db: aiosqlite.Connection = Depends(get_db_conn)) -> dict:
        """Create a Plex OAuth authentication PIN."""
        config = await _get_plex_config(db)
        client_id = _get_plex_client_id(config)
        if not config.get("plex_client_identifier"):
            await _save_plex_config(db, {"plex_client_identifier": client_id})

        headers = {
            "Accept": "application/json",
            "X-Plex-Product": "Vigile Fleet Manager",
            "X-Plex-Version": "1.0.0",
            "X-Plex-Device": "Vigile Master",
            "X-Plex-Client-Identifier": client_id,
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post("https://plex.tv/api/v2/pins?strong=true", headers=headers)
                if resp.status_code not in (200, 201):
                    raise HTTPException(status_code=502, detail=f"Plex API error: {resp.status_code}")
                data = resp.json()
                code = data.get("code")
                pin_id = data.get("id")
                auth_url = (
                    f"https://app.plex.tv/auth/#!?clientID={client_id}"
                    f"&code={code}&context%5Bdevice%5D%5Bproduct%5D=Vigile+Fleet+Manager"
                )
                return {
                    "id": pin_id,
                    "code": code,
                    "auth_url": auth_url,
                    "client_id": client_id,
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to create Plex PIN: %s", e)
            raise HTTPException(status_code=502, detail="Failed to connect to Plex authentication servers.")

    @route("/auth/verify", method="POST", roles=["admin", "operator"])
    async def auth_verify_route(
        self,
        payload: VerifyPinRequest,
        db: aiosqlite.Connection = Depends(get_db_conn),
    ) -> dict:
        """Check status of Plex PIN and save auth token if authorized."""
        pin_id = payload.pin_id
        config = await _get_plex_config(db)
        client_id = _get_plex_client_id(config)
        headers = {
            "Accept": "application/json",
            "X-Plex-Client-Identifier": client_id,
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(f"https://plex.tv/api/v2/pins/{pin_id}", headers=headers)
                if resp.status_code != 200:
                    return {"authenticated": False}
                data = resp.json()
                token = data.get("authToken") or data.get("auth_token")
                if not token:
                    return {"authenticated": False}

                user_name = None
                try:
                    user_resp = await client.get(
                        "https://plex.tv/api/v2/user",
                        headers={"Accept": "application/json", "X-Plex-Token": token, "X-Plex-Client-Identifier": client_id},
                    )
                    if user_resp.status_code == 200:
                        user_data = user_resp.json()
                        user_name = user_data.get("username") or user_data.get("title") or user_data.get("email")
                except Exception:
                    logger.debug("Could not fetch Plex user details")

                updated = await _save_plex_config(
                    db,
                    {
                        "plex_token": token,
                        "plex_username": user_name or "Plex User",
                    },
                )
                return {
                    "authenticated": True,
                    "token": token,
                    "user": user_name,
                    "config": updated,
                }
        except Exception as e:
            logger.error("Failed to verify Plex PIN %s: %s", pin_id, e)
            raise HTTPException(status_code=502, detail="Failed to verify Plex authentication PIN.")

    @route("/servers", method="GET", roles=["admin", "operator"])
    async def servers_route(self, db: aiosqlite.Connection = Depends(get_db_conn)) -> dict:
        """Fetch available Plex Media Servers for the authenticated user from Plex.tv."""
        config = await _get_plex_config(db)
        token = config.get("plex_token", "")
        if not token:
            raise HTTPException(status_code=400, detail="Plex est non connecté. Veuillez d'abord vous authentifier.")

        client_id = _get_plex_client_id(config)
        headers = {
            "Accept": "application/json",
            "X-Plex-Token": token,
            "X-Plex-Client-Identifier": client_id,
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get("https://plex.tv/api/v2/resources?includeHttps=1&includeRelays=1", headers=headers)
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail="Erreur lors de la récupération des serveurs Plex.")
                resources = resp.json()

                servers = []
                for res in resources:
                    provides = res.get("provides", "")
                    provides_str = ",".join(provides) if isinstance(provides, list) else str(provides)

                    if "server" in provides_str:
                        connections = []
                        raw_conns = res.get("connections", [])
                        for conn in raw_conns:
                            connections.append({
                                "uri": conn.get("uri"),
                                "address": conn.get("address"),
                                "port": conn.get("port"),
                                "local": bool(conn.get("local")),
                                "protocol": conn.get("protocol", "http"),
                            })
                        servers.append({
                            "name": res.get("name"),
                            "product": res.get("product"),
                            "productVersion": res.get("productVersion"),
                            "clientIdentifier": res.get("clientIdentifier"),
                            "owned": bool(res.get("owned")),
                            "connections": connections,
                        })
                return {"servers": servers, "count": len(servers)}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to fetch Plex servers: %s", e)
            raise HTTPException(status_code=502, detail="Impossible de joindre plex.tv pour lister les serveurs.")

    @route("/config/server", method="POST", roles=["admin", "operator"])
    async def save_server_config_route(
        self,
        payload: dict,
        db: aiosqlite.Connection = Depends(get_db_conn),
    ) -> dict:
        """Save selected Plex server connection URL and preferences."""
        server_url = (payload.get("server_url") or "").strip()
        server_name = (payload.get("server_name") or "").strip()
        client_identifier = (payload.get("client_identifier") or "").strip()

        updates: dict[str, Any] = {
            "plex_server_url": server_url,
            "plex_server_name": server_name,
        }
        if client_identifier:
            updates["plex_server_client_identifier"] = client_identifier

        updated_config = await _save_plex_config(db, updates)
        return {"status": "ok", "config": updated_config}


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

async def auth_pin_route(db: aiosqlite.Connection) -> dict:
    from master.core.plugin_base import PluginContext
    ctx = PluginContext(plugin_id="plex", config={}, db=db)
    plugin = PlexPlugin(ctx)
    return await plugin.auth_pin_route(db=db)

async def auth_verify_route(payload: VerifyPinRequest | int, db: aiosqlite.Connection) -> dict:
    from master.core.plugin_base import PluginContext
    ctx = PluginContext(plugin_id="plex", config={}, db=db)
    plugin = PlexPlugin(ctx)
    req = payload if isinstance(payload, VerifyPinRequest) else VerifyPinRequest(pin_id=payload)
    return await plugin.auth_verify_route(payload=req, db=db)

async def servers_route(db: aiosqlite.Connection) -> dict:
    from master.core.plugin_base import PluginContext
    ctx = PluginContext(plugin_id="plex", config={}, db=db)
    plugin = PlexPlugin(ctx)
    return await plugin.servers_route(db=db)

async def save_server_config_route(payload: dict, db: aiosqlite.Connection) -> dict:
    from master.core.plugin_base import PluginContext
    ctx = PluginContext(plugin_id="plex", config={}, db=db)
    plugin = PlexPlugin(ctx)
    return await plugin.save_server_config_route(payload=payload, db=db)


