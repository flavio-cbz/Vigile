from __future__ import annotations

"""
Vigile — Admin API Router
Endpoints:
  - GET  /api/admin/audit-verify           → Verify audit log chain integrity
  - GET  /api/admin/nodes/connections       → List active worker node connections
  - GET  /api/admin/settings               → Get masked system settings
  - POST /api/admin/settings/llm           → Update LLM configuration
  - POST /api/admin/settings/llm/test      → Test connection to configured LLM
  - POST /api/admin/intent-config          → Update default intent max age
  - GET  /api/admin/plugins                → List all registered and available plugins
  - POST /api/admin/plugins/upload         → Upload a new plugin module
  - POST /api/admin/plugins/{plugin_id}/config → Update a plugin's DB configuration
  - POST /api/admin/plugins/{plugin_id}/toggle → Enable/disable a plugin dynamically
  - DELETE /api/admin/plugins/{plugin_id}  → Uninstall a plugin module
  - GET  /api/admin/alerts                  → List all alerts with optional filters
  - GET  /api/admin/alerts/summary         → Alert summary with counts by severity
  - POST /api/admin/alerts/{alert_id}/acknowledge → Acknowledge an alert
  - GET  /api/admin/alerts/metrics         → Prometheus alert metrics
"""

import ast
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import anyio
import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, Response

from master.api.demo_data import is_demo
from master.api.deps import get_db, get_settings, require_role, reset_llm_clients
from master.api.schemas.admin import (
    IntentConfigUpdate,
    LLMSettingsUpdate,
    RegistryPluginResponse,
    RegistryResponse,
)
from master.api.worker_binary import refresh_binary_cache
from master.core.audit import AuditAction, log_action, verify_chain
from master.core.llm_client import LLMClient, LLMError
from master.core.node_manager import node_manager
from master.core.plugin_ids import canonical_plugin_id, plugin_file_stem
import master.core.plugin_manager as _pm_mod
from master.db.database import get_db_conn, transaction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _get_active_plugin_engine() -> Any:
    return _pm_mod.plugin_engine if _pm_mod.plugin_engine is not None else _pm_mod.plugin_manager



def _resolve_plugin_stem(plugin_id: str, plugins_dir: str) -> str:
    # Try progressively normalized candidates to tolerate display names,
    # title-cased labels, or mixed input as the plugin_id.
    candidates = [
        canonical_plugin_id(plugin_id),
        plugin_file_stem(plugin_id),
        plugin_id,
        plugin_id.lower(),
        plugin_id.replace(" ", "_"),
        plugin_id.lower().replace(" ", "_"),
        plugin_id.replace("-", "_"),
        plugin_id.lower().replace(" ", "_").replace("-", "_"),
    ]
    seen: set[str] = set()
    unique_candidates: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique_candidates.append(c)

    for candidate in unique_candidates:
        if os.path.isfile(os.path.join(plugins_dir, f"{candidate}.py")):
            return candidate
        if os.path.isdir(os.path.join(plugins_dir, candidate)):
            return candidate
    return plugin_file_stem(plugin_id)


def _resolve_plugin_path(plugin_id: str, plugin_stem: str, plugins_dir: str) -> str | None:
    """Return resolved file or directory path for a plugin, or None if non-existent."""
    candidates = [
        plugin_id,
        plugin_stem,
        canonical_plugin_id(plugin_id),
        plugin_file_stem(plugin_id),
    ]
    seen: set[str] = set()
    unique_candidates: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            unique_candidates.append(c)

    for cand in unique_candidates:
        py_path = os.path.join(plugins_dir, f"{cand}.py")
        if os.path.isfile(py_path):
            return py_path

        pkg_dir = os.path.join(plugins_dir, cand)
        if os.path.isdir(pkg_dir):
            pkg_init = os.path.join(pkg_dir, "__init__.py")
            pkg_manifest = os.path.join(pkg_dir, "manifest.json")
            if os.path.isfile(pkg_init) or os.path.isfile(pkg_manifest):
                return pkg_dir

        if os.path.isdir(pkg_dir):
            return pkg_dir

    return None



@router.get("/audit-verify", summary="Verify audit log integrity")
async def verify_audit_chain(
    claims=Depends(require_role("admin")),
) -> JSONResponse:
    """
    Walk the entire audit log and verify the SHA256 hash chain.
    Returns a report indicating whether the chain is intact.
    Admin only.
    """
    db = get_db_conn()
    report = await verify_chain(db)
    status_code = 200 if report["valid"] else 409
    return JSONResponse(report, status_code=status_code)


