from __future__ import annotations

"""
Auto-update management for Vigile Master Node.

This module contains the background loop and orchestration logic for automatically
updating connected Vigile workers to the latest validated release.

Features:
  - Semver parsing & comparison (anti-loop guard).
  - Canary deployment: updates 1 node first and verifies health before fleet rollout.
  - Fail-closed: aborts rollout if canary fails or times out.
  - Audit logging via hash-chain (AuditAction.AUTO_UPDATE_WORKER).
  - Robust parameter injection (os, arch, binary_url, sha256_url).
"""

import asyncio
import logging
import time
from typing import Any

from master.api.worker_binary import ARCH_MAP, _fetch_manifest
from master.core.audit import AuditAction, log_action
from master.core.enums import WorkerAction
from master.core.proposal_dispatcher import ApprovedProposalDispatcher

logger = logging.getLogger(__name__)


def parse_semver(v: str | None) -> tuple[int, ...]:
    """Parse version string like 'v1.1.0' or '1.2.3' into tuple (1, 2, 3)."""
    if not v:
        return (0, 0, 0)
    clean = str(v).strip().lstrip("v").split("-")[0]
    parts = []
    for part in clean.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer_version(new_ver: str | None, current_ver: str | None) -> bool:
    """Return True if new_ver is strictly greater than current_ver."""
    if not new_ver:
        return False
    return parse_semver(new_ver) > parse_semver(current_ver)


async def auto_update_workers_task(db: Any, nm: Any, settings_obj: Any) -> None:
    """
    Background loop that checks for worker updates and dispatches them if AUTO_UPDATE_WORKERS is enabled.
    """
    logger.info("Auto-update workers task started.")
    # Wait for startup and heartbeats to settle
    await asyncio.sleep(45.0)

    while True:
        try:
            if getattr(settings_obj, "auto_update_workers", False):
                await _process_worker_updates(db, nm, settings_obj)
            else:
                logger.debug("Auto-update workers is disabled in settings.")
        except Exception as exc:
            logger.exception("Error in auto-update workers task: %s", exc)

        interval = float(getattr(settings_obj, "auto_update_interval_seconds", 3600))
        await asyncio.sleep(interval)


async def _process_worker_updates(db: Any, nm: Any, settings_obj: Any) -> None:
    """
    Process worker updates for all connected nodes using canary rollout strategy.
    """
    logger.info("Auto-update: Checking connected nodes for updates...")

    try:
        manifest = await _fetch_manifest(settings_obj)
    except Exception as exc:
        logger.warning("Auto-update: Manifest unavailable, skipping update cycle: %s", exc)
        return

    if not manifest:
        return

    latest_version = manifest.get("version")
    if not latest_version:
        logger.debug("Auto-update: No version found in manifest.")
        return

    logger.info("Auto-update: Latest available worker release: %s", latest_version)

    # Get all registered active nodes
    async with db.execute(
        "SELECT id, name, version, worker_version, state, os, arch FROM nodes WHERE state != 'REVOKED'"
    ) as cursor:
        rows = await cursor.fetchall()

    outdated_nodes: list[dict[str, Any]] = []
    for row in rows:
        node = dict(row)
        node_id = node["id"]
        if not await nm.is_connected(node_id):
            continue

        current_ver = node.get("worker_version") or node.get("version") or ""
        if is_newer_version(latest_version, current_ver):
            outdated_nodes.append(node)

    if not outdated_nodes:
        logger.info("Auto-update: All connected nodes are up-to-date (%s).", latest_version)
        return

    logger.info(
        "Auto-update: %d node(s) require update to %s: %s",
        len(outdated_nodes),
        latest_version,
        [n.get("name") or n.get("id") for n in outdated_nodes],
    )

    use_canary = getattr(settings_obj, "auto_update_canary", True) and len(outdated_nodes) > 1

    if use_canary:
        canary_node = outdated_nodes[0]
        remaining_nodes = outdated_nodes[1:]

        logger.info(
            "Auto-update: Starting canary rollout on node %s (%s)...",
            canary_node["id"],
            canary_node["name"],
        )
        dispatched = await _dispatch_node_update(canary_node, nm, settings_obj, db)
        if not dispatched:
            logger.error("Auto-update: Failed to dispatch update to canary node. Aborting fleet rollout.")
            return

        # Wait up to 120s for canary to reconnect with the new version
        canary_ok = await _wait_for_node_update(canary_node["id"], nm, db, latest_version, timeout=120.0)
        if not canary_ok:
            logger.error(
                "Auto-update: Canary node %s failed to report updated version %s within timeout! Aborting fleet rollout.",
                canary_node["id"],
                latest_version,
            )
            return

        logger.info(
            "Auto-update: Canary node %s successfully updated to %s. Proceeding with remaining %d node(s).",
            canary_node["id"],
            latest_version,
            len(remaining_nodes),
        )

        for node in remaining_nodes:
            await _dispatch_node_update(node, nm, settings_obj, db)
            await asyncio.sleep(10.0)  # Stagger rollouts
    else:
        # Single node or canary disabled
        for node in outdated_nodes:
            await _dispatch_node_update(node, nm, settings_obj, db)
            await asyncio.sleep(10.0)


