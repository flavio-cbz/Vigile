from __future__ import annotations

"""
S7 — Catalogue de permissions fermé + vérificateur d'intersection (T18, sous-tâche A).

Contrat : docs/contracts/block-contract-v2.md §6. Le catalogue est core-owned
et fermé ; l'intersection s'applique au dispatch :
    role >= min_role  ET  p in manifest.permissions  ET  resource_contract
"""

from dataclasses import dataclass

import pytest

import master.core.permissions as permissions
from master.core.permissions import (
    PERMISSION_CATALOG,
    PermissionSpec,
    check_permission_intersection,
    manifest_permission_names,
    role_level,
)
from master.core.plugin_manifest import PermissionV2


@dataclass(frozen=True)
class FakeCommand:
    """Doublure duck-typed de ``CommandEntry`` — aucun lien avec le registre réel."""

    name: str
    resource_contract: str
    mutation: bool = False


def _cmd(contract: str, mutation: bool = False, name: str = "fake.cmd") -> FakeCommand:
    return FakeCommand(name=name, resource_contract=contract, mutation=mutation)


def test_catalog_closed():
    """Un id de permission absent du catalogue n'est jamais accordable,
    même si le manifeste le déclare."""
    assert "nonexistent_perm" not in PERMISSION_CATALOG
    allowed, reason = check_permission_intersection(
        role="admin",
        command_entry=_cmd("systemd", mutation=True),
        manifest_permissions=[{"name": "nonexistent_perm"}],
    )
    assert allowed is False
    assert reason == "permission non déclarée"


def test_role_matrix(monkeypatch):
    """Matrice rôle × min_role : viewer refusé pour operator/admin,
    operator autorisé pour operator mais refusé pour admin, admin tout passe."""
    catalog = {
        "read_viewer": PermissionSpec(
            id="read_viewer", resource_contract="test", mutation=False, min_role="viewer"
        ),
        "mut_operator": PermissionSpec(
            id="mut_operator", resource_contract="test", mutation=True, min_role="operator"
        ),
        "mut_admin": PermissionSpec(
            id="mut_admin", resource_contract="test", mutation=True, min_role="admin"
        ),
    }
    monkeypatch.setattr(permissions, "PERMISSION_CATALOG", catalog)

    # viewer : lecture OK, mutations refusées
    assert check_permission_intersection(
        role="viewer",
        command_entry=_cmd("test"),
        manifest_permissions=[{"name": "read_viewer"}],
    ) == (True, "")
    allowed, reason = check_permission_intersection(
        role="viewer",
        command_entry=_cmd("test", mutation=True),
        manifest_permissions=[{"name": "mut_operator"}],
    )
    assert (allowed, reason) == (False, "rôle insuffisant (min: operator)")
    allowed, reason = check_permission_intersection(
        role="viewer",
        command_entry=_cmd("test", mutation=True),
        manifest_permissions=[{"name": "mut_admin"}],
    )
    assert (allowed, reason) == (False, "rôle insuffisant (min: admin)")

    # operator : operator OK, admin refusé
    assert check_permission_intersection(
        role="operator",
        command_entry=_cmd("test", mutation=True),
        manifest_permissions=[{"name": "mut_operator"}],
    ) == (True, "")
    allowed, reason = check_permission_intersection(
        role="operator",
        command_entry=_cmd("test", mutation=True),
        manifest_permissions=[{"name": "mut_admin"}],
    )
    assert (allowed, reason) == (False, "rôle insuffisant (min: admin)")

    # admin : tout passe
    assert check_permission_intersection(
        role="admin",
        command_entry=_cmd("test", mutation=True),
        manifest_permissions=[{"name": "mut_admin"}],
    ) == (True, "")
    assert check_permission_intersection(
        role="admin",
        command_entry=_cmd("test"),
        manifest_permissions=[{"name": "read_viewer"}],
    ) == (True, "")


def test_mutation_flag_mismatch():
    """mutation=True avec une entrée read-only du catalogue => refusé ;
    mutation=False avec une entrée mutation => refusé (seule la forme exacte
    accorde)."""
    allowed, reason = check_permission_intersection(
        role="operator",
        command_entry=_cmd("systemd", mutation=True),
        manifest_permissions=[{"name": "service_read"}],
    )
    assert (allowed, reason) == (False, "permission non déclarée")

    allowed, reason = check_permission_intersection(
        role="operator",
        command_entry=_cmd("systemd", mutation=False),
        manifest_permissions=[{"name": "restart_service"}],
    )
    assert (allowed, reason) == (False, "permission non déclarée")


def test_resource_contract_mismatch():
    """Le manifeste déclare restart_service mais le contrat de la commande est
    un autre domaine => refusé."""
    allowed, reason = check_permission_intersection(
        role="admin",
        command_entry=_cmd("docker", mutation=True),
        manifest_permissions=[{"name": "restart_service"}],
    )
    assert (allowed, reason) == (False, "permission non déclarée")


def test_flat_model_legacy():
    """manifest_permissions=None => modèle plat, autorisé (plugin V1)."""
    assert check_permission_intersection(
        role="viewer",
        command_entry=_cmd("systemd", mutation=True),
        manifest_permissions=None,
    ) == (True, "")
    # liste vide V2 = aucune permission déclarée => fail-closed (C1)
    allowed, reason = check_permission_intersection(
        role="viewer",
        command_entry=_cmd("systemd", mutation=True),
        manifest_permissions=[],
    )
    assert allowed is False
    assert "aucune permission déclarée" in reason


def test_manifest_permissions_accepts_dicts():
    """La forme list[dict] (JSON brut) fonctionne comme la forme PermissionV2."""
    names = manifest_permission_names(
        [{"name": "restart_service", "description": "x"}, PermissionV2(name="plex_read")]
    )
    assert names == frozenset({"restart_service", "plex_read"})

    allowed, reason = check_permission_intersection(
        role="operator",
        command_entry=_cmd("systemd", mutation=True),
        manifest_permissions=[{"name": "restart_service"}],
    )
    assert (allowed, reason) == (True, "")


def test_manifest_permission_names_never_raises():
    """Entrées invalides (None, scalaires, objets sans name) => jamais d'exception."""
    assert manifest_permission_names(None) == frozenset()
    assert manifest_permission_names("restart_service") == frozenset()
    assert manifest_permission_names(42) == frozenset()
    assert manifest_permission_names([{"description": "sans name"}]) == frozenset()
    assert manifest_permission_names([None, 42, "restart_service"]) == frozenset(
        {"restart_service"}
    )


def test_role_level_unknown_floor():
    """Rôles inconnus => plancher viewer (0)."""
    assert role_level("viewer") == 0
    assert role_level("operator") == 1
    assert role_level("admin") == 2
    assert role_level("superuser") == 0


def test_happy_path_plex_read():
    """Lecture plex : viewer + plex_read + contrat plex + read => autorisé."""
    assert check_permission_intersection(
        role="viewer",
        command_entry=_cmd("plex", mutation=False),
        manifest_permissions=[{"name": "plex_read"}],
    ) == (True, "")