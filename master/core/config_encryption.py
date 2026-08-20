from __future__ import annotations

"""
Vigile — Chiffrement au repos de la configuration des plugins

Décision de conception (plan ``docs/plans/migration_master_plugins.md``,
Partie 4 §5.1) : le Master ne possède AUCUN secret symétrique réutilisable.
La seule matière secrète disponible est la paire Ed25519 de signature
(challenge-response Worker, ``load_or_generate_master_key``, fichier 0600,
O_EXCL + re-read sur course). On dérive donc une clé AES-256 via
HKDF-SHA256 sur les octets bruts de la clé privée Ed25519 — dérivation
déterministe (même clé privée ⇒ même clé de chiffrement), la clé dérivée
n'existe qu'en mémoire et jamais sur disque. La clé n'est JAMAIS lue depuis
l'environnement ni les settings : elle est toujours dérivée de l'objet
``Ed25519PrivateKey`` passé en argument (DI au bord, règle master/core).

Format des valeurs chiffrées : ``v1:<b64url iv>:<b64url ciphertext+tag>``
(AES-256-GCM, IV 12 octets aléatoire par appel). Les valeurs legacy (ne
commençant pas par ``v1:``) sont du texte clair historique :
``decrypt_secret`` les restitue telles quelles (la migration in-place s'en
charge), et toute valeur ``v1:`` corrompue lève ``SecretDecryptionError``
(échec-faible : jamais de secret partiellement lu).

Le marqueur ``secret: true`` vit dans le ``manifest.json`` du plugin (champ
``config_schema``) — jamais dans ``plugin_manifest.py`` : le schéma y est un
dict libre sans validation stricte des feuilles, le marqueur y survit
inchangé à la migration V1→V2. ``is_secret_field`` le lit pour les chemins
d'écriture (chiffrement) et de lecture (masquage).
"""

import base64
import json
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

# Masque unique renvoyé par l'API à la place de tout champ secret — jamais le
# clair, jamais le chiffré. Le frontend renvoie ce masque tel quel quand
# l'utilisateur ne modifie pas le secret : le chemin d'écriture le détecte et
# conserve la valeur stockée (même sémantique que l'API key LLM).
SECRET_MASK = "••••••••"

# Préfixe de version des valeurs chiffrées (v1 = AES-256-GCM).
_ENCRYPTED_PREFIX = "v1:"

# Sel et info HKDF stables : modifier l'un d'eux invalide TOUS les secrets
# chiffrés existants (rotation = nouvelle dérivation + ré-chiffrement).
_HKDF_SALT = b"vigile-plugin-config-encryption"
_HKDF_INFO = b"vigile:plugin-config-secrets:v1"

_IV_LENGTH = 12  # taille d'IV recommandée pour AES-GCM (96 bits)


class SecretDecryptionError(Exception):
    """Valeur chiffrée ``v1:`` illisible ou corrompue — échec-faible."""


def derive_config_key(private_key: Ed25519PrivateKey) -> bytes:
    """Dérive la clé AES-256 de chiffrement au repos depuis la clé privée Ed25519.

    HKDF-SHA256 (extract+expand, sel et info applicatifs stables) sur les 32
    octets bruts de la clé privée. La clé dérivée est déterministe pour une
    même clé privée — la rotation de la clé master entraîne une rotation de
    tous les secrets chiffrés (documenté, aucune rotation automatique).
    """
    raw = private_key.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=_HKDF_INFO,
    )
    return hkdf.derive(raw)


def encrypt_secret(plaintext: str, key: bytes) -> str:
    """Chiffre un secret en AES-256-GCM et renvoie ``v1:<b64 iv>:<b64 ct+tag>``.

    IV aléatoire de 12 octets à chaque appel : deux chiffrements du même
    clair ne produisent jamais la même valeur.
    """
    iv = os.urandom(_IV_LENGTH)
    ciphertext = AESGCM(key).encrypt(iv, plaintext.encode("utf-8"), None)
    b64_iv = base64.urlsafe_b64encode(iv).decode("ascii")
    b64_ct = base64.urlsafe_b64encode(ciphertext).decode("ascii")
    return f"{_ENCRYPTED_PREFIX}{b64_iv}:{b64_ct}"


def decrypt_secret(stored: str, key: bytes) -> str:
    """Déchiffre une valeur ``v1:`` ; les valeurs legacy (sans préfixe) sont
    restituées telles quelles (la migration in-place les chiffre au chargement).

    Toute valeur ``v1:`` corrompue (IV/ciphertext invalides, tag erroné, clé
    incorrecte) lève ``SecretDecryptionError`` — échec-faible.
    """
    if not stored.startswith(_ENCRYPTED_PREFIX):
        return stored
    try:
        _, b64_iv, b64_ct = stored.split(":", 2)
        iv = base64.urlsafe_b64decode(b64_iv + "=" * (-len(b64_iv) % 4))
        ct = base64.urlsafe_b64decode(b64_ct + "=" * (-len(b64_ct) % 4))
        plaintext = AESGCM(key).decrypt(iv, ct, None)
    except (InvalidTag, ValueError, TypeError, IndexError) as exc:
        raise SecretDecryptionError(
            "Valeur chiffrée v1: corrompue ou clé invalide"
        ) from exc
    return plaintext.decode("utf-8")


def is_secret_field(manifest: dict[str, Any] | None, field_name: str) -> bool:
    """Lit le marqueur ``secret: true`` dans le ``config_schema`` d'un manifest brut.

    Deux formes acceptées (miroir de ``ConfigFieldSpec`` dans plugin_manifest.py) :
      - wrapper : ``config_schema.schema.<field>.secret``
      - flat    : ``config_schema.<field>.secret``
    Le marqueur vit dans le manifest.json du plugin (champ ``config_schema``,
    dict libre — aucune validation stricte des feuilles) et survit à la
    migration V1→V2 (``config_schema`` transporté tel quel).
    """
    if not isinstance(manifest, dict):
        return False
    schema = manifest.get("config_schema")
    if not isinstance(schema, dict):
        return False
    nested = schema.get("schema")
    fields = nested if isinstance(nested, dict) else schema
    if not isinstance(fields, dict):
        return False
    spec = fields.get(field_name)
    return isinstance(spec, dict) and spec.get("secret") is True


def mask_secret_fields(
    config: dict[str, Any], manifest: dict[str, Any] | None
) -> dict[str, Any]:
    """Remplace tout champ marqué ``secret: true`` par ``SECRET_MASK``.

    L'API ne renvoie JAMAIS le clair ni le chiffré d'un secret : le frontend
    ne peut pas le relire, et renvoie le masque tel quel lors d'une mise à
    jour sans changement (conservé par le chemin d'écriture).
    """
    if not isinstance(config, dict):
        return {}
    if not isinstance(manifest, dict):
        return config
    masked = dict(config)
    for field in config:
        if is_secret_field(manifest, field):
            masked[field] = SECRET_MASK
    return masked


def load_manifest_json(path: str) -> dict[str, Any] | None:
    """Charge un manifest.json brut depuis un chemin fichier ou un dossier plugin.

    Retourne None si aucun manifest n'existe (plugins .py legacy — aucun champ
    secret déclaré) ou si le fichier est illisible/invalide (échec-faible côté
    lecture : on ne chiffre/masque que ce qui est déclaré).
    """
    manifest_file = path
    if os.path.isdir(path):
        manifest_file = os.path.join(path, "manifest.json")
    if not os.path.isfile(manifest_file):
        return None
    try:
        with open(manifest_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None