@router.get("/nodes/connections", summary="List active WebSocket connections")
async def list_active_connections(
    claims=Depends(require_role("admin")),
) -> JSONResponse:
    """Debug endpoint: show all currently connected Worker nodes."""
    return JSONResponse(
        {
            "connected_nodes": node_manager.connected_node_ids(),
            "count": len(node_manager.connected_node_ids()),
        }
    )


@router.get("/settings", summary="Get system settings")
async def get_system_settings(
    claims=Depends(require_role("admin", "operator")),
    settings=Depends(get_settings),
) -> JSONResponse:
    """Return system settings with sensitive keys masked. Admin or operator only."""
    masked_server_secret = "••••••••" if settings.server_secret_key else ""
    masked_jwt_secret = "••••••••" if settings.jwt_secret_key else ""
    masked_llm_key = "••••••••" if settings.llm_api_key else ""

    return JSONResponse(
        {
            "master_url": settings.master_url,
            "host": settings.host,
            "port": settings.port,
            "debug": settings.debug,
            "database_path": settings.database_path,
            "server_secret_key": masked_server_secret,
            "jwt_secret_key": masked_jwt_secret,
            "jwt_algorithm": settings.jwt_algorithm,
            "jwt_access_token_ttl": settings.jwt_access_token_ttl,
            "jwt_refresh_token_ttl": settings.jwt_refresh_token_ttl,
            "join_token_ttl": settings.join_token_ttl,
            "worker_token_ttl": settings.worker_token_ttl,
            "worker_token_rotation": settings.worker_token_rotation,
            "heartbeat_interval": settings.heartbeat_interval,
            "heartbeat_lost_threshold": settings.heartbeat_lost_threshold,
            "heartbeat_stale_threshold": settings.heartbeat_stale_threshold,
            "master_key_path": settings.master_key_path,
            "cors_origins": settings.cors_origins,
            "trusted_proxies": settings.trusted_proxies,
            "enforce_https": settings.enforce_https,
            "llm_base_url": settings.llm_base_url,
            "llm_api_key": masked_llm_key,
            "llm_model": settings.llm_model,
            "plugins_dir": settings.plugins_dir,
        }
    )


@router.post("/settings/llm", summary="Update LLM settings")
async def update_llm_settings(
    body: LLMSettingsUpdate,
    claims=Depends(require_role("admin")),
    db=Depends(get_db),
    settings=Depends(get_settings),
) -> JSONResponse:
    """Update LLM settings and persist overrides. Admin only."""
    if is_demo(claims):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Modifications non autorisées en mode démonstration.",
        )

    # Secure API key masking logic
    api_key_to_save = body.llm_api_key
    if api_key_to_save == "••••••••":
        api_key_to_save = settings.llm_api_key

    override_path = Path(settings.database_path).parent / "settings_override.json"
    override_path.parent.mkdir(parents=True, exist_ok=True)

    def _write_overrides() -> None:
        with override_path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "llm_base_url": body.llm_base_url,
                    "llm_api_key": api_key_to_save,
                    "llm_model": body.llm_model,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

    try:
        await anyio.to_thread.run_sync(_write_overrides)
    except Exception as e:
        logger.error("Failed to write settings overrides: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impossible d'enregistrer la configuration sur le disque.",
        )

    settings.apply_overrides(
        base_url=body.llm_base_url,
        api_key=api_key_to_save,
        model=body.llm_model,
    )

    # Reset lazy singletons in deps
    reset_llm_clients()

    await log_action(
        db,
        user_id=claims["sub"],
        action=AuditAction.UPDATE_LLM_SETTINGS,
        details={
            "llm_base_url": body.llm_base_url,
            "llm_model": body.llm_model,
            "api_key_updated": body.llm_api_key != "••••••••",
        },
    )

    masked_server_secret = "••••••••" if settings.server_secret_key else ""
    masked_jwt_secret = "••••••••" if settings.jwt_secret_key else ""
    masked_llm_key = "••••••••" if settings.llm_api_key else ""

    return JSONResponse(
        {
            "master_url": settings.master_url,
            "host": settings.host,
            "port": settings.port,
            "debug": settings.debug,
            "database_path": settings.database_path,
            "server_secret_key": masked_server_secret,
            "jwt_secret_key": masked_jwt_secret,
            "jwt_algorithm": settings.jwt_algorithm,
            "jwt_access_token_ttl": settings.jwt_access_token_ttl,
            "jwt_refresh_token_ttl": settings.jwt_refresh_token_ttl,
            "join_token_ttl": settings.join_token_ttl,
            "worker_token_ttl": settings.worker_token_ttl,
            "worker_token_rotation": settings.worker_token_rotation,
            "heartbeat_interval": settings.heartbeat_interval,
            "heartbeat_lost_threshold": settings.heartbeat_lost_threshold,
            "heartbeat_stale_threshold": settings.heartbeat_stale_threshold,
            "master_key_path": settings.master_key_path,
            "cors_origins": settings.cors_origins,
            "trusted_proxies": settings.trusted_proxies,
            "enforce_https": settings.enforce_https,
            "llm_base_url": settings.llm_base_url,
            "llm_api_key": masked_llm_key,
            "llm_model": settings.llm_model,
            "plugins_dir": settings.plugins_dir,
        }
    )


