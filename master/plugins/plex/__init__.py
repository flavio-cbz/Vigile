from __future__ import annotations

"""
Vigile — Plex Integration Plugin (Package Format)

Monitors Plex Media Server activity, logs watch history, provides detailed diagnostics,
exposes secure artwork proxying, and injects context into the AI Copilot.
"""

import asyncio
import json
import logging
import os
import time
import uuid
import posixpath
from typing import Any, AsyncGenerator, Optional

from fastapi import Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx
import aiosqlite

from master.db.database import get_db_conn
from master.core.node_manager import node_manager
from master.core.audit import AuditAction, log_action
from master.core.config_encryption import (
    SecretDecryptionError,
    decrypt_secret,
    derive_config_key,
    encrypt_secret,
)
from master.core.security_manager import get_security_instance
from master.core.plugin_base import PluginBase, route, hook
from master.core.lock import LoopBoundLock
from master.core.event_bus import EventBus, get_event_bus
from master.core.rate_limiter import (
    PluginCallType,
    default_plugin_budget_provider,
    plugin_rate_limiter,
)
from master.api.deps import get_bus
from master.api.schemas.plex import PlexSession, PlexWatchHistoryEntry, PlexStats

logger = logging.getLogger(__name__)

# Default configurations
DEFAULT_PLEX_PORT = 32400
DEFAULT_CPU_THRESHOLD = 80
DEFAULT_RETENTION_DAYS = 30

# --- Flux OAuth Plex (T27-BE-2) ---
# Canal SSE scopé par utilisateur : `plex.auth.status:{user_id}` (claims["sub"]).
_AUTH_STATUS_TOPIC = "plex.auth.status"
_SSE_KEEPALIVE_SECONDS = 25.0
_POLL_INTERVAL_SECONDS = 1.0
_POLL_MAX_ATTEMPTS = 120
# user_id -> {"task", "token", "pin_id", "status", "cancelled"}
_auth_flows: dict[str, dict] = {}
_auth_flow_lock = LoopBoundLock()
_config_save_lock = LoopBoundLock()

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

def _config_encryption_key() -> bytes:
    """Clé AES-256 dérivée de la clé privée Ed25519 du Master (HKDF-SHA256).

    DI au bord : la clé est dérivée de l'objet clé privée du singleton
    SecurityManager — jamais lue depuis l'environnement ni les settings
    (règle master/core, plan §5.1 : la paire de signature est la seule
    matière secrète disponible).
    """
    return derive_config_key(get_security_instance().master_private_key)


async def _migrate_and_decrypt_plex_config(db: aiosqlite.Connection, config: dict[str, Any]) -> None:
    """Migration in-place + déchiffrement du token Plex (plan §5.1, option A).

    - Token ``v1:`` → déchiffré pour l'usage serveur ; valeur corrompue →
      échec-faible (token ignoré, log, le reste de la config reste utilisable).
    - Token legacy en clair → chiffré en place + entrée d'audit
      (``CONFIGURE_PLUGIN``, même action que le chemin d'écriture admin).
      Idempotent : au second chargement le token commence par ``v1:`` → no-op.
    """
    token = config.get("plex_token")
    if not token:
        return
    if token.startswith("v1:"):
        try:
            config["plex_token"] = decrypt_secret(token, _config_encryption_key())
        except SecretDecryptionError as e:
            logger.error("Plex plugin: token chiffré corrompu — secret ignoré (échec-faible): %s", e)
            config["plex_token"] = ""
        return
    # Legacy plaintext → chiffrement en place. Écriture directe (jamais via
    # _save_plex_config, qui relirait la config → récursion infinie).
    try:
        encrypted = encrypt_secret(token, _config_encryption_key())
        config["plex_token"] = encrypted
        await db.execute(
            "INSERT INTO plugins (id, enabled, config_json) VALUES ('plex', 1, ?) "
            "ON CONFLICT(id) DO UPDATE SET config_json = excluded.config_json",
            (json.dumps(config),),
        )
        if not db.in_transaction:
            await db.commit()
        await log_action(
            db,
            user_id="plex_plugin",
            action=AuditAction.CONFIGURE_PLUGIN,
            details={"plugin_id": "plex", "secret_migrated": "plex_token"},
        )
        # Le stockage est chiffré, mais le consommateur serveur reçoit le
        # clair : la valeur retournée par _get_plex_config doit être utilisable.
        config["plex_token"] = token
    except Exception as e:
        logger.error("Plex plugin: échec de la migration du token (conservé en clair): %s", e)


async def _get_plex_config(db: aiosqlite.Connection) -> dict:
    """Charge la config Plex depuis la DB.

    Chiffrement au repos (plan §5.1) : le token stocké est chiffré (``v1:...``)
    et déchiffré ici pour les consommateurs serveur ; tout token legacy en
    clair est migré en place (chiffré + audit) — idempotent.
    """
    try:
        cursor = await db.execute("SELECT config_json FROM plugins WHERE id = 'plex'")
        row = await cursor.fetchone()
        if row and row[0]:
            config = json.loads(row[0])
            await _migrate_and_decrypt_plex_config(db, config)
            return config
    except Exception as e:
        logger.error("Plex plugin: Failed to query config: %s", e)
    return {}


