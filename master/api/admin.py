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
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

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
from master.core.node_manager import node_manager
from master.core.plugin_manager import canonical_plugin_id, plugin_file_stem, plugin_manager
from master.db.database import get_db_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _resolve_plugin_stem(plugin_id: str, plugins_dir: str) -> str:
    for candidate in (plugin_file_stem(plugin_id), plugin_id):
        if os.path.isfile(os.path.join(plugins_dir, f"{candidate}.py")):
            return candidate
    return plugin_file_stem(plugin_id)


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

    try:
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

    from master.core.llm_client import LLMClient, LLMError

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
            "SELECT plugin_id, enabled, config_json FROM plugin_configs"
        ) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                plugin_db_states[row[0]] = {"enabled": bool(row[1]), "config": json.loads(row[2])}
    except Exception as e:
        logger.error("Failed to query plugin_configs table: %s", e)

    # 2. Scan directory
    plugins_dir = settings.plugins_dir
    plugin_files = []
    if os.path.isdir(plugins_dir):
        for fname in sorted(os.listdir(plugins_dir)):
            if fname.endswith(".py") and not fname.startswith("_"):
                plugin_files.append(fname[:-3])

    # 3. Build response for each plugin
    result = []
    for name in plugin_files:
        plugin_id = canonical_plugin_id(name)
        is_loaded = plugin_id in plugin_manager.loaded_plugins
        db_state = plugin_db_states.get(plugin_id, {"enabled": True, "config": {}})

        # Dynamically inspect metadata and schema if loaded
        meta = {
            "name": name.replace("_", " ").title(),
            "description": "Custom Python extension module.",
            "category": "System",
            "schema": {},
        }

        module_name = f"vigile.plugins.{name}"
        if module_name in sys.modules:
            mod = sys.modules[module_name]
            if hasattr(mod, "get_config_schema"):
                try:
                    meta.update(mod.get_config_schema())
                except Exception:
                    pass

        # Find hooks registered by this plugin
        plugin_hooks = []
        hooks_registry = plugin_manager.get_hooks()
        for hook_name, plugins in hooks_registry.items():
            if plugin_id in plugins:
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
            }
        )

    return JSONResponse(
        {
            "loaded_plugins": plugin_manager.loaded_plugins,
            "hooks": plugin_manager.get_hooks(),
            "plugins": result,
        }
    )