@router.post("/settings/llm/test", summary="Test LLM connection")
async def test_llm_settings(
    body: LLMSettingsUpdate,
    claims=Depends(require_role("admin")),
    settings=Depends(get_settings),
) -> JSONResponse:
    """Test LLM connection with the provided configuration. Admin only."""
    if is_demo(claims):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tests de connexion non autorisés en mode démonstration.",
        )

    api_key_to_test = body.llm_api_key
    if api_key_to_test == "••••••••":
        api_key_to_test = settings.llm_api_key

    client = LLMClient(
        base_url=body.llm_base_url, api_key=api_key_to_test, model=body.llm_model, timeout=10
    )
    try:
        await client.complete(messages=[{"role": "user", "content": "ping"}], max_tokens=5)
        return JSONResponse(
            {"status": "success", "message": "Configuration valide. Connexion réussie."}
        )
    except LLMError as e:
        return JSONResponse(
            {"status": "error", "message": f"Échec de l'appel LLM: {str(e)}"}, status_code=400
        )
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Erreur inattendue: {str(e)}"}, status_code=500
        )


@router.post("/intent-config", summary="Update default intent max age")
async def update_intent_config(
    body: IntentConfigUpdate,
    claims=Depends(require_role("admin")),
) -> JSONResponse:
    """Update the default max age for pending intents. Admin only."""
    node_manager.set_default_intent_max_age(body.default_intent_max_age)
    db = get_db_conn()
    await log_action(
        db,
        user_id=claims["sub"],
        action=AuditAction.UPDATE_INTENT_CONFIG,
        details={"default_intent_max_age": body.default_intent_max_age},
    )
    return JSONResponse({"status": "ok", "default_intent_max_age": body.default_intent_max_age})


