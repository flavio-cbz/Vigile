from __future__ import annotations

"""
Proposal expiry management for Vigile Master Node.

This module contains the proposal expiry task and related functions.
"""

import asyncio
import logging

from master.core.node_manager import node_manager
from master.core.proposal_autoexpire import auto_expire_proposals

logger = logging.getLogger(__name__)


async def proposal_expiry_task(db, nm, settings_obj) -> None:
    """
    Background loop that cancels stale PENDING proposals by TTL or
    resolved metric conditions.
    """
    logger.info("Proposal auto-expiry task started.")
    # Wait a bit on startup to let things settle and first metrics arrive
    await asyncio.sleep(60.0)

    while True:
        try:
            canceled = await auto_expire_proposals(db, nm)
            if canceled:
                logger.info("Proposal auto-expiry: canceled %d proposals.", canceled)
        except Exception as exc:
            logger.exception("Error in proposal expiry task: %s", exc)

        # Check every 60 seconds
        await asyncio.sleep(60.0)
