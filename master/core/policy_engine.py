from __future__ import annotations

"""
Vigile — Master Policy Engine

Manages plugin grants, compiles node-level policy bundles,
signs them using Ed25519 (JCS RFC 8785), and manages policy delivery.
"""

import json
import logging
import time
import uuid
from typing import Any

import aiosqlite

from master.core.security_manager import SecurityManager

logger = logging.getLogger(__name__)

DEFAULT_POLICY_TTL = 30 * 24 * 3600  # 30 days


class PolicyEngine:
    """
    Compiles active plugin_grants into signed Ed25519 policy bundles per worker.
    """

    def __init__(self, security_manager: SecurityManager) -> None:
        self._security = security_manager

    async def get_active_grants(self, db: aiosqlite.Connection, node_id: str) -> list[dict[str, Any]]:
        """Retrieve all currently active (non-revoked) grants for a node."""
        async with db.execute(
            """
            SELECT id, plugin_id, node_id, action, target_kind, target_id, limits_json, granted_by, granted_at
            FROM plugin_grants
            WHERE node_id = ? AND revoked_at IS NULL
            """,
            (node_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                limits = json.loads(r["limits_json"]) if r["limits_json"] else {}
                results.append({
                    "grant_id": r["id"],
                    "plugin_id": r["plugin_id"],
                    "node_id": r["node_id"],
                    "action": r["action"],
                    "target_kind": r["target_kind"],
                    "target_id": r["target_id"],
                    "limits": limits,
                    "granted_by": r["granted_by"],
                    "granted_at": r["granted_at"],
                })
            return results

    async def compile_policy_bundle(
        self,
        db: aiosqlite.Connection,
        node_id: str,
        issued_by: str = "system",
        ttl_seconds: int = DEFAULT_POLICY_TTL,
    ) -> dict[str, Any]:
        """
        Compiles active grants for a node into a single signed PolicyBundle payload.
        """
        grants = await self.get_active_grants(db, node_id)

        # Retrieve current version to increment policy_version
        async with db.execute(
            """
            SELECT policy_epoch, policy_version
            FROM policies
            WHERE node_id = ?
            ORDER BY policy_epoch DESC, policy_version DESC
            LIMIT 1
            """,
            (node_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                policy_epoch = row["policy_epoch"]
                policy_version = row["policy_version"] + 1
            else:
                policy_epoch = 1
                policy_version = 1

        now = time.time()
        expires_at = now + ttl_seconds
        policy_id = str(uuid.uuid4())

        rules = []
        for g in grants:
            rules.append({
                "rule_id": g["grant_id"],
                "plugin_id": g["plugin_id"],
                "action": g["action"],
                "target": {
                    "kind": g["target_kind"],
                    "id": g["target_id"],
                },
                "limits": g["limits"],
                "requires_human_approval": True,
            })

        # Add Bootstrap read-only rules if no grants exist yet
        if not rules:
            bootstrap_rules = [
                {"rule_id": "bootstrap-1", "plugin_id": "core", "action": "LIST_SERVICES", "target": {"kind": "systemd_service", "id": "*"}, "requires_human_approval": False},
                {"rule_id": "bootstrap-2", "plugin_id": "core", "action": "LIST_CONTAINERS", "target": {"kind": "docker_container", "id": "*"}, "requires_human_approval": False},
                {"rule_id": "bootstrap-3", "plugin_id": "core", "action": "LIST_LOG_SOURCES", "target": {"kind": "log_source", "id": "*"}, "requires_human_approval": False},
            ]
            rules.extend(bootstrap_rules)

        bundle_payload = {
            "policy_id": policy_id,
            "node_id": node_id,
            "master_key_id": self._security.master_public_key_b64[:16],
            "policy_epoch": policy_epoch,
            "policy_version": policy_version,
            "issued_at": now,
            "expires_at": expires_at,
            "rules": rules,
        }

        signature = self._security.sign_policy_bundle(bundle_payload)
        bundle_payload["signature"] = signature

        bundle_json = json.dumps(bundle_payload, sort_keys=True)
        bundle_hash = self._security.join_token_hash(bundle_json)

        # Persist policy bundle to DB
        await db.execute(
            """
            INSERT INTO policies (id, node_id, master_key_id, policy_epoch, policy_version, bundle_hash, bundle_json, signature, status, issued_by, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
            """,
            (
                policy_id,
                node_id,
                bundle_payload["master_key_id"],
                policy_epoch,
                policy_version,
                bundle_hash,
                bundle_json,
                signature,
                issued_by,
                expires_at,
                now,
            ),
        )
        await db.commit()

        logger.info(f"Compiled and signed PolicyBundle {policy_id} (version {policy_version}) for node {node_id}")
        return bundle_payload