@router.get("/plugins", summary="List loaded plugins and hooks")
async def list_plugins(
    claims=Depends(require_role("admin", "operator")),
    settings=Depends(get_settings),
) -> JSONResponse:
    """Get status, configuration, schema, and hooks of all plugins in the directory."""
    db = get_db_conn()

    # 1. Get enabled/disabled status and configs from database
    plugin_db_states = {}
    try:
        async with db.execute(
            "SELECT id, enabled, config_json FROM plugins"
        ) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                plugin_db_states[row[0]] = {"enabled": bool(row[1]), "config": json.loads(row[2])}
    except Exception as e:
        logger.error("Failed to query plugins table: %s", e)

    # 2. Scan directory
    plugins_dir = settings.plugins_dir
    plugin_files = []
    plugin_errors: dict[str, str] = {}
    if os.path.isdir(plugins_dir):
        for entry in sorted(os.listdir(plugins_dir)):
            if entry.endswith(".py") and not entry.startswith("_"):
                plugin_files.append(entry[:-3])
            elif os.path.isdir(os.path.join(plugins_dir, entry)):
                manifest_path = os.path.join(plugins_dir, entry, "manifest.json")
                if os.path.isfile(manifest_path):
                    plugin_files.append(entry)

    # 3. Build response for each plugin
    active_pm = _get_active_plugin_engine()
    result = []
    seen_ids: set[str] = set()
    for name in plugin_files:
        plugin_id = canonical_plugin_id(name)
        if plugin_id in seen_ids:
            continue
        seen_ids.add(plugin_id)
        _lp = getattr(active_pm, "_loaded_plugins", [])

        is_loaded = any(
            k in _lp or k in active_pm.loaded_plugins
            for k in (plugin_id, name, plugin_file_stem(plugin_id))
        )
        db_state = (
            plugin_db_states.get(plugin_id)
            or plugin_db_states.get(name)
            or plugin_db_states.get(plugin_file_stem(plugin_id))
            or {"enabled": True, "config": {}}
        )
        version = db_state.get("version", db_state.get("config", {}).get("version", "0.0.0"))

        path = os.path.join(plugins_dir, f"{name}.py")
        if not os.path.isfile(path):
            path = os.path.join(plugins_dir, name, "manifest.json")

        module_name = f"vigile.plugins.{name}" if name != plugin_id else f"vigile.plugins.{name}"

        meta = {
            "name": name.replace("_", " ").title(),
            "description": "Custom Python extension module.",
            "category": "System",
            "schema": {},
        }

        error: str | None = (
            plugin_errors.get(plugin_id)
            or plugin_errors.get(name)
            or plugin_errors.get(plugin_file_stem(plugin_id))
        )
        if error is None and not is_loaded and db_state["enabled"]:
            error = "Plugin not loaded"

        possible_mod_names = (
            f"master.plugins.{name}",
            f"master.plugins.{plugin_id}",
            f"vigile.plugins.{name}",
            f"vigile.plugins.{plugin_id}",
            name,
            plugin_id,
        )
        mod = next((sys.modules[m] for m in possible_mod_names if m in sys.modules), None)
        if mod is not None:
            if hasattr(mod, "get_config_schema"):
                try:
                    meta.update(mod.get_config_schema())
                except Exception:
                    pass

        elif getattr(active_pm, "_sandbox", False) and any(
            k in active_pm.loaded_plugins
            for k in (plugin_id, name, plugin_file_stem(plugin_id))
        ):
            wrapper = (
                getattr(active_pm, "_wrappers", {}).get(plugin_id)
                or getattr(active_pm, "_wrappers", {}).get(name)
                or getattr(active_pm, "_wrappers", {}).get(plugin_file_stem(plugin_id))
            )
            if wrapper and wrapper.schema:
                meta.update(wrapper.schema)

        if getattr(active_pm, "scanner", None) is not None:
            manifest = active_pm.scanner.get_manifest(plugin_id) or active_pm.scanner.get_manifest(name)
            if manifest is not None:
                version = manifest.version
                default_title = name.replace("_", " ").title()
                if meta.get("name") == default_title or manifest.name != default_title:
                    meta["name"] = manifest.name
                meta["description"] = manifest.description or meta["description"]


        plugin_hooks = []
        hooks_registry = active_pm.get_hooks()
        for hook_name, plugins in hooks_registry.items():
            if any(k in plugins for k in (plugin_id, name, plugin_file_stem(plugin_id))):
                plugin_hooks.append(hook_name)

        result.append(
            {
                "id": plugin_id,
                "name": meta["name"],
                "description": meta["description"],
                "category": meta["category"],
                "schema": meta["schema"],
                "enabled": db_state["enabled"],
                "config": db_state["config"],
                "loaded": is_loaded,
                "hooks": plugin_hooks,
                "path": path,
                "module": module_name,
                "error": error,
                "version": version,
            }
        )

    return JSONResponse(
        {
            "loaded_plugins": active_pm.loaded_plugins,
            "hooks": active_pm.get_hooks(),
            "plugins": result,
        }
    )


