from __future__ import annotations

"""Tests for the /metrics Prometheus endpoint."""

import importlib
import os
import re
import time
import uuid

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

os.environ["CORS_ORIGINS"] = "*"

import master.config
import master.main

importlib.reload(master.config)
importlib.reload(master.main)

from master.main import app


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_200(db):
    """GET /metrics returns 200 with text/plain content-type."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get("/metrics")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"].startswith("text/plain")


@pytest.mark.asyncio
async def test_metrics_contains_required_metrics(db):
    """Each of the 6+ required metric names appears in the response body."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get("/metrics")
        body = response.text

    required = [
        "vigile_connected_workers_total",
        "vigile_proposals_pending_total",
        "vigile_database_latency_seconds",
        "vigile_nodes_total",
        "vigile_uptime_seconds",
        "vigile_master_info",
    ]
    for metric in required:
        assert metric in body, f"Missing metric: {metric}"


@pytest.mark.asyncio
async def test_metrics_format_valid(db):
    """Each metric has preceding HELP and TYPE comment lines."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get("/metrics")
        body = response.text

    metric_names = [
        "vigile_connected_workers_total",
        "vigile_proposals_pending_total",
        "vigile_database_latency_seconds",
        "vigile_nodes_total",
        "vigile_uptime_seconds",
        "vigile_master_info",
    ]
    for metric in metric_names:
        assert f"# HELP {metric}" in body, f"Missing HELP for {metric}"
        assert f"# TYPE {metric}" in body, f"Missing TYPE for {metric}"


@pytest.mark.asyncio
async def test_metrics_counts_reflect_db_state(db):
    """Inserting a pending proposal increases vigile_proposals_pending_total."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Get baseline
        resp_before = await c.get("/metrics")
        body_before = resp_before.text
        match_before = re.search(r"vigile_proposals_pending_total (\d+)", body_before)
        baseline = int(match_before.group(1)) if match_before else 0

        # Insert a pending proposal
        proposal_id = str(uuid.uuid4())
        node_id = str(uuid.uuid4())
        now = time.time()
        await db.execute(
            "INSERT INTO nodes (id, name, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (node_id, "test-metrics-node", "CONNECTED", now, now),
        )
        await db.execute(
            """
            INSERT INTO action_proposals
                (id, node_id, action, params_json, reasoning, risk_level,
                 status, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal_id,
                node_id,
                "TEST_ACTION",
                "{}",
                "test reasoning",
                "LOW",
                "PENDING",
                "test-user",
                now,
                now,
            ),
        )
        await db.commit()

        # Check after insertion
        resp_after = await c.get("/metrics")
        body_after = resp_after.text
        match_after = re.search(r"vigile_proposals_pending_total (\d+)", body_after)
        after_count = int(match_after.group(1)) if match_after else -1

        assert after_count == baseline + 1, (
            f"Expected pending proposals to increase from {baseline} to {baseline + 1}, "
            f"got {after_count}"
        )
