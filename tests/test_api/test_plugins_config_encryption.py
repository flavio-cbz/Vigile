from __future__ import annotations

"""
Tests du chiffrement au repos de la config plugin (J4-T27-BE-1).

Couvre :
  - config_encryption : round-trip chiffrement/déchiffrement, IV aléatoire,
    échec-faible sur valeur corrompue / clé erronée, passage legacy en clair,
    marqueur `secret: true` (formes wrapper + flat) ;
  - migration in-place du token Plex legacy (plan §5.1 option A) : premier
    chargement chiffre + audit, second chargement no-op ;
  - `_get_plex_config` / `_save_plex_config` : token utilisable côté serveur,
    stockage toujours chiffré (`v1:...`) ;
  - API admin : POST /config chiffre les champs secrets, GET /plugins masque
    (`••••••••`), le masque renvoyé en POST conserve la valeur stockée.
"""

import json

import aiosqlite
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import status
from httpx import AsyncClient

from master.api import deps
from master.config import settings
from master.core.config_encryption import (
    SECRET_MASK,
    SecretDecryptionError,
    decrypt_secret,
    derive_config_key,
    encrypt_secret,
    is_secret_field,
    mask_secret_fields,
)
from master.core.plugin_manager import plugin_manager
from master.core.security_manager import SecurityManager, get_security_instance
from master.main import app
from master.plugins.plex import _get_plex_config, _save_plex_config


# ---------------------------------------------------------------------------
# Fixtures (même harnais que test_plugins_api.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_headers(security: SecurityManager):
    def _make(role: str = "admin"):
        token = security.create_access_token("test-user", "test_user", role)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
async def client(db):
    from httpx import ASGITransport, AsyncClient

    app.dependency_overrides[deps.get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)


@pytest.fixture(autouse=True)
async def setup_temp_plugins_dir(tmp_path):
    """Crée un plugin package déclarant un champ secret (`api_key`) + un champ
    non secret (`host`) dans son manifest — le harnais des tests API."""
    import sys

    saved_modules = dict(sys.modules)
    old_plugins_dir = settings.plugins_dir
    temp_dir = tmp_path / "plugins"
    temp_dir.mkdir()
    settings.plugins_dir = str(temp_dir)
    try:
        import master.api.admin

        master.api.admin.settings.plugins_dir = str(temp_dir)
    except Exception:
        pass

    pkg_dir = temp_dir / "secretbox"
    pkg_dir.mkdir()
    (pkg_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": "secretbox",
                "name": "Secret Plugin",
                "version": "1.0.0",
                "trusted": True,
                "config_schema": {
                    "name": "Secret Plugin",
                    "category": "Test",
                    "schema": {
                        "api_key": {
                            "type": "string",
                            "title": "API Key",
                            "default": "",
                            "secret": True,
                        },
                        "host": {"type": "string", "title": "Host", "default": ""},
                    },
                },
            }
        )
    )
    (pkg_dir / "__init__.py").write_text(
        "from master.core.plugin_base import PluginBase\n"
        "class SecretPlugin(PluginBase):\n"
        "    plugin_id = 'secretbox'\n"
    )

    yield temp_dir

    settings.plugins_dir = old_plugins_dir
    try:
        import master.api.admin

        master.api.admin.settings.plugins_dir = old_plugins_dir
    except Exception:
        pass
    for k in list(sys.modules.keys()):
        if k not in saved_modules:
            del sys.modules[k]
    sys.modules.update(saved_modules)


def _test_key() -> bytes:
    return derive_config_key(Ed25519PrivateKey.generate())


# ---------------------------------------------------------------------------
# config_encryption — unités pures
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_roundtrip():
    key = _test_key()
    stored = encrypt_secret("mon-secret-plex", key)
    assert stored.startswith("v1:")
    assert decrypt_secret(stored, key) == "mon-secret-plex"


def test_encrypt_uses_random_iv_per_call():
    key = _test_key()
    a = encrypt_secret("même secret", key)
    b = encrypt_secret("même secret", key)
    assert a != b  # IV aléatoire : deux chiffrements ne sont jamais identiques


def test_decrypt_tampered_ciphertext_fails_closed():
    key = _test_key()
    stored = encrypt_secret("secret", key)
    prefix, b64_iv, b64_ct = stored.split(":")
    flipped = ("0" if b64_ct[0] != "0" else "1") + b64_ct[1:]
    tampered = f"{prefix}:{b64_iv}:{flipped}"
    with pytest.raises(SecretDecryptionError):
        decrypt_secret(tampered, key)