@router.get(
    "/plugins/registry",
    response_model=RegistryResponse,
    summary="Get available plugins from registry",
)
async def get_plugin_registry(
    claims=Depends(require_role("admin")),
    settings=Depends(get_settings),
) -> RegistryResponse:
    """Fetch the plugin registry list from remote or fallback."""
    registry_url = settings.plugin_registry_url
    logger.info("Fetching plugin registry from %s", registry_url)

    fallback_data = {
        "plugins": [
            {
                "id": "discord_alert",
                "name": "Discord Alerts",
                "description": "Send alert notifications to a Discord webhook on node state changes.",
                "author": "Vigile Team",
                "version": "1.0.0",
                "download_url": "https://raw.githubusercontent.com/flavio-cbz/Vigile-Plugins/main/plugins/discord_alert.py",
            },
            {
                "id": "slack_alert",
                "name": "Slack Alerts",
                "description": "Send alert notifications to a Slack webhook on node state changes.",
                "author": "Vigile Team",
                "version": "1.0.0",
                "download_url": "https://raw.githubusercontent.com/flavio-cbz/Vigile-Plugins/main/plugins/slack_alert.py",
            },
            {
                "id": "clean_logs",
                "name": "Clean Logs Utility",
                "description": "Periodically clean up large log files on target worker nodes.",
                "author": "Vigile Team",
                "version": "1.0.0",
                "download_url": "https://raw.githubusercontent.com/flavio-cbz/Vigile-Plugins/main/plugins/clean_logs.py",
            },
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(registry_url)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict) and "plugins" in data:
                    return RegistryResponse(
                        plugins=[RegistryPluginResponse(**p) for p in data["plugins"]]
                    )
            logger.warning("Remote registry returned status %d. Using fallback.", r.status_code)
    except Exception as e:
        logger.warning("Failed to fetch remote registry (%s). Using fallback.", e)

    return RegistryResponse(plugins=[RegistryPluginResponse(**p) for p in fallback_data["plugins"]])


@router.post("/plugins/registry/{plugin_id}/install", summary="Install a plugin from registry")
async def install_plugin(
    plugin_id: str,
    claims=Depends(require_role("admin")),
    settings=Depends(get_settings),
) -> JSONResponse:
    """Download, validate, and install a plugin from the registry by its ID."""
    if is_demo(claims):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Installation d'extensions non autorisée en mode démonstration.",
        )

    # 1. Fetch registry first to find the download URL
    registry = await get_plugin_registry(claims, settings)
    target_plugin = None
    for p in registry.plugins:
        if p.id == plugin_id:
            target_plugin = p
            break

    if not target_plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin '{plugin_id}' non trouvé dans le registre.",
        )

    # 2. Fetch the source code
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(target_plugin.download_url)
            if r.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Impossible de télécharger le fichier source (HTTP {r.status_code}).",
                )
            source = r.text
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Erreur lors du téléchargement de l'extension : {str(e)}",
        )

    # 3. Compilability checks
    try:
        compile(source, f"{plugin_id}.py", "exec")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur de syntaxe Python dans le code téléchargé : {str(e)}",
        )

    # 4. AST validation for register contract
    try:
        tree = ast.parse(source)
        has_register = False
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "register":
                has_register = True
                break
        if not has_register:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Validation du contrat échouée : le plugin doit définir une fonction 'register(pm)'.",
            )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Validation AST échouée : {str(e)}",
        )

    # 5. Sanitize and build paths
    if "/" in plugin_id or "\\" in plugin_id or ".." in plugin_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Nom d'extension invalide."
        )

    plugin_name = plugin_id
    plugin_path = os.path.join(settings.plugins_dir, f"{plugin_name}.py")
    os.makedirs(settings.plugins_dir, exist_ok=True)

    # 6. Write to disk using run_sync to prevent blocking the event loop (as per Phase 1)
    def _write_file():
        with open(plugin_path, "w", encoding="utf-8") as f:
            f.write(source)

    try:
        await anyio.to_thread.run_sync(_write_file)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Échec de l'écriture du fichier : {str(e)}",
        )

    # 7. Update database configuration
    db = get_db_conn()
    await db.execute(
        "INSERT OR IGNORE INTO plugins (id, enabled, config_json) VALUES (?, 1, '{}')",
        (plugin_name,),
    )
    await db.commit()

    # 8. Load the plugin into PluginManager
    active_pm = _get_active_plugin_engine()
    success = await active_pm.load_plugin(plugin_name, settings.plugins_dir)

    if not success:
        if os.path.exists(plugin_path):
            try:
                os.remove(plugin_path)
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impossible de charger le plugin dans PluginManager.",
        )

    # 9. Log audit action
    await log_action(
        db,
        user_id=claims["sub"],
        action=AuditAction.UPLOAD_PLUGIN,
        details={"plugin_id": plugin_name, "source": "registry"},
    )

    return JSONResponse(
        {"status": "success", "message": f"Plugin '{plugin_name}' installé et activé avec succès."}
    )


@router.post("/plugins/upload", summary="Upload a new plugin")
async def upload_plugin(
    file: UploadFile = File(...),
    claims=Depends(require_role("admin")),
    settings=Depends(get_settings),
) -> JSONResponse:
    if is_demo(claims):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Installation d'extensions non autorisée en mode démonstration.",
        )

    if file.filename is None:
        raise HTTPException(status_code=400, detail="Nom de fichier manquant.")
    if not file.filename.endswith(".py"):
        raise HTTPException(
            status_code=400, detail="Seuls les fichiers Python (.py) sont autorisés."
        )

    content = await file.read()
    source = content.decode("utf-8")

    try:
        compile(source, file.filename, "exec")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur de syntaxe Python: {str(e)}")

    # 2. AST validation for register contract
    try:
        tree = ast.parse(source)
        has_register = False
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "register":
                has_register = True
                break
        if not has_register:
            raise HTTPException(
                status_code=400,
                detail="Validation du contrat échouée: le plugin doit définir une fonction 'register(pm)'.",
            )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=f"Validation AST échouée: {str(e)}")

    filename = file.filename
    plugin_name = filename[:-3]
    if "/" in plugin_name or "\\" in plugin_name or ".." in plugin_name:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide.")

    plugin_path = os.path.join(settings.plugins_dir, filename)
    os.makedirs(settings.plugins_dir, exist_ok=True)

    def _write_uploaded_plugin() -> None:
        with open(plugin_path, "wb") as f:
            f.write(content)

    try:
        await anyio.to_thread.run_sync(_write_uploaded_plugin)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Échec de l'écriture du fichier: {str(e)}")

    db = get_db_conn()
    canonical_id = canonical_plugin_id(plugin_name)
    await db.execute(
        "INSERT OR IGNORE INTO plugins (id, enabled, config_json) VALUES (?, 1, '{}')",
        (canonical_id,),
    )
    await db.commit()

    active_pm = _get_active_plugin_engine()
    success = await active_pm.load_plugin(canonical_id, settings.plugins_dir)
    if not success:
        if os.path.exists(plugin_path):
            try:
                os.remove(plugin_path)
            except Exception:
                pass
        raise HTTPException(
            status_code=500, detail="Impossible de charger le plugin dans PluginManager."
        )

    await log_action(
        db,
        user_id=claims["sub"],
        action=AuditAction.UPLOAD_PLUGIN,
        details={"plugin_id": plugin_name},
    )

    return JSONResponse(
        {"status": "success", "message": f"Plugin '{plugin_name}' téléversé et activé avec succès."}
    )