@router.get("/plugins/registry", response_model=RegistryResponse, summary="Get available plugins from registry")
async def get_plugin_registry(
    claims=Depends(require_role("admin")),
    settings=Depends(get_settings),
) -> RegistryResponse:
    """Fetch the plugin registry list from remote or fallback."""
    import httpx

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
                    return RegistryResponse(plugins=data["plugins"])
            logger.warning("Remote registry returned status %d. Using fallback.", r.status_code)
    except Exception as e:
        logger.warning("Failed to fetch remote registry (%s). Using fallback.", e)

    return RegistryResponse(plugins=fallback_data["plugins"])


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
    import httpx
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
    import ast
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nom d'extension invalide.")

    plugin_name = plugin_id
    plugin_path = os.path.join(settings.plugins_dir, f"{plugin_name}.py")
    os.makedirs(settings.plugins_dir, exist_ok=True)

    # 6. Write to disk using run_sync to prevent blocking the event loop (as per Phase 1)
    import anyio

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
        "INSERT OR IGNORE INTO plugin_configs (plugin_id, enabled, config_json) VALUES (?, 1, '{}')",
        (plugin_name,),
    )
    await db.commit()

    # 8. Load the plugin into PluginManager
    success = plugin_manager.load_plugin(plugin_name, settings.plugins_dir)
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
    import ast

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

    plugin_name = file.filename[:-3]
    if "/" in plugin_name or "\\" in plugin_name or ".." in plugin_name:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide.")

    plugin_path = os.path.join(settings.plugins_dir, file.filename)
    os.makedirs(settings.plugins_dir, exist_ok=True)

    try:
        with open(plugin_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Échec de l'écriture du fichier: {str(e)}")

    db = get_db_conn()
    await db.execute(
        "INSERT OR IGNORE INTO plugin_configs (plugin_id, enabled, config_json) VALUES (?, 1, '{}')",
        (plugin_name,),
    )
    await db.commit()

    success = plugin_manager.load_plugin(plugin_name, settings.plugins_dir)
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
        db, user_id=claims["sub"], action=AuditAction.UPLOAD_PLUGIN, details={"plugin_id": plugin_name}
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

    # Validate plugin exists
    plugin_stem = _resolve_plugin_stem(plugin_id, settings.plugins_dir)
    plugin_path = os.path.join(settings.plugins_dir, f"{plugin_stem}.py")
    if not os.path.isfile(plugin_path):
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' introuvable.")

    config_str = json.dumps(config)
    await db.execute(
        "INSERT INTO plugin_configs (plugin_id, enabled, config_json) VALUES (?, 1, ?) "
        "ON CONFLICT(plugin_id) DO UPDATE SET config_json = excluded.config_json",
        (plugin_id, config_str),
    )
    await db.commit()

    # Log audit
    await log_action(
        db,
        user_id=claims["sub"],
        action=AuditAction.CONFIGURE_PLUGIN,
        details={"plugin_id": plugin_id, "config": config},
    )

    return JSONResponse(
        {"status": "success", "message": f"Configuration du plugin '{plugin_id}' mise à jour."}
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

    # Validate plugin exists
    plugin_stem = _resolve_plugin_stem(plugin_id, settings.plugins_dir)
    plugin_path = os.path.join(settings.plugins_dir, f"{plugin_stem}.py")
    if not os.path.isfile(plugin_path):
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' introuvable.")

    # Get current state
    enabled = True
    async with db.execute(
        "SELECT enabled FROM plugin_configs WHERE plugin_id = ?", (plugin_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            enabled = bool(row[0])

    new_state = not enabled
    await db.execute(
        "INSERT INTO plugin_configs (plugin_id, enabled, config_json) VALUES (?, ?, '{}') "
        "ON CONFLICT(plugin_id) DO UPDATE SET enabled = excluded.enabled",
        (plugin_id, int(new_state)),
    )
    await db.commit()

    # Reload or Unload dynamically
    if new_state:
        plugin_manager.load_plugin(plugin_stem, settings.plugins_dir)
    else:
        await plugin_manager.unload_plugin(plugin_stem)

    # Log audit
    await log_action(
        db,
        user_id=claims["sub"],
        action=AuditAction.TOGGLE_PLUGIN,
        details={"plugin_id": plugin_id, "enabled": new_state},
    )

    return JSONResponse(
        {
            "status": "success",
            "message": f"Plugin '{plugin_id}' est maintenant {'activé' if new_state else 'désactivé'}.",
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

    if plugin_id in ["metrics", "systemd", "docker"]:
        raise HTTPException(
            status_code=400,
            detail="Les extensions intégrées au système ne peuvent pas être supprimées.",
        )

    db = get_db_conn()

    # Validate plugin exists
    plugin_stem = _resolve_plugin_stem(plugin_id, settings.plugins_dir)
    plugin_path = os.path.join(settings.plugins_dir, f"{plugin_stem}.py")
    if not os.path.isfile(plugin_path):
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' introuvable.")

    # 1. Unload hooks dynamically
    await plugin_manager.unload_plugin(plugin_stem)

    # 2. Remove file from disk
    try:
        os.remove(plugin_path)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Impossible de supprimer le fichier du plugin : {str(e)}"
        )

    # 3. Clean up database entry
    await db.execute("DELETE FROM plugin_configs WHERE plugin_id = ?", (plugin_id,))
    await db.commit()

    # 4. Log audit
    await log_action(
        db, user_id=claims["sub"], action=AuditAction.DELETE_PLUGIN, details={"plugin_id": plugin_id}
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