def test_decrypt_wrong_key_fails_closed():
    stored = encrypt_secret("secret", _test_key())
    with pytest.raises(SecretDecryptionError):
        decrypt_secret(stored, _test_key())


def test_decrypt_legacy_plaintext_passthrough():
    key = _test_key()
    assert decrypt_secret("legacy-token", key) == "legacy-token"
    assert decrypt_secret("", key) == ""


def test_decrypt_malformed_v1_raises():
    key = _test_key()
    with pytest.raises(SecretDecryptionError):
        decrypt_secret("v1:pas-un-b64", key)
    with pytest.raises(SecretDecryptionError):
        decrypt_secret("v1:abc", key)


def test_is_secret_field_wrapper_and_flat_shapes():
    wrapper = {
        "config_schema": {
            "schema": {
                "api_key": {"type": "string", "secret": True},
                "host": {"type": "string"},
            }
        }
    }
    assert is_secret_field(wrapper, "api_key") is True
    assert is_secret_field(wrapper, "host") is False

    flat = {"config_schema": {"api_key": {"secret": True}}}
    assert is_secret_field(flat, "api_key") is True

    assert is_secret_field(None, "api_key") is False
    assert is_secret_field({}, "api_key") is False
    assert is_secret_field({"config_schema": "nope"}, "api_key") is False


def test_mask_secret_fields_replaces_only_secrets():
    manifest = {
        "config_schema": {
            "schema": {
                "api_key": {"secret": True},
                "host": {"type": "string"},
            }
        }
    }
    masked = mask_secret_fields({"api_key": "v1:xyz", "host": "example.com"}, manifest)
    assert masked["api_key"] == SECRET_MASK
    assert masked["host"] == "example.com"
    # L'entrée d'origine n'est pas mutée
    assert mask_secret_fields({"api_key": "v1:xyz"}, None) == {"api_key": "v1:xyz"}


# ---------------------------------------------------------------------------
# Migration in-place du token Plex (plan §5.1 option A)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plex_config_migration_encrypts_legacy_token(db: aiosqlite.Connection):
    await db.execute(
        "INSERT INTO plugins (id, enabled, config_json) VALUES ('plex', 1, ?)",
        (json.dumps({"plex_token": "legacy-token-abc", "plex_server_url": "http://x:32400"}),),
    )
    await db.commit()

    # Premier chargement : token utilisable côté serveur…
    config = await _get_plex_config(db)
    assert config["plex_token"] == "legacy-token-abc"
    assert config["plex_server_url"] == "http://x:32400"

    # …mais stockage chiffré en place.
    async with db.execute("SELECT config_json FROM plugins WHERE id = 'plex'") as cur:
        row = await cur.fetchone()
    stored = json.loads(row[0])
    assert stored["plex_token"].startswith("v1:")
    assert stored["plex_server_url"] == "http://x:32400"

    # Entrée d'audit appendée (même action que le chemin d'écriture admin).
    async with db.execute(
        "SELECT action, details_json FROM audit_log WHERE action = 'CONFIGURE_PLUGIN'"
    ) as cur:
        rows = await cur.fetchall()
    assert len(rows) == 1
    details = json.loads(rows[0][1])
    assert details["plugin_id"] == "plex"
    assert details["secret_migrated"] == "plex_token"

    # Second chargement = no-op (aucune nouvelle entrée d'audit).
    config2 = await _get_plex_config(db)
    assert config2["plex_token"] == "legacy-token-abc"
    async with db.execute(
        "SELECT COUNT(*) FROM audit_log WHERE action = 'CONFIGURE_PLUGIN'"
    ) as cur:
        count = (await cur.fetchone())[0]
    assert count == 1


@pytest.mark.asyncio
async def test_plex_get_config_returns_usable_token_after_migration(db: aiosqlite.Connection):
    await db.execute(
        "INSERT INTO plugins (id, enabled, config_json) VALUES ('plex', 1, ?)",
        (json.dumps({"plex_token": "plain-token"}),),
    )
    await db.commit()

    config = await _get_plex_config(db)
    assert config["plex_token"] == "plain-token"

    # Le token chiffré se déchiffre bien avec la clé dérivée du Master.
    async with db.execute("SELECT config_json FROM plugins WHERE id = 'plex'") as cur:
        row = await cur.fetchone()
    stored = json.loads(row[0])
    key = derive_config_key(get_security_instance().master_private_key)
    assert decrypt_secret(stored["plex_token"], key) == "plain-token"