@router.post("/plugins/{plugin_id}/config", summary="Update plugin configuration")
async def configure_plugin(
    plugin_id: str,
    config: dict[str, Any],
    claims=Depends(require_role("admin")),
    settings=Depends(get_settings),
) -> JSONResponse:
    if is_demo(claims):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Configuration des extensions non autorisée en mode démonstration.",
        )

    db = get_db_conn()

    raw_plugin_id = plugin_id
    plugin_id_canonical = canonical_plugin_id(plugin_id)

    # Validate plugin exists
    plugin_stem = _resolve_plugin_stem(raw_plugin_id, settings.plugins_dir)
    plugin_path = _resolve_plugin_path(raw_plugin_id, plugin_stem, settings.plugins_dir)
    if plugin_path is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' introuvable.")

    config_str = json.dumps(config)
    async with transaction(db):
        await db.execute(
            "INSERT INTO plugins (id, enabled, config_json) VALUES (?, 1, ?) "
            "ON CONFLICT(id) DO UPDATE SET config_json = excluded.config_json",
            (plugin_id_canonical, config_str),
        )
        await log_action(
            db,
            user_id=claims["sub"],
            action=AuditAction.CONFIGURE_PLUGIN,
            details={"plugin_id": plugin_id_canonical, "config": config},
        )

    return JSONResponse(
        {"status": "success", "message": f"Configuration du plugin '{plugin_id_canonical}' mise à jour."}
    )


@router.post("/plugins/{plugin_id}/toggle", summary="Toggle plugin state")
async def toggle_plugin(
    plugin_id: str,
    claims=Depends(require_role("admin")),
    settings=Depends(get_settings),
) -> JSONResponse:
    if is_demo(claims):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Contrôle des extensions non autorisé en mode démonstration.",
        )

    db = get_db_conn()

    raw_plugin_id = plugin_id
    plugin_id_canonical = canonical_plugin_id(plugin_file_stem(plugin_id))
    plugin_stem = _resolve_plugin_stem(raw_plugin_id, settings.plugins_dir)
    plugin_path = _resolve_plugin_path(raw_plugin_id, plugin_stem, settings.plugins_dir)
    if plugin_path is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' introuvable.")

    # Get current state
    enabled = True
    async with db.execute(
        "SELECT enabled FROM plugins WHERE id IN (?, ?, ?)",
        (plugin_id_canonical, plugin_stem, raw_plugin_id),
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            enabled = bool(row[0])

    new_state = not enabled
    async with transaction(db):
        await db.execute(
            "INSERT INTO plugins (id, enabled, config_json) VALUES (?, ?, '{}') "
            "ON CONFLICT(id) DO UPDATE SET enabled = excluded.enabled",
            (plugin_id_canonical, int(new_state)),
        )
        await log_action(
            db,
            user_id=claims["sub"],
            action=AuditAction.TOGGLE_PLUGIN,
            details={"plugin_id": plugin_id_canonical, "enabled": new_state},
        )

    # Reload or Unload dynamically
    active_pm = _get_active_plugin_engine()
    target_load_id = plugin_id_canonical
    if hasattr(active_pm, "get_manifest"):
        manifest = (
            active_pm.get_manifest(plugin_id_canonical)
            or active_pm.get_manifest(plugin_stem)
            or active_pm.get_manifest(raw_plugin_id)
        )
        if manifest and manifest.id:
            target_load_id = manifest.id

    success = True
    if new_state:
        if getattr(active_pm, "_disabled_plugins", None) is not None:
            active_pm._disabled_plugins.discard(plugin_id_canonical)
            active_pm._disabled_plugins.discard(plugin_stem)
            active_pm._disabled_plugins.discard(raw_plugin_id)
        # Unload existing instance if loaded (single targeted call)
        if target_load_id in getattr(active_pm, "loaded_plugins", []):
            await active_pm.unload_plugin(target_load_id)

        success = await active_pm.load_plugin(target_load_id, settings.plugins_dir)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Plugin '{plugin_id_canonical}' enabled in DB but failed to load in runtime.",
            )
    else:
        # Single targeted unload — engine handles hooks, scheduler, routes, pages, DB
        await active_pm.unload_plugin(target_load_id)

    return JSONResponse(
        {
            "status": "success",
            "message": f"Plugin '{plugin_id_canonical}' est maintenant {'activé' if new_state else 'désactivé'}.",
            "loaded": new_state and success,
        }
    )


