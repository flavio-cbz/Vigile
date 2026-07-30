from __future__ import annotations

"""
Auto-update management for Vigile Master Node.

This module contains the auto-update worker task and related functions.
"""

import asyncio
import logging
from typing import Any

from master.config import settings
from master.core.node_manager import node_manager

logger = logging.getLogger(__name__)


async def auto_update_workers_task(db, nm, settings_obj) -> None:
    """
    Background loop that checks for worker updates and dispatches them if AUTO_UPDATE_WORKERS is enabled.
    """
    logger.info("Auto-update workers task started.")
    # Wait a bit on startup to let things settle down
    await asyncio.sleep(30.0)

    while True:
        try:
            if settings_obj.offline_mode:
                logger.info("Offline mode: skipping auto-update check.")
                await asyncio.sleep(3600.0)
                continue

            if settings_obj.auto_update_workers:
                await _process_worker_updates(db, nm, settings_obj)
        except Exception as exc:
            logger.exception("Error in auto-update workers task: %s", exc)

        # Check every 1 hour (3600 seconds)
        await asyncio.sleep(3600.0)


async def _process_worker_updates(db, nm, settings_obj) -> None:
    """
    Process worker updates for all connected nodes.
    """
    logger.info("Auto-update: Checking connected nodes for updates...")
    from master.api.worker_binary import _fetch_manifest

    manifest = await _fetch_manifest(settings_obj)

    if manifest:
        latest_version = manifest.get("version")
        if latest_version:
            logger.info(
                "Auto-update: Latest available worker version: %s", latest_version
            )

            # Get all registered nodes (exclude revoked)
            async with db.execute(
                "SELECT id, name, version, state FROM nodes WHERE state != 'REVOKED'"
            ) as cursor:
                nodes = await cursor.fetchall()

            for node in nodes:
                await _update_node_if_needed(node, nm, latest_version, settings_obj)


async def _update_node_if_needed(node, nm, latest_version, settings_obj, db) -> None:
    """
    Update a single node if its version is outdated.
    """
    node_id = node["id"]
    # Check if node is online/connected
    if await nm.is_connected(node_id):
        current_version = node["version"]
        # If version is empty (legacy) or doesn't match latest_version, trigger update
        if not current_version or current_version != latest_version:
            logger.info(
                "Auto-update: Node %s (%s) has version %s (latest is %s). Dispatching update...",
                node_id,
                node["name"],
                current_version,
                latest_version,
            )
            await _dispatch_node_update(node_id, nm, settings_obj, db)


async def _dispatch_node_update(node_id, nm, settings_obj, db) -> None:
    """
    Dispatch an update intent to a specific node.
    """
    from master.core.enums import WorkerAction
    from master.core.proposal_dispatcher import ApprovedProposalDispatcher

    dispatcher = ApprovedProposalDispatcher(nm)
    try:
        await dispatcher.dispatch_admin_action(
            node_id,
            WorkerAction.UPDATE_WORKER,
            {},
            "system",
            db,
            intent_timeout=settings_obj.DEFAULT_TIMEOUT,
            reasoning="Auto-update: worker binary version mismatch",
        )
        logger.info(
            "Auto-update: Node %s successfully updated and restarted.",
            node_id,
        )
    except Exception as e:
        logger.error(
            "Auto-update: Node %s update failed: %s", node_id, e
        )