@pytest.mark.asyncio
async def test_plex_save_config_encrypts_token_on_write(db: aiosqlite.Connection):
    await db.execute(
        "INSERT INTO plugins (id, enabled, config_json) VALUES ('plex', 1, ?)",
        (json.dumps({"plex_token": "old-token"}),),
    )
    await db.commit()

    saved = await _save_plex_config(db, {"plex_token": "new-token"})
    # Valeur retournée utilisable côté serveur…
    assert saved["plex_token"] == "new-token"

    # …stockage toujours chiffré.
    async with db.execute("SELECT config_json FROM plugins WHERE id = 'plex'") as cur:
        row = await cur.fetchone()
    stored = json.loads(row[0])
    assert stored["plex_token"].startswith("v1:")
    key = derive_config_key(get_security_instance().master_private_key)
    assert decrypt_secret(stored["plex_token"], key) == "new-token"


@pytest.mark.asyncio
async def test_plex_get_config_corrupted_token_fails_closed(db: aiosqlite.Connection):
    await db.execute(
        "INSERT INTO plugins (id, enabled, config_json) VALUES ('plex', 1, ?)",
        (json.dumps({"plex_token": "v1:corrompu", "plex_server_url": "http://x:32400"}),),
    )
    await db.commit()

    config = await _get_plex_config(db)
    # Échec-faible : token ignoré, reste de la config utilisable.
    assert config["plex_token"] == ""
    assert config["plex_server_url"] == "http://x:32400"


# ---------------------------------------------------------------------------
# API admin — chiffrement à l'écriture, masquage à la lecture
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_post_encrypts_secret_field(
    client: AsyncClient, auth_headers, db: aiosqlite.Connection
):
    res = await client.post(
        "/api/admin/plugins/secretbox/config",
        headers=auth_headers("admin"),
        json={"api_key": "super-secret", "host": "example.com"},
    )
    assert res.status_code == status.HTTP_200_OK

    async with db.execute("SELECT config_json FROM plugins WHERE id = 'secretbox'") as cur:
        row = await cur.fetchone()
    stored = json.loads(row[0])
    assert stored["api_key"].startswith("v1:")  # champ secret chiffré
    assert stored["host"] == "example.com"  # champ non secret inchangé


@pytest.mark.asyncio
async def test_config_get_masks_secret_field(
    client: AsyncClient, auth_headers, db: aiosqlite.Connection
):
    await db.execute(
        "INSERT INTO plugins (id, enabled, config_json) VALUES ('secretbox', 1, ?)",
        (json.dumps({"api_key": "v1:whatever", "host": "example.com"}),),
    )
    await db.commit()

    res = await client.get("/api/admin/plugins", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK
    data = res.json()["plugins"]
    plugin = next(p for p in data if p["id"] == "secretbox")
    assert plugin["config"]["api_key"] == SECRET_MASK  # jamais le clair ni le chiffré
    assert plugin["config"]["host"] == "example.com"


@pytest.mark.asyncio
async def test_config_post_mask_keeps_stored_secret(
    client: AsyncClient, auth_headers, db: aiosqlite.Connection
):
    await db.execute(
        "INSERT INTO plugins (id, enabled, config_json) VALUES ('secretbox', 1, ?)",
        (json.dumps({"api_key": "v1:abc", "host": "old"}),),
    )
    await db.commit()

    res = await client.post(
        "/api/admin/plugins/secretbox/config",
        headers=auth_headers("admin"),
        json={"api_key": SECRET_MASK, "host": "new"},
    )
    assert res.status_code == status.HTTP_200_OK

    async with db.execute("SELECT config_json FROM plugins WHERE id = 'secretbox'") as cur:
        row = await cur.fetchone()
    stored = json.loads(row[0])
    assert stored["api_key"] == "v1:abc"  # masque → valeur stockée conservée
    assert stored["host"] == "new"


@pytest.mark.asyncio
async def test_config_post_non_secret_plugin_unchanged(
    client: AsyncClient, auth_headers, db: aiosqlite.Connection
):
    """Un plugin sans manifest (ou sans champ secret) garde le chemin historique."""
    from pathlib import Path

    (Path(settings.plugins_dir) / "plaincfg.py").write_text(
        "def register(pm):\n"
        "    pm.register('get_supported_actions', lambda: [], plugin_name='plaincfg')\n"
    )
    res = await client.post(
        "/api/admin/plugins/plaincfg/config",
        headers=auth_headers("admin"),
        json={"api_key": "plain-value"},
    )
    assert res.status_code == status.HTTP_200_OK

    async with db.execute("SELECT config_json FROM plugins WHERE id = 'plaincfg'") as cur:
        row = await cur.fetchone()
    stored = json.loads(row[0])
    assert stored["api_key"] == "plain-value"  # aucun chiffrement appliqué