@router.delete("/plugins/{plugin_id}", summary="Uninstall plugin")
async def delete_plugin(
    plugin_id: str,
    claims=Depends(require_role("admin")),
    settings=Depends(get_settings),
) -> JSONResponse:
    if is_demo(claims):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Désinstallation d'extensions non autorisée en mode démonstration.",
        )

    raw_plugin_id = plugin_id
    plugin_id_canonical = canonical_plugin_id(plugin_id)

    if plugin_id_canonical in ["metrics", "systemd", "docker", "disk_analysis"]:
        raise HTTPException(
            status_code=400,
            detail="Les extensions intégrées au système ne peuvent pas être supprimées.",
        )

    db = get_db_conn()

    # Validate plugin exists
    plugin_stem = _resolve_plugin_stem(raw_plugin_id, settings.plugins_dir)
    plugin_path = _resolve_plugin_path(raw_plugin_id, plugin_stem, settings.plugins_dir)
    if plugin_path is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' introuvable.")

    active_pm = _get_active_plugin_engine()
    for k in {plugin_id_canonical, plugin_stem, raw_plugin_id}:
        if hasattr(active_pm, "uninstall"):
            try:
                await active_pm.uninstall(k)
            except Exception as e:
                logger.error("Failed to uninstall plugin '%s' via engine: %s", k, e)
                await active_pm.unload_plugin(k)
        else:
            await active_pm.unload_plugin(k)

    # 2. Remove file/directory from disk
    try:
        if os.path.isdir(plugin_path):
            shutil.rmtree(plugin_path)
        elif os.path.isfile(plugin_path):
            os.remove(plugin_path)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Impossible de supprimer le fichier du plugin : {str(e)}"
        )

    # 3. Clean up database entry + audit log in same transaction
    async with transaction(db):
        await db.execute("DELETE FROM plugins WHERE id = ? OR id = ?", (plugin_id, plugin_stem))
        await log_action(
            db,
            user_id=claims["sub"],
            action=AuditAction.DELETE_PLUGIN,
            details={"plugin_id": plugin_id},
        )

    return JSONResponse(
        {"status": "success", "message": f"Plugin '{plugin_id}' désinstallé avec succès."}
    )


@router.get("/binary/refresh", summary="Force re-fetch of worker binary cache")
async def admin_refresh_binary_cache(
    claims=Depends(require_role("admin")),
) -> JSONResponse:
    result = await refresh_binary_cache()
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


@router.get("/alerts", summary="List all alerts with optional filters")
async def list_alerts(
    node_id: str | None = None,
    status: str | None = None,  # firing | resolved
    severity: str | None = None,  # info | warning | critical
    limit: int = 100,
    offset: int = 0,
    db=Depends(get_db),
    claims=Depends(require_role("operator")),
) -> JSONResponse:
    """
    Liste paginée des alertes. Filtrable par nœud, statut, sévérité.
    Accessible aux rôles operator et admin.
    """
    conditions = ["1=1"]
    params: list = []

    if node_id:
        conditions.append("alerts.node_id = ?")
        params.append(node_id)
    if status:
        conditions.append("alerts.status = ?")
        params.append(status)
    if severity:
        conditions.append("alerts.severity = ?")
        params.append(severity)

    where = " AND ".join(conditions)

    # Total count
    count_sql = "SELECT COUNT(*) as cnt FROM alerts WHERE " + where
    async with db.execute(count_sql, params) as cursor:
        row = await cursor.fetchone()
        total = row["cnt"] if row else 0

    # Rows
    rows_sql = (
        "SELECT alerts.*, nodes.name as node_name, nodes.hostname as node_hostname "
        "FROM alerts LEFT JOIN nodes ON alerts.node_id = nodes.id "
        "WHERE " + where + " ORDER BY alerts.created_at DESC LIMIT ? OFFSET ?"
    )
    async with db.execute(rows_sql, [*params, limit, offset]) as cursor:
        rows = await cursor.fetchall()

    alerts_list = [dict(r) for r in rows]

    return JSONResponse({
        "total": total,
        "limit": limit,
        "offset": offset,
        "alerts": alerts_list,
    })