async def _dispatch_node_update(node: dict[str, Any], nm: Any, settings_obj: Any, db: Any) -> bool:
    """
    Dispatch an UPDATE_WORKER intent to a specific node with resolved binary URLs.
    """
    node_id = node["id"]
    raw_os = (node.get("os") or "linux").lower()
    raw_arch = (node.get("arch") or "amd64").lower()
    node_os = raw_os
    node_arch = ARCH_MAP.get(raw_arch, raw_arch)

    update_params = {
        "os": node_os,
        "arch": node_arch,
        "binary_url": f"/api/nodes/binary/{node_os}/{node_arch}/worker",
        "sha256_url": f"/api/nodes/binary/{node_os}/{node_arch}/worker.sha256",
    }

    dispatcher = ApprovedProposalDispatcher(nm)
    timeout = getattr(settings_obj, "DEFAULT_TIMEOUT", 30.0)

    try:
        result = await dispatcher.dispatch_admin_action(
            node_id,
            WorkerAction.UPDATE_WORKER,
            update_params,
            "system",
            db,
            intent_timeout=timeout,
            reasoning="Auto-update: worker binary version mismatch",
        )
        success = result.get("success", False)
        if success:
            logger.info("Auto-update: Node %s accepted update intent and scheduled restart.", node_id)
            await log_action(
                db,
                user_id="system",
                action=AuditAction.AUTO_UPDATE_WORKER.value,
                node_id=node_id,
                details={"status": "dispatched", "params": update_params},
            )
            return True
        else:
            logger.warning("Auto-update: Node %s rejected update: %s", node_id, result.get("error"))
            return False
    except Exception as e:
        logger.error("Auto-update: Node %s update dispatch error: %s", node_id, e)
        return False


async def _wait_for_node_update(
    node_id: str,
    nm: Any,
    db: Any,
    expected_ver: str,
    timeout: float = 120.0,
) -> bool:
    """
    Wait for a node to disconnect, reconnect, and report the expected version.
    """
    start_time = time.time()
    clean_expected = str(expected_ver).strip().lstrip("v")
    await asyncio.sleep(5.0)  # Initial pause for worker process shutdown

    while time.time() - start_time < timeout:
        if await nm.is_connected(node_id):
            async with db.execute(
                "SELECT worker_version, version FROM nodes WHERE id = ?", (node_id,)
            ) as cursor:
                row = await cursor.fetchone()
            if row:
                reported = (row[0] or row[1] or "").strip().lstrip("v")
                if reported == clean_expected:
                    return True
        await asyncio.sleep(3.0)

    return False