async def _save_plex_config(db: aiosqlite.Connection, updates: dict[str, Any]) -> dict[str, Any]:
    """Updates and saves Plex plugin config JSON in database.

    Chiffrement au repos : le token est TOUJOURS persisté chiffré (``v1:...``),
    jamais en clair — le chargement le déchiffre pour les consommateurs. La
    valeur retournée reste utilisable côté serveur (token déchiffré).
    """
    async with _config_save_lock:
        config = await _get_plex_config(db)
        config.update(updates)
        token = config.get("plex_token")
        stored = config
        if token and not token.startswith("v1:"):
            stored = dict(config)
            stored["plex_token"] = encrypt_secret(token, _config_encryption_key())
        config_json = json.dumps(stored)
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


# ---------------------------------------------------------------------------
# Flux OAuth Plex (T27-BE-2)
# ---------------------------------------------------------------------------

def _resolve_user_id(request: Request) -> str:
    """Identité de l'utilisateur depuis le Bearer token (claims["sub"])."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentification requise (Bearer token).")
    try:
        claims = get_security_instance().verify_access_token(auth[7:].strip())
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré.") from None
    return str(claims.get("sub", ""))


async def _create_pin(db: aiosqlite.Connection) -> dict[str, Any]:
    """Crée un PIN OAuth Plex (extrait de l'ancienne route /auth/pin)."""
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


async def _publish_auth_status(user_id: str, payload: dict[str, Any]) -> None:
    """Publie un statut sur le canal SSE scopé à l'utilisateur."""
    await get_event_bus().publish(f"{_AUTH_STATUS_TOPIC}:{user_id}", payload)


async def _poll_pin_flow(user_id: str, pin_id: int, db: aiosqlite.Connection) -> None:
    """Polling du PIN (120 × 1 s) : succès → sauvegarde config + audit +
    événement `success` ; timeout → événement `timeout`. Le token de quota
    est libéré uniquement sur annulation (voir auth_cancel_route)."""
    config = await _get_plex_config(db)
    client_id = _get_plex_client_id(config)
    headers = {"Accept": "application/json", "X-Plex-Client-Identifier": client_id}
    status = "timeout"
    try:
        for _ in range(_POLL_MAX_ATTEMPTS):
            flow = _auth_flows.get(user_id)
            if flow is None or flow.get("cancelled"):
                return
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.get(f"https://plex.tv/api/v2/pins/{pin_id}", headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        token = data.get("authToken") or data.get("auth_token")
                        if token:
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
                            await _save_plex_config(
                                db,
                                {"plex_token": token, "plex_username": user_name or "Plex User"},
                            )
                            await log_action(
                                db,
                                user_id=user_id,
                                action=AuditAction.CONFIGURE_PLUGIN,
                                details={"plugin_id": "plex", "oauth_user": user_name or "Plex User"},
                            )
                            if not db.in_transaction:
                                await db.commit()
                            status = "success"
                            break
            except Exception as e:
                logger.error("Failed to poll Plex PIN %s: %s", pin_id, e)
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    finally:
        async with _auth_flow_lock:
            flow = _auth_flows.get(user_id)
            if flow is not None and flow.get("task") is asyncio.current_task():
                flow["status"] = status
                if not flow.get("cancelled"):
                    await _publish_auth_status(user_id, {"status": status})
                token = flow.get("token")
                if token is not None:
                    await token.release()
                _auth_flows.pop(user_id, None)


async def _auth_status_stream(bus: EventBus, request: Request, topic: str) -> AsyncGenerator[str, None]:
    """Générateur SSE : replay du ring buffer + heartbeat 25 s (modèle
    ``plugins_events.py``), canal scopé à l'utilisateur."""
    queue = bus.subscribe(topic)
    try:
        for evt in bus.replay(topic):
            if await request.is_disconnected():
                return
            payload = evt.get("payload", {}) if isinstance(evt, dict) else {}
            yield f"event: {_AUTH_STATUS_TOPIC}\ndata: {json.dumps(payload)}\n\n"
            if payload.get("status") in ("success", "timeout", "cancelled"):
                return
        while True:
            if await request.is_disconnected():
                break
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=_SSE_KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            payload = evt.get("payload", {}) if isinstance(evt, dict) else {}
            yield f"event: {_AUTH_STATUS_TOPIC}\ndata: {json.dumps(payload)}\n\n"
            if payload.get("status") in ("success", "timeout", "cancelled"):
                break
    finally:
        bus.unsubscribe(topic, queue)


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
                c_names_raw = c.get("names", [])
                c_names = [n.lower() for n in c_names_raw] if isinstance(c_names_raw, list) else []

                # Check ports for 32400
                has_plex_port = False
                port = DEFAULT_PLEX_PORT
                ports = c.get("ports", [])
                if isinstance(ports, list):
                    for p in ports:
                        if isinstance(p, dict):
                            c_port = p.get("ContainerPort") or p.get("container_port")
                            h_port = p.get("HostPort") or p.get("host_port")
                            if c_port == 32400 or h_port == 32400:
                                has_plex_port = True
                                port = h_port or DEFAULT_PLEX_PORT
                                break

                is_plex_container = (
                    "plex" in c_name
                    or "plex" in c_image
                    or any("plex" in n for n in c_names)
                    or has_plex_port
                )

                if is_plex_container:
                    container_displayName = c.get("name") or (c_names_raw[0] if c_names_raw else "plex")
                    return {
                        "detected": True,
                        "port": port,
                        "type": "docker",
                        "container_name": str(container_displayName).lstrip("/"),
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
                s_name = str(s.get("service") or s.get("name") or s.get("unit") or "").lower()
                if "plex" in s_name or "pms" in s_name:
                    display_name = s.get("service") or s.get("name") or s.get("unit") or "plexmediaserver"
                    return {
                        "detected": True,
                        "port": DEFAULT_PLEX_PORT,
                        "type": "native",
                        "service_name": str(display_name),
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
                    p_name = str(p.get("name", "")).lower()
                    p_cmd_raw = p.get("cmdline", "")
                    p_cmd = " ".join(p_cmd_raw).lower() if isinstance(p_cmd_raw, list) else str(p_cmd_raw).lower()
                    if "plex" in p_name or "plex" in p_cmd:
                        return {
                            "detected": True,
                            "port": DEFAULT_PLEX_PORT,
                            "type": "native",
                            "status": "running",
                        }
            except Exception:
                logger.exception("Plex plugin: failed to parse metrics processes")

    # 4. HTTP Probe Fallback on host port 32400
    hostname = node.get("hostname")
    if hostname:
        probe_url = f"http://{hostname}:{DEFAULT_PLEX_PORT}/identity"
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                resp = await client.get(probe_url)
                if resp.status_code == 200 and ("Plex" in resp.text or "machineIdentifier" in resp.text):
                    return {
                        "detected": True,
                        "port": DEFAULT_PLEX_PORT,
                        "type": "native",
                        "status": "running",
                    }
        except Exception:
            pass

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
    """Legacy helper: JSON data or ``None`` (failure logged, swallowed).

    New code should prefer :func:`_query_plex_api_detailed` to surface the
    failure reason to the caller (actionable 502 details instead of a generic
    message when a route must fail).
    """
    data, _ = await _query_plex_api_detailed(url, path, token)
    return data


async def _query_plex_api_detailed(url: str, path: str, token: str) -> tuple[dict | None, str | None]:
    """JSON request on Plex API returning ``(data, failure_reason)``.

    ``failure_reason`` is ``None`` on success and a human-readable, actionable
    cause otherwise (connection error, timeout, non-200 status, non-JSON body).
    The attempted URL is always included so operators can spot unreachable
    LAN hostnames / stale ``plex_server_url`` values.
    """
    headers = {"Accept": "application/json"}
    params = {"X-Plex-Token": token}
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            response = await client.get(f"{url.rstrip('/')}{path}", headers=headers, params=params)
    except Exception as e:
        reason = f"connexion impossible à {url}{path} : {type(e).__name__}: {e}"
        logger.warning("Plex API connection failed to %s: %s", url, e)
        return None, reason
    if response.status_code != 200:
        reason = f"HTTP {response.status_code} de {url}{path}"
        logger.warning("Plex API %s%s returned HTTP %s", url, path, response.status_code)
        return None, reason
    try:
        return response.json(), None
    except Exception as e:
        reason = f"réponse non-JSON de {url}{path} : {type(e).__name__}: {e}"
        logger.warning("Plex API invalid JSON payload from %s: %s", url, e)
        return None, reason


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
        server_url = (config.get("plex_server_url") or "").strip()
        server_name = config.get("plex_server_name", "")

        detected = detection["detected"] or bool(server_url)
        det_type = detection["type"] or ("remote" if server_url else None)

        return {
            "node_id": node_id,
            "detected": detected,
            "type": det_type,
            "port": detection["port"],
            "status": detection.get("status") or ("configured" if server_url else None),
            "container_name": detection.get("container_name"),
            "service_name": detection.get("service_name"),
            "configured": configured,
            "server_url": server_url,
            "server_name": server_name,
        }

    @route("/{node_id}/sessions", method="GET", roles=["operator", "viewer"])
    async def sessions_route(self, node_id: str, db: aiosqlite.Connection = Depends(get_db_conn)) -> dict:
        """Returns currently active streaming sessions and auto-records watch history."""
        config = await _get_plex_config(db)
        client_info = await _get_plex_client_and_url(node_id, db, config)
        if not client_info:
            raise HTTPException(status_code=400, detail="Plex is not configured or not active on this node.")

        url, token = client_info
        data, api_error = await _query_plex_api_detailed(url, "/status/sessions", token)
        if not data:
            reason = api_error or "réponse vide"
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch sessions from Plex API. {reason}",
            )

        metadata = data.get("MediaContainer", {}).get("Metadata", [])
        sessions = []
        now = time.time()

        for item in metadata:
            transcode = item.get("TranscodeSession", {})
            user_info = item.get("User", {})
            player_info = item.get("Player", {})

            session_key_val = str(item.get("sessionKey") or "")
            user_val = user_info.get("title", "Unknown")
            title_val = item.get("title", "Sans titre")
            gp_val = item.get("grandparentTitle")
            media_type_val = item.get("type", "unknown")
            duration_val = float(item.get("duration", 1))
            offset_val = float(item.get("viewOffset", 0))
            progress_val = (offset_val / max(duration_val, 1.0)) * 100.0
            device_val = player_info.get("title", "Unknown Device")
            quality_val = "Transcode" if bool(transcode) else "Direct Play"

            session_obj = PlexSession(
                session_key=session_key_val,
                user=user_val,
                user_thumb=user_info.get("thumb"),
                title=title_val,
                grandparent_title=gp_val,
                parent_title=item.get("parentTitle"),
                media_type=media_type_val,
                progress_percent=progress_val,
                state=player_info.get("state", "playing"),
                player_device=device_val,
                player_platform=player_info.get("platform"),
                quality_profile=quality_val,
                bandwidth_kbps=item.get("Session", {}).get("bandwidth", 0),
                started_at=int(now),
                transcode=bool(transcode),
                video_decision=transcode.get("videoDecision"),
                audio_decision=transcode.get("audioDecision"),
                speed=float(transcode.get("speed")) if transcode.get("speed") else None,
                thumb=item.get("thumb"),
            )
            sessions.append(session_obj.model_dump())

            # Auto-record watch history if progress >= 10%
            if progress_val >= 10.0:
                try:
                    cutoff_10m = now - 600
                    async with db.execute(
                        "SELECT id FROM plex_watch_history WHERE node_id = ? AND user = ? AND title = ? AND viewed_at > ?",
                        (node_id, user_val, title_val, cutoff_10m),
                    ) as cur:
                        exists = await cur.fetchone()
                    if not exists:
                        await db.execute(
                            "INSERT INTO plex_watch_history (node_id, user, title, grandparent_title, media_type, viewed_at, duration_watched_s, progress_percent, device, quality) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (node_id, user_val, title_val, gp_val, media_type_val, now, int(offset_val / 1000), progress_val, device_val, quality_val),
                        )
                        await db.commit()
                except Exception as e:
                    logger.debug("Plex plugin: failed to auto-record watch history: %s", e)

        return {"sessions": sessions, "count": len(sessions)}

    @route("/{node_id}/sessions/{session_key}", method="DELETE", roles=["admin", "operator"])
    async def kill_session_route(self, node_id: str, session_key: str, db: aiosqlite.Connection = Depends(get_db_conn)) -> dict:
        """Terminates an active Plex streaming session."""
        config = await _get_plex_config(db)
        client_info = await _get_plex_client_and_url(node_id, db, config)
        if not client_info:
            raise HTTPException(status_code=400, detail="Plex is not configured.")

        url, token = client_info
        params = {"X-Plex-Token": token, "sessionId": session_key, "reason": "Interrompu par l'administrateur Vigile"}
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                await client.get(f"{url.rstrip('/')}/status/sessions/terminate", params=params)
                return {"status": "ok", "session_key": session_key}
        except Exception as e:
            logger.error("Failed to kill Plex session %s: %s", session_key, e)
            raise HTTPException(status_code=502, detail="Impossible d'interrompre la session sur le serveur Plex.")

    @route("/{node_id}/transcodes", method="GET", roles=["operator", "viewer"])
    async def transcodes_route(self, node_id: str, db: aiosqlite.Connection = Depends(get_db_conn)) -> dict:
        """Returns detailed active transcode sessions and active downloads/syncs."""
        config = await _get_plex_config(db)
        client_info = await _get_plex_client_and_url(node_id, db, config)
        if not client_info:
            raise HTTPException(status_code=400, detail="Plex is not configured.")

        url, token = client_info
        sessions_data = await _query_plex_api(url, "/status/sessions", token)
        sync_data = await _query_plex_api(url, "/sync/items", token) or {}

        transcodes = []
        downloads = []

        if sessions_data:
            metadata = sessions_data.get("MediaContainer", {}).get("Metadata", [])
            for item in metadata:
                ts = item.get("TranscodeSession")
                if ts:
                    user_info = item.get("User", {})
                    player_info = item.get("Player", {})
                    transcodes.append({
                        "session_key": item.get("sessionKey"),
                        "title": item.get("title"),
                        "grandparent_title": item.get("grandparentTitle"),
                        "user": user_info.get("title", "Unknown"),
                        "device": player_info.get("title", "Unknown Device"),
                        "video_decision": ts.get("videoDecision", "transcode"),
                        "audio_decision": ts.get("audioDecision", "copy"),
                        "video_codec": ts.get("videoCodec"),
                        "audio_codec": ts.get("audioCodec"),
                        "speed": float(ts.get("speed")) if ts.get("speed") else 1.0,
                        "progress": float(ts.get("progress", 0)),
                        "throttled": bool(ts.get("throttled", False)),
                        "bandwidth_kbps": item.get("Session", {}).get("bandwidth", 0),
                        "context": ts.get("context", "streaming"),
                    })

        sync_items = sync_data.get("MediaContainer", {}).get("SyncItem", [])
        for sync in sync_items:
            downloads.append({
                "id": sync.get("id"),
                "title": sync.get("title"),
                "user": sync.get("userName", "Utilisateur"),
                "state": sync.get("state", "pending"),
                "progress": float(sync.get("progress", 0)),
                "size_bytes": int(sync.get("size", 0)),
                "device_name": sync.get("deviceName", "Appareil mobile"),
            })

        return {
            "transcodes": transcodes,
            "transcodes_count": len(transcodes),
            "downloads": downloads,
            "downloads_count": len(downloads),
        }

    @route("/{node_id}/files", method="GET", roles=["operator", "viewer"])
    async def files_route(self, node_id: str, db: aiosqlite.Connection = Depends(get_db_conn)) -> dict:
        """Returns Plex media files breakdown and library disk locations."""
        config = await _get_plex_config(db)
        client_info = await _get_plex_client_and_url(node_id, db, config)
        if not client_info:
            raise HTTPException(status_code=400, detail="Plex is not configured.")

        url, token = client_info
        sections_data = await _query_plex_api(url, "/library/sections", token)
        if not sections_data:
            raise HTTPException(status_code=502, detail="Failed to fetch library sections.")

        directories = sections_data.get("MediaContainer", {}).get("Directory", [])
        libraries_files = []
        all_files = []
        total_storage_bytes = 0

        for dir_item in directories:
            sec_key = dir_item.get("key")
            sec_title = dir_item.get("title")
            sec_type = dir_item.get("type")
            locations = [loc.get("path") for loc in dir_item.get("Location", []) if loc.get("path")]

            # Query leaf items (/allLeaves) to retrieve Media.Part.size for all episodes, tracks, movies, photos
            items_data = await _query_plex_api(
                url,
                f"/library/sections/{sec_key}/allLeaves",
                token,
            )
            # Fallback to /all if /allLeaves is not available or returns no items
            if not items_data or not items_data.get("MediaContainer", {}).get("Metadata"):
                items_data = await _query_plex_api(
                    url,
                    f"/library/sections/{sec_key}/all",
                    token,
                )

            sec_files_count = 0
            sec_size_bytes = 0

            if items_data:
                meta = items_data.get("MediaContainer", {}).get("Metadata", [])
                sec_files_count = items_data.get("MediaContainer", {}).get("totalSize", len(meta))
                
                if sec_type == "show":
                    series_map: dict[str, dict] = {}
                    for m in meta:
                        show_title = m.get("grandparentTitle") or m.get("title") or "Série Inconnue"
                        if show_title not in series_map:
                            series_map[show_title] = {
                                "section": sec_title,
                                "section_type": sec_type,
                                "title": show_title,
                                "file_path": "",
                                "size_bytes": 0,
                                "items_count": 0,
                                "container": None,
                                "resolution": None,
                                "codec": None,
                                "added_at": 0,
                                "is_series": True,
                                "_paths": [],
                                "_resolutions": set(),
                            }
                        entry = series_map[show_title]
                        entry["items_count"] += 1
                        entry["added_at"] = max(entry["added_at"], m.get("addedAt") or 0)
                        
                        for media in m.get("Media", []):
                            if media.get("videoResolution"):
                                entry["_resolutions"].add(media.get("videoResolution"))
                            if not entry["container"] and media.get("container"):
                                entry["container"] = media.get("container")
                            if not entry["codec"] and media.get("videoCodec"):
                                entry["codec"] = media.get("videoCodec")
                            for part in media.get("Part", []):
                                f_size = int(part.get("size", 0))
                                sec_size_bytes += f_size
                                total_storage_bytes += f_size
                                entry["size_bytes"] += f_size
                                if part.get("file"):
                                    entry["_paths"].append(part.get("file"))
                    
                    for show_title, entry in series_map.items():
                        paths = entry.pop("_paths")
                        res_set = entry.pop("_resolutions")
                        if paths:
                            common_dir = os.path.dirname(os.path.dirname(paths[0])) if len(paths) > 0 else os.path.dirname(paths[0])
                            entry["file_path"] = f"{entry['items_count']} épisodes · {common_dir}"
                        else:
                            entry["file_path"] = f"{entry['items_count']} épisodes"
                        
                        if "4k" in res_set or "2160" in res_set:
                            entry["resolution"] = "4k"
                        elif "1080" in res_set:
                            entry["resolution"] = "1080p"
                        elif "720" in res_set:
                            entry["resolution"] = "720p"
                        elif "sd" in res_set or "480" in res_set or "576" in res_set:
                            entry["resolution"] = "SD"
                        elif res_set:
                            entry["resolution"] = next(iter(res_set))
                        
                        all_files.append(entry)
                else:
                    for m in meta:
                        title = m.get("title")
                        gp = m.get("grandparentTitle")
                        if gp:
                            title = f"{gp} - {title}"

                        media_list = m.get("Media", [])
                        for media in media_list:
                            v_res = media.get("videoResolution")
                            v_codec = media.get("videoCodec")
                            container = media.get("container")
                            parts = media.get("Part", [])
                            for part in parts:
                                f_path = part.get("file")
                                f_size = int(part.get("size", 0))
                                sec_size_bytes += f_size
                                total_storage_bytes += f_size
                                if f_path:
                                    all_files.append({
                                        "section": sec_title,
                                        "section_type": sec_type,
                                        "title": title,
                                        "file_path": f_path,
                                        "size_bytes": f_size,
                                        "container": container,
                                        "resolution": v_res,
                                        "codec": v_codec,
                                        "added_at": m.get("addedAt"),
                                        "is_series": False,
                                        "items_count": 1,
                                    })

            libraries_files.append({
                "key": sec_key,
                "title": sec_title,
                "type": sec_type,
                "locations": locations,
                "total_files": sec_files_count,
                "total_size_bytes": sec_size_bytes,
            })

        return {
            "libraries": libraries_files,
            "largest_files": sorted(all_files, key=lambda x: x["size_bytes"], reverse=True)[:50],
            "total_storage_bytes": total_storage_bytes,
        }

    @route("/{node_id}/library/{section_id}/scan", method="POST", roles=["admin", "operator"])
    async def scan_library_section_route(
        self, node_id: str, section_id: str, db: aiosqlite.Connection = Depends(get_db_conn)
    ) -> dict:
        """Triggers a library section refresh on Plex Media Server."""
        config = await _get_plex_config(db)
        client_info = await _get_plex_client_and_url(node_id, db, config)
        if not client_info:
            raise HTTPException(status_code=400, detail="Plex is not configured.")

        url, token = client_info
        params = {"X-Plex-Token": token}
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                await client.get(f"{url.rstrip('/')}/library/sections/{section_id}/refresh", params=params)
                return {"status": "ok", "section_id": section_id}
        except Exception as e:
            logger.error("Failed to scan library section %s: %s", section_id, e)
            raise HTTPException(status_code=502, detail="Impossible de lancer le scan de la bibliothèque.")

    @route("/{node_id}/photo", method="GET", roles=["operator", "viewer"])
    async def photo_proxy_route(
        self,
        node_id: str,
        path: str = Query(..., description="Relative Plex artwork path"),
        db: aiosqlite.Connection = Depends(get_db_conn),
    ) -> Response:
        """Secure Master photo proxy for Plex posters and artwork."""
        norm_path = posixpath.normpath(path)
        if (
            ".." in norm_path
            or norm_path.startswith("//")
            or "://" in norm_path
            or "\x00" in norm_path
            or not any(norm_path.startswith(prefix) for prefix in ALLOWED_ARTWORK_PREFIXES)
        ):
            raise HTTPException(status_code=400, detail="Invalid artwork path prefix.")

        config = await _get_plex_config(db)
        client_info = await _get_plex_client_and_url(node_id, db, config)
        if not client_info:
            raise HTTPException(status_code=400, detail="Plex is not configured.")

        url, token = client_info
        full_url = f"{url.rstrip('/')}{norm_path}"

        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
                resp = await client.get(full_url, params={"X-Plex-Token": token})
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail="Failed to fetch image from Plex.")

                content_type = resp.headers.get("content-type", "image/jpeg")
                if not content_type.startswith("image/"):
                    content_type = "image/jpeg"
                return Response(
                    content=resp.content,
                    media_type=content_type,
                    headers={"Cache-Control": "public, max-age=86400"},
                )
        except HTTPException:
            raise
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
        """Returns list of Plex home/shared users with last seen / connection timestamp."""
        config = await _get_plex_config(db)
        client_info = await _get_plex_client_and_url(node_id, db, config)
        if not client_info:
            raise HTTPException(status_code=400, detail="Plex is not configured or not active on this node.")

        url, token = client_info
        data = await _query_plex_api(url, "/accounts", token)
        if not data:
            raise HTTPException(status_code=502, detail="Failed to fetch accounts from Plex API.")

        accounts = data.get("MediaContainer", {}).get("Account", [])

        # 1. Fetch active sessions to detect currently online users
        active_sessions_data = await _query_plex_api(url, "/status/sessions", token)
        online_users = set()
        if active_sessions_data:
            sessions_list = active_sessions_data.get("MediaContainer", {}).get("Metadata", [])
            for s in sessions_list:
                u_title = s.get("User", {}).get("title")
                if u_title:
                    online_users.add(u_title.lower())

        # 2. Fetch recent history from Plex API to get last viewed timestamp per user
        history_data = await _query_plex_api(url, "/status/sessions/history/all?X-Plex-Container-Start=0&X-Plex-Container-Size=200", token)
        user_last_seen: dict[str, int] = {}
        if history_data:
            history_meta = history_data.get("MediaContainer", {}).get("Metadata", [])
            for h in history_meta:
                u_title = h.get("User", {}).get("title") or str(h.get("accountID", ""))
                v_at = int(h.get("viewedAt", 0))
                if u_title and v_at:
                    u_key = u_title.lower()
                    if u_key not in user_last_seen or v_at > user_last_seen[u_key]:
                        user_last_seen[u_key] = v_at

        # 3. Query local SQLite table as complementary/fallback source
        try:
            async with db.execute(
                "SELECT user, MAX(viewed_at) FROM plex_watch_history WHERE node_id = ? GROUP BY user", (node_id,)
            ) as cursor:
                for row in await cursor.fetchall():
                    u_name, v_at = row[0], row[1]
                    if u_name and v_at:
                        u_key = u_name.lower()
                        if u_key not in user_last_seen or v_at > user_last_seen[u_key]:
                            user_last_seen[u_key] = int(v_at)
        except Exception:
            pass

        users = []
        for item in accounts:
            name = item.get("name") or "Utilisateur"
            acc_id = str(item.get("id", ""))
            name_key = name.lower()
            acc_key = acc_id.lower()

            is_online = name_key in online_users
            last_seen = user_last_seen.get(name_key) or user_last_seen.get(acc_key)

            users.append({
                "id": acc_id,
                "name": name,
                "default_subtitle_language": item.get("defaultSubtitleLanguage"),
                "last_seen_at": last_seen,
                "is_online": is_online,
            })
        return {"users": users, "count": len(users)}

    @route("/{node_id}/history", method="GET", roles=["operator", "viewer"])
    async def history_route(
        self,
        node_id: str,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        query: Optional[str] = Query(default=None),
        media_type: Optional[str] = Query(default=None),
        db: aiosqlite.Connection = Depends(get_db_conn),
    ) -> dict:
        """Returns paginated watch history directly from Plex Media Server API (with SQLite fallback)."""
        config = await _get_plex_config(db)
        client_info = await _get_plex_client_and_url(node_id, db, config)

        if client_info:
            url, token = client_info
            plex_history_path = f"/status/sessions/history/all?X-Plex-Container-Start={offset}&X-Plex-Container-Size={limit}"
            history_data = await _query_plex_api(url, plex_history_path, token)

            if history_data and "MediaContainer" in history_data:
                mc = history_data.get("MediaContainer", {})
                metadata = mc.get("Metadata", [])
                total_plex = mc.get("totalSize") or mc.get("size") or len(metadata)

                entries = []
                for idx, item in enumerate(metadata):
                    user_info = item.get("User", {})
                    player_info = item.get("Player", {})

                    user_title = user_info.get("title") or item.get("accountID") or "Utilisateur"
                    title_val = item.get("title", "Sans titre")
                    gp_title = item.get("grandparentTitle")
                    m_type = item.get("type", "movie")
                    viewed_at = int(item.get("viewedAt", time.time()))
                    duration = int(float(item.get("duration", 0)) / 1000) if item.get("duration") else 0
                    device = player_info.get("title") or item.get("device", "Appareil")

                    if query:
                        q_lower = query.lower()
                        if (
                            q_lower not in str(user_title).lower()
                            and q_lower not in title_val.lower()
                            and q_lower not in str(gp_title or "").lower()
                        ):
                            continue
                    if media_type and m_type != media_type:
                        continue

                    entries.append(
                        PlexWatchHistoryEntry(
                            id=idx + offset + 1,
                            node_id=node_id,
                            user=str(user_title),
                            title=title_val,
                            grandparent_title=gp_title,
                            media_type=m_type,
                            viewed_at=viewed_at,
                            duration_watched_s=duration,
                            progress_percent=100.0,
                            device=str(device),
                            quality="Direct Play",
                        ).model_dump()
                    )

                return {"history": entries, "total": total_plex, "limit": limit, "offset": offset}

        # Fallback to SQLite table if Plex API is unavailable
        where_clauses = ["node_id = ?"]
        params: list[Any] = [node_id]

        if query:
            where_clauses.append("(title LIKE ? OR user LIKE ? OR grandparent_title LIKE ?)")
            q_like = f"%{query}%"
            params.extend([q_like, q_like, q_like])
        if media_type:
            where_clauses.append("media_type = ?")
            params.append(media_type)

        where_str = " AND ".join(where_clauses)
        count_sql = f"SELECT COUNT(*) FROM plex_watch_history WHERE {where_str}"
        select_sql = f"SELECT id, user, title, grandparent_title, media_type, viewed_at, duration_watched_s, progress_percent, device, quality FROM plex_watch_history WHERE {where_str} ORDER BY viewed_at DESC LIMIT ? OFFSET ?"

        async with db.execute(count_sql, params) as cursor:
            total_row = await cursor.fetchone()
            total = total_row[0] if total_row else 0

        fetch_params = list(params) + [limit, offset]
        async with db.execute(select_sql, fetch_params) as cursor:
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
        """Point d'entrée obsolète — remplacé par POST /plex.auth.start."""
        raise HTTPException(
            status_code=410,
            detail="Ce point d'entrée est obsolète. Utilisez POST /plex.auth.start.",
        )

    @route("/plex.auth.start", method="POST", roles=["admin", "operator"])
    async def auth_start_route(
        self,
        request: Request,
        db: aiosqlite.Connection = Depends(get_db_conn),
    ) -> dict:
        """Démarre un flux OAuth Plex pour l'utilisateur authentifié (Bearer).

        Un seul flux actif par utilisateur (409) ; quota de mutation du
        plugin consommé (429 si épuisé). Le polling (120 × 1 s) tourne en
        tâche de fond et publie le statut sur ``plex.auth.status:{user_id}``.
        """
        user_id = _resolve_user_id(request)
        pin = await _create_pin(db)
        async with _auth_flow_lock:
            if user_id in _auth_flows:
                raise HTTPException(
                    status_code=409,
                    detail="Un flux d'authentification Plex est déjà actif pour cet utilisateur.",
                )
            budget = await default_plugin_budget_provider("plex", PluginCallType.MUTATIONS)
            token = await plugin_rate_limiter.acquire("plex", user_id, PluginCallType.MUTATIONS, budget)
            if token is None:
                raise HTTPException(
                    status_code=429,
                    detail="Quota de flux d'authentification atteint, réessayez plus tard.",
                )
            task = asyncio.create_task(_poll_pin_flow(user_id, pin["id"], db))
            _auth_flows[user_id] = {"task": task, "token": token, "pin_id": pin["id"], "status": "waiting"}
            return {**pin, "status": "waiting"}

    @route("/plex.auth.cancel", method="POST", roles=["admin", "operator"])
    async def auth_cancel_route(
        self,
        request: Request,
        db: aiosqlite.Connection = Depends(get_db_conn),
    ) -> dict:
        """Annule le flux OAuth Plex actif de l'utilisateur (libère le quota)."""
        user_id = _resolve_user_id(request)
        async with _auth_flow_lock:
            flow = _auth_flows.pop(user_id, None)
            if flow is None:
                return {"status": "idle"}
            flow["cancelled"] = True
            task = flow.get("task")
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            token = flow.get("token")
            if token is not None:
                await token.release()
            await _publish_auth_status(user_id, {"status": "cancelled"})
            return {"status": "cancelled"}

    @route("/auth/status/stream", method="GET", roles=["admin", "operator"])
    async def auth_status_stream_route(
        self,
        request: Request,
        token: Optional[str] = Query(default=None),
        bus: EventBus = Depends(get_bus),
    ) -> StreamingResponse:
        """Flux SSE des statuts d'authentification Plex de l'utilisateur.

        Auth par ``?token=<jwt>`` (EventSource ne peut pas envoyer
        d'en-têtes) ; canal scopé ``plex.auth.status:{user_id}`` — aucun
        autre utilisateur ne reçoit ces événements.
        """
        if not token:
            raise HTTPException(
                status_code=401,
                detail="Missing token query parameter (EventSource cannot send Authorization headers)",
            )
        try:
            claims = get_security_instance().verify_access_token(token)
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired token") from None
        user_id = str(claims.get("sub", ""))
        topic = f"{_AUTH_STATUS_TOPIC}:{user_id}"
        return StreamingResponse(
            _auth_status_stream(bus, request, topic),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @route("/auth/verify", method="POST", roles=["admin", "operator"])
    async def auth_verify_route(
        self,
        payload: VerifyPinRequest,
        db: aiosqlite.Connection = Depends(get_db_conn),
    ) -> dict:
        """Vérifie le statut d'un PIN Plex — ne renvoie JAMAIS le token.

        Le token est sauvegardé en config (chiffré) si le PIN est autorisé ;
        la réponse ne contient que le statut (``success``/``pending``/
        ``timeout``) — le flux complet passe par POST /plex.auth.start.
        """
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
                if resp.status_code == 404:
                    return {"status": "timeout"}
                if resp.status_code != 200:
                    return {"status": "pending"}
                data = resp.json()
                token = data.get("authToken") or data.get("auth_token")
                if not token:
                    return {"status": "pending"}

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

                await _save_plex_config(
                    db,
                    {
                        "plex_token": token,
                        "plex_username": user_name or "Plex User",
                    },
                )
                return {"status": "success"}
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

async def auth_start_route(request: Request, db: aiosqlite.Connection) -> dict:
    from master.core.plugin_base import PluginContext
    ctx = PluginContext(plugin_id="plex", config={}, db=db)
    plugin = PlexPlugin(ctx)
    return await plugin.auth_start_route(request=request, db=db)

async def auth_cancel_route(request: Request, db: aiosqlite.Connection) -> dict:
    from master.core.plugin_base import PluginContext
    ctx = PluginContext(plugin_id="plex", config={}, db=db)
    plugin = PlexPlugin(ctx)
    return await plugin.auth_cancel_route(request=request, db=db)

async def auth_status_stream_route(
    request: Request,
    token: Optional[str] = None,
    bus: EventBus | None = None,
) -> StreamingResponse:
    from master.core.plugin_base import PluginContext
    ctx = PluginContext(plugin_id="plex", config={}, db=None)
    plugin = PlexPlugin(ctx)
    return await plugin.auth_status_stream_route(request=request, token=token, bus=bus)

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