@router.get("/alerts/summary", summary="Alert summary with counts by severity")
async def alert_summary(
    db=Depends(get_db),
    claims=Depends(require_role("operator")),
) -> JSONResponse:
    """Retourne le résumé des alertes actives et les compteurs par sévérité."""
    # Compteurs par sévérité depuis la base
    async with db.execute(
        "SELECT severity, COUNT(*) as cnt FROM alerts WHERE status = 'firing' GROUP BY severity"
    ) as cursor:
        rows = await cursor.fetchall()
    by_severity: dict[str, int] = {"critical": 0, "warning": 0, "info": 0}
    for row in rows:
        by_severity[row["severity"]] = row["cnt"]

    # Top alertes récentes (10 dernières)
    async with db.execute(
        "SELECT alerts.*, nodes.name as node_name "
        "FROM alerts LEFT JOIN nodes ON alerts.node_id = nodes.id "
        "WHERE alerts.status = 'firing' "
        "ORDER BY alerts.created_at DESC LIMIT 10"
    ) as cursor:
        recent = [dict(r) for r in await cursor.fetchall()]

    # Total
    async with db.execute(
        "SELECT COUNT(*) as cnt FROM alerts WHERE status = 'firing'"
    ) as cursor:
        row = await cursor.fetchone()
        total = row["cnt"] if row else 0

    return JSONResponse({
        "total_active": total,
        "by_severity": by_severity,
        "recent": recent,
    })


@router.post("/alerts/{alert_id}/acknowledge", summary="Acknowledge an alert")
async def acknowledge_alert(
    alert_id: str,
    db=Depends(get_db),
    claims=Depends(require_role("operator")),
) -> JSONResponse:
    """Marque une alerte comme acquittée (la supprime de la vue active)."""
    async with db.execute(
        "UPDATE alerts SET status = 'resolved', resolved_at = ?, updated_at = ? WHERE id = ? AND status = 'firing'",
        (time.time(), time.time(), alert_id),
    ) as cursor:
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Alert not found or already resolved")
    return JSONResponse({"status": "success", "message": "Alert acknowledged."})


# ---------------------------------------------------------------------------
# Prometheus alert metrics
# ---------------------------------------------------------------------------


@router.get(
    "/alerts/metrics",
    summary="Prometheus alert metrics",
    response_class=Response,
)
async def alerts_prometheus_metrics(
    db=Depends(get_db),
    claims=Depends(require_role("operator")),
) -> Response:
    """Return alert metrics in Prometheus exposition format."""
    lines = [
        "# HELP vigile_alerts_total Total number of alerts by severity and status",
        "# TYPE vigile_alerts_total counter",
    ]

    async with db.execute(
        "SELECT severity, status, COUNT(*) as cnt FROM alerts GROUP BY severity, status"
    ) as cursor:
        rows = await cursor.fetchall()
    for row in rows:
        lines.append(
            f'vigile_alerts_total{{severity="{row["severity"]}",status="{row["status"]}"}} {row["cnt"]}'
        )

    lines.append("")
    lines.append(
        "# HELP vigile_active_alerts Current number of firing alerts by severity"
    )
    lines.append("# TYPE vigile_active_alerts gauge")

    async with db.execute(
        "SELECT severity, COUNT(*) as cnt FROM alerts WHERE status = 'firing' GROUP BY severity"
    ) as cursor:
        rows = await cursor.fetchall()
    for row in rows:
        lines.append(
            f'vigile_active_alerts{{severity="{row["severity"]}"}} {row["cnt"]}'
        )

    lines.append("")
    lines.append(
        "# HELP vigile_alert_names_total Total alerts by name"
    )
    lines.append("# TYPE vigile_alert_names_total counter")

    async with db.execute(
        "SELECT alert_name, COUNT(*) as cnt FROM alerts GROUP BY alert_name ORDER BY cnt DESC LIMIT 20"
    ) as cursor:
        rows = await cursor.fetchall()
    for row in rows:
        safe_name = row["alert_name"].replace("-", "_").replace(".", "_")
        lines.append(
            f'vigile_alert_names_total{{alert_name="{safe_name}"}} {row["cnt"]}'
        )

    lines.append("")
    return Response(
        content="\n".join(lines) + "\n",
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
