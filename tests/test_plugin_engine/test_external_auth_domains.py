from __future__ import annotations

"""
T27-BE-2 — Garde-fou `external_auth_domains` (A.1 + A.2/A.3).

A.1 : le champ `external_auth_domains` déclaré dans un manifest V1 (sans
`schema_version`) survit à la migration V1→V2 (recopié par
`_attach_raw_extras` au scan).
A.2/A.3 : les routes POST d'un plugin déclarant des domaines sont
enveloppées d'un garde-fou — toute URL d'auth externe hors domaines est
rejetée (502 + audit SECURITY_INCIDENT). Les GET ne sont pas enveloppés
(URL LAN http:// légitimes en config, ex. plex_server_url).
"""

import json

import aiosqlite
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from master.core.audit import AuditAction
from master.core.plugin_base import PluginBase, PluginContext, route
from master.core.plugin_engine import _attach_raw_extras
from master.core.plugin_manifest import load_and_validate_manifest
from master.core.route_registrar import RouteRegistrar
from master.db.database import get_db_conn


class _AuthUrlPlugin(PluginBase):
    plugin_id = "authurl"

    @route("/evil", method="POST", roles=["admin"])
    async def evil_route(self, db: aiosqlite.Connection = Depends(get_db_conn)) -> dict:
        return {"auth_url": "https://evil.com/callback"}

    @route("/good", method="POST", roles=["admin"])
    async def good_route(self, db: aiosqlite.Connection = Depends(get_db_conn)) -> dict:
        return {"auth_url": "https://app.plex.tv/auth"}

    @route("/subdomain-spoof", method="POST", roles=["admin"])
    async def subdomain_spoof_route(
        self, db: aiosqlite.Connection = Depends(get_db_conn)
    ) -> dict:
        return {"auth_url": "https://plex.tv.attacker.com/"}

    @route("/http-scheme", method="POST", roles=["admin"])
    async def http_scheme_route(self, db: aiosqlite.Connection = Depends(get_db_conn)) -> dict:
        return {"auth_url": "http://app.plex.tv/auth"}

    @route("/lan-config", method="POST", roles=["admin"])
    async def lan_config_route(self, db: aiosqlite.Connection = Depends(get_db_conn)) -> dict:
        # URL LAN http:// dans une clé NON-auth (plex_server_url) — jamais flaggée
        return {"plex_server_url": "http://192.168.1.50:32400"}


class _NoDomainsPlugin(PluginBase):
    plugin_id = "nodomains"

    @route("/evil", method="POST", roles=["admin"])
    async def evil_route(self, db: aiosqlite.Connection = Depends(get_db_conn)) -> dict:
        return {"auth_url": "https://evil.com/callback"}


def _mount(app: FastAPI, plugin_cls: type[PluginBase], domains: list[str] | None) -> None:
    registrar = RouteRegistrar(app)
    ctx = PluginContext(plugin_id=plugin_cls.plugin_id, config={}, db=None)
    instance = plugin_cls(ctx)
    registrar.mount(plugin_cls.plugin_id, instance.routes, instance, external_auth_domains=domains)


@pytest.fixture
def guarded_app(db: aiosqlite.Connection) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_db_conn] = lambda: db
    _mount(app, _AuthUrlPlugin, ["plex.tv"])
    return app


@pytest.fixture
def unguarded_app(db: aiosqlite.Connection) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_db_conn] = lambda: db
    _mount(app, _NoDomainsPlugin, None)
    return app


async def _post(app: FastAPI, path: str) -> tuple[int, dict]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(path)
        try:
            body = resp.json()
        except ValueError:
            body = {}
        return resp.status_code, body


async def _count_audit_incidents(db: aiosqlite.Connection) -> int:
    cursor = await db.execute(
        "SELECT COUNT(*) FROM audit_log WHERE action = ?",
        (AuditAction.SECURITY_INCIDENT.value,),
    )
    row = await cursor.fetchone()
    return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# A.1 — survie du champ à la migration V1→V2 (scan)
# ---------------------------------------------------------------------------


def test_attach_raw_extras_preserves_external_auth_domains():
    raw_v1 = {
        "id": "plex",
        "name": "Plex",
        "version": "1.0.0",
        "author": "Vigile",
        "trusted": True,
        "description": "Plex integration",
        "external_auth_domains": ["plex.tv"],
        "routes": [],
    }
    v2 = _attach_raw_extras(load_and_validate_manifest(raw_v1), raw_v1)
    assert v2.external_auth_domains == ["plex.tv"]


def test_attach_raw_extras_does_not_override_v2_declared_domains():
    raw_v2 = {
        "schema_version": 2,
        "id": "plex",
        "version": "1.0.0",
        "external_auth_domains": ["plex.tv"],
        "routes": [],
    }
    v2 = _attach_raw_extras(load_and_validate_manifest(raw_v2), raw_v2)
    assert v2.external_auth_domains == ["plex.tv"]


def test_attach_raw_extras_absent_field_stays_none():
    raw_v1 = {
        "id": "plex",
        "name": "Plex",
        "version": "1.0.0",
        "author": "Vigile",
        "trusted": True,
        "description": "Plex integration",
        "routes": [],
    }
    v2 = _attach_raw_extras(load_and_validate_manifest(raw_v1), raw_v1)
    assert v2.external_auth_domains is None


