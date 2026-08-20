"""Catalogue de permissions fermé (S7) + vérificateur d'intersection au dispatch.

Contrat : docs/contracts/block-contract-v2.md §6. Le catalogue est core-owned
et fermé : un plugin ne peut demander qu'à appartenir à une entrée existante
par nom. Intersection au dispatch :
    role >= min_role  ET  p in manifest.permissions  ET  resource_contract
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# Hiérarchie des rôles partagée avec la couche API (viewer < operator < admin).
ROLE_LEVELS: Mapping[str, int] = {"viewer": 0, "operator": 1, "admin": 2}


@dataclass(frozen=True)
class PermissionSpec:
    """Une entrée du catalogue fermé."""

    id: str                 # identifiant de permission du catalogue, ex. "restart_service"
    resource_contract: str  # domaine propriétaire (plugin id)
    mutation: bool          # True => doit passer par ActionProposal
    min_role: str           # "viewer" | "operator" | "admin"


# Catalogue FERMÉ — core-owned. Les plugins ne peuvent demander qu'une
# appartenance par nom. Couvre les domaines des commandes built-in actuelles
# (scan du registre : metrics, systemd, docker, plex) :
#   - lectures (nœud, services, conteneurs, logs, disque, plex) : viewer
#   - mutations (restart service/conteneur, auth plex) : operator
PERMISSION_CATALOG: Mapping[str, PermissionSpec] = {
    "node_read": PermissionSpec(
        id="node_read", resource_contract="metrics", mutation=False, min_role="viewer"
    ),
    "service_read": PermissionSpec(
        id="service_read", resource_contract="systemd", mutation=False, min_role="viewer"
    ),
    "restart_service": PermissionSpec(
        id="restart_service", resource_contract="systemd", mutation=True, min_role="operator"
    ),
    "container_read": PermissionSpec(
        id="container_read", resource_contract="docker", mutation=False, min_role="viewer"
    ),
    "restart_container": PermissionSpec(
        id="restart_container", resource_contract="docker", mutation=True, min_role="operator"
    ),
    "read_logs": PermissionSpec(
        id="read_logs", resource_contract="systemd", mutation=False, min_role="viewer"
    ),
    "disk_scan": PermissionSpec(
        id="disk_scan", resource_contract="disk_analysis", mutation=False, min_role="viewer"
    ),
    "plex_read": PermissionSpec(
        id="plex_read", resource_contract="plex", mutation=False, min_role="viewer"
    ),
    "plex_auth": PermissionSpec(
        id="plex_auth", resource_contract="plex", mutation=True, min_role="operator"
    ),
}


def role_level(role: str) -> int:
    """Mappe un rôle vers son niveau ; les rôles inconnus valent 0 (plancher viewer)."""
    return ROLE_LEVELS.get(role, 0)


def manifest_permission_names(manifest_permissions: Any) -> frozenset[str]:
    """Extrait les noms de permissions d'une liste ``PluginManifestV2.permissions``.

    Accepte ``None``, ``list[PermissionV2]`` ou ``list[dict]`` (forme brute
    JSON) — ne lève jamais. ``None``/vide => ``frozenset()`` (modèle plat).
    """
    if manifest_permissions is None:
        return frozenset()
    if not isinstance(manifest_permissions, (list, tuple, set, frozenset)):
        return frozenset()
    names: set[str] = set()
    for item in manifest_permissions:
        if isinstance(item, str):
            names.add(item)
            continue
        name = getattr(item, "name", None)
        if name is None and isinstance(item, Mapping):
            name = item.get("name")
        if isinstance(name, str) and name:
            names.add(name)
    return frozenset(names)


def check_permission_intersection(
    *,
    role: str,
    command_entry: Any,
    manifest_permissions: Any,
) -> tuple[bool, str]:
    """Retourne ``(allowed, reason)`` — intersection selon le contrat §6.

    - Plugin sans manifeste V2 / sans permissions déclarées :
      MODÈLE PLAT -> autorisé (les plugins V1 hérités doivent continuer à
      fonctionner).
    - Sinon : autorisé s'il EXISTE une entrée du catalogue dont l'id est
      déclaré dans ``manifest.permissions`` ET dont ``resource_contract``
      correspond au contrat de la commande ET dont le flag ``mutation``
      correspond à celui de la commande ET dont ``min_role`` est satisfait
      par le rôle. Sinon refusé (fail-closed pour les plugins V2).

    ``reason`` est une courte chaîne française décrivant la dimension en échec
    ("permission non déclarée", "rôle insuffisant (min: X)", ...), ou "" si
    autorisé.
    """
    if manifest_permissions is None:
        return (True, "")  # modèle plat — plugin V1 hérité (champ non présent)

    names = manifest_permission_names(manifest_permissions)
    if not names:
        return (False, "aucune permission déclarée (liste vide)")

    contract = str(getattr(command_entry, "resource_contract", ""))
    mutation = bool(getattr(command_entry, "mutation", False))
    shape_min: str | None = None

    for name in names:
        entry = PERMISSION_CATALOG.get(name)
        if entry is None:
            continue
        if entry.resource_contract != contract or entry.mutation != mutation:
            continue
        if shape_min is None or role_level(entry.min_role) < role_level(shape_min):
            shape_min = entry.min_role
        if role_level(role) >= role_level(entry.min_role):
            return (True, "")

    if shape_min is not None:
        return (False, f"rôle insuffisant (min: {shape_min})")
    return (False, "permission non déclarée")