# ---------------------------------------------------------------------------
# A.2/A.3 — garde-fou sur les routes POST
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guard_rejects_evil_url(guarded_app: FastAPI, db: aiosqlite.Connection):
    status, body = await _post(guarded_app, "/api/plugins/authurl/evil")
    assert status == 502
    assert "evil.com" in body.get("detail", "")
    assert await _count_audit_incidents(db) == 1


@pytest.mark.asyncio
async def test_guard_allows_declared_domain(guarded_app: FastAPI, db: aiosqlite.Connection):
    status, body = await _post(guarded_app, "/api/plugins/authurl/good")
    assert status == 200
    assert body["auth_url"] == "https://app.plex.tv/auth"
    assert await _count_audit_incidents(db) == 0


@pytest.mark.asyncio
async def test_guard_rejects_subdomain_spoof(guarded_app: FastAPI, db: aiosqlite.Connection):
    # plex.tv.attacker.com ne finit pas par ".plex.tv" → rejeté
    status, body = await _post(guarded_app, "/api/plugins/authurl/subdomain-spoof")
    assert status == 502
    assert await _count_audit_incidents(db) == 1


@pytest.mark.asyncio
async def test_guard_rejects_http_scheme(guarded_app: FastAPI, db: aiosqlite.Connection):
    # https uniquement — http:// même sur un domaine autorisé est rejeté
    status, body = await _post(guarded_app, "/api/plugins/authurl/http-scheme")
    assert status == 502
    assert await _count_audit_incidents(db) == 1


@pytest.mark.asyncio
async def test_guard_ignores_non_auth_lan_url(guarded_app: FastAPI, db: aiosqlite.Connection):
    # plex_server_url (URL LAN http://) n'est pas une clé d'auth → passe
    status, body = await _post(guarded_app, "/api/plugins/authurl/lan-config")
    assert status == 200
    assert body["plex_server_url"] == "http://192.168.1.50:32400"
    assert await _count_audit_incidents(db) == 0


@pytest.mark.asyncio
async def test_no_domains_means_no_guard(unguarded_app: FastAPI, db: aiosqlite.Connection):
    # Plugin sans external_auth_domains → comportement inchangé (pas de garde-fou)
    status, body = await _post(unguarded_app, "/api/plugins/nodomains/evil")
    assert status == 200
    assert body["auth_url"] == "https://evil.com/callback"
    assert await _count_audit_incidents(db) == 0


@pytest.mark.asyncio
async def test_toggle_plugin_preserves_external_auth_guard(tmp_path, db: aiosqlite.Connection):
    """Vérifie que le cycle complet de désactivation/réactivation (toggle)
    d'un plugin via PluginEngine préserve bien le garde-fou external_auth_domains."""
    from master.core.plugin_engine import PluginEngine
    from master.core.route_registrar import RouteRegistrar

    # 1. Préparer un plugin dans un répertoire temporaire
    p_dir = tmp_path / "plugins"
    p_dir.mkdir()
    plugin_dir = p_dir / "authurl"
    plugin_dir.mkdir()

    (plugin_dir / "manifest.json").write_text(
        json.dumps({
            "id": "authurl",
            "name": "AuthURL Plugin",
            "version": "1.0.0",
            "author": "Vigile",
            "trusted": True,
            "external_auth_domains": ["plex.tv"],
            "routes": [],
        })
    )
    (plugin_dir / "__init__.py").write_text(
        "from master.core.plugin_base import PluginBase, route\n"
        "class AuthPlugin(PluginBase):\n"
        "    plugin_id = 'authurl'\n"
        "    @route('/evil', method='POST', roles=['admin'])\n"
        "    async def evil_route(self) -> dict:\n"
        "        return {'auth_url': 'https://evil.com/callback'}\n"
        "    @route('/good', method='POST', roles=['admin'])\n"
        "    async def good_route(self) -> dict:\n"
        "        return {'auth_url': 'https://app.plex.tv/auth'}\n"
    )

    app = FastAPI()
    app.dependency_overrides[get_db_conn] = lambda: db
    registrar = RouteRegistrar(app)
    engine = PluginEngine(db=db, route_registrar=registrar)

    # 2. Premier chargement (scan initial)
    await engine.scan(str(p_dir))
    loaded = await engine.load_plugin("authurl", str(p_dir))
    assert loaded is True

    # Vérifie le garde-fou actif
    status, body = await _post(app, "/api/plugins/authurl/evil")
    assert status == 502
    assert "evil.com" in body.get("detail", "")

    # 3. Simulation du toggle OFF (unload)
    await engine.unload_plugin("authurl")
    assert "authurl" not in engine.loaded_plugins
    status, _ = await _post(app, "/api/plugins/authurl/evil")
    assert status == 404

    # 4. Simulation du toggle ON (load_plugin sans re-scan)
    reloaded = await engine.load_plugin("authurl", str(p_dir))
    assert reloaded is True
    assert "authurl" in engine.loaded_plugins

    # Vérifie que le garde-fou est TOUJOURS actif après le toggle
    status, body = await _post(app, "/api/plugins/authurl/evil")
    assert status == 502
    assert "evil.com" in body.get("detail", "")

    # Vérifie que le domaine autorisé passe
    status, body = await _post(app, "/api/plugins/authurl/good")
    assert status == 200
    assert body["auth_url"] == "https://app.plex.tv/auth"

    await engine.unload_plugin("authurl")