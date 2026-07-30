from __future__ import annotations

"""
Vigile — Automation Rules API Router

Endpoints:
  - GET    /api/admin/automations               → List all automation rules
  - POST   /api/admin/automations               → Create a new rule
  - GET    /api/admin/automations/{rule_id}     → Get rule details
  - PATCH  /api/admin/automations/{rule_id}     → Update a rule
  - DELETE /api/admin/automations/{rule_id}     → Delete a rule
  - POST   /api/admin/automations/{rule_id}/toggle → Enable / disable
  - GET    /api/admin/automations/{rule_id}/logs   → Execution history
  - POST   /api/admin/automations/{rule_id}/test   → Force trigger on a node
"""

import asyncio
import json
import logging
import time
import uuid

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from master.api.deps import require_role
from master.api.schemas.automations import (
    AutomationLogResponse,
    AutomationRuleCreate,
    AutomationRuleResponse,
    AutomationRuleUpdate,
    AutomationTestRequest,
)
from master.core.audit import AuditAction, log_action
from master.core.automation_engine import automation_engine
from master.db.database import get_db_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/automations", tags=["automations"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _row_to_response(row: dict) -> AutomationRuleResponse:
    """Convert a raw DB row into the response schema."""
    db = get_db_conn()

    # Fetch aggregate stats
    async with db.execute(
        "SELECT COUNT(*) as total, MAX(triggered_at) as last FROM automation_logs WHERE rule_id = ?",
        (row["id"],),
    ) as cursor:
        stats = await cursor.fetchone()

    return AutomationRuleResponse(
        id=row["id"],
        name=row["name"],
        description=row["description"] or "",
        enabled=bool(row["enabled"]),
        trigger_type=row["trigger_type"],
        trigger_config=json.loads(row["trigger_config_json"] or "{}"),
        conditions=json.loads(row["conditions_json"] or "[]"),
        actions=json.loads(row["actions_json"] or "[]"),
        target_node_id=row["target_node_id"],
        target_group=row["target_group"],
        cooldown_seconds=row["cooldown_seconds"],
        trust_level=row["trust_level"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        total_executions=stats["total"] if stats else 0,
        last_triggered_at=stats["last"] if stats else None,
    )


async def _get_rule_or_404(rule_id: str) -> dict:
    db = get_db_conn()
    async with db.execute("SELECT * FROM automation_rules WHERE id = ?", (rule_id,)) as cursor:
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")
    return dict(row)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=List[AutomationRuleResponse],
    summary="List automation rules",
)
async def list_rules(
    enabled_only: bool = Query(default=False, description="Filter to enabled rules only"),
    claims=Depends(require_role("operator")),
) -> list[AutomationRuleResponse]:
    """Return all automation rules with execution stats. Operator+ access."""
    db = get_db_conn()
    query = "SELECT * FROM automation_rules"
    params: tuple = ()
    if enabled_only:
        query += " WHERE enabled = 1"
    query += " ORDER BY created_at DESC"

    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()

    return [await _row_to_response(dict(row)) for row in rows]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=AutomationRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create automation rule",
)
async def create_rule(
    body: AutomationRuleCreate,
    claims=Depends(require_role("admin")),
) -> AutomationRuleResponse:
    """Create a new automation rule. Admin only."""
    db = get_db_conn()
    now = time.time()
    rule_id = str(uuid.uuid4())

    # Validate target_node_id if provided
    if body.target_node_id:
        async with db.execute(
            "SELECT id FROM nodes WHERE id = ?", (body.target_node_id,)
        ) as cursor:
            node_row = await cursor.fetchone()
        if node_row is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Node not found: {body.target_node_id}",
            )

    await db.execute(
        """INSERT INTO automation_rules
           (id, name, description, enabled, trigger_type, trigger_config_json,
            conditions_json, actions_json, target_node_id, target_group,
            cooldown_seconds, trust_level, created_by, created_at, updated_at)
           VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            rule_id,
            body.name,
            body.description,
            body.trigger_type,
            json.dumps(body.trigger_config),
            json.dumps(body.conditions),
            json.dumps(body.actions),
            body.target_node_id,
            body.target_group,
            body.cooldown_seconds,
            body.trust_level,
            claims["sub"],
            now,
            now,
        ),
    )
    await db.commit()

    await log_action(
        db,
        user_id=claims["sub"],
        action=AuditAction.CREATE_AUTOMATION_RULE,
        details={"rule_id": rule_id, "name": body.name, "trigger_type": body.trigger_type},
    )

    # Hot-reload engine rules
    await automation_engine.reload_rules(db)

    row = await _get_rule_or_404(rule_id)
    return await _row_to_response(row)


# ---------------------------------------------------------------------------
# Get single
# ---------------------------------------------------------------------------


@router.get(
    "/{rule_id}",
    response_model=AutomationRuleResponse,
    summary="Get automation rule",
)
async def get_rule(
    rule_id: str,
    claims=Depends(require_role("operator")),
) -> AutomationRuleResponse:
    row = await _get_rule_or_404(rule_id)
    return await _row_to_response(row)


# ---------------------------------------------------------------------------
# Update (PATCH)
# ---------------------------------------------------------------------------


@router.patch(
    "/{rule_id}",
    response_model=AutomationRuleResponse,
    summary="Update automation rule",
)
async def update_rule(
    rule_id: str,
    body: AutomationRuleUpdate,
    claims=Depends(require_role("admin")),
) -> AutomationRuleResponse:
    """Partially update a rule. Admin only."""
    db = get_db_conn()
    row = await _get_rule_or_404(rule_id)

    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if body.trigger_config is not None:
        updates["trigger_config_json"] = json.dumps(body.trigger_config)
    if body.conditions is not None:
        updates["conditions_json"] = json.dumps(body.conditions)
    if body.actions is not None:
        updates["actions_json"] = json.dumps(body.actions)
    if body.target_node_id is not None:
        updates["target_node_id"] = body.target_node_id
    if body.target_group is not None:
        updates["target_group"] = body.target_group
    if body.cooldown_seconds is not None:
        updates["cooldown_seconds"] = body.cooldown_seconds
    if body.trust_level is not None:
        updates["trust_level"] = body.trust_level

    if not updates:
        return await _row_to_response(row)

    updates["updated_at"] = time.time()
    _VALID_RULE_FIELDS = {
        "name",
        "trigger_type",
        "trigger_config_json",
        "actions_json",
        "target_node_id",
        "target_group",
        "cooldown_seconds",
        "trust_level",
        "updated_at",
    }
    for k in updates:
        if k not in _VALID_RULE_FIELDS:
            raise ValueError(f"Invalid rule field: {k}")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [rule_id]
    query = "UPDATE automation_rules SET " + set_clause + " WHERE id = ?"
    await db.execute(query, values)
    await db.commit()

    await log_action(
        db,
        user_id=claims["sub"],
        action=AuditAction.UPDATE_AUTOMATION_RULE,
        details={"rule_id": rule_id, "fields": list(updates.keys())},
    )

    await automation_engine.reload_rules(db)

    row = await _get_rule_or_404(rule_id)
    return await _row_to_response(row)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete(
    "/{rule_id}",
    summary="Delete automation rule",
)
async def delete_rule(
    rule_id: str,
    claims=Depends(require_role("admin")),
) -> Response:
    """Delete a rule and all its logs. Admin only."""
    db = get_db_conn()
    await _get_rule_or_404(rule_id)

    await log_action(
        db,
        user_id=claims["sub"],
        action=AuditAction.DELETE_AUTOMATION_RULE,
        details={"rule_id": rule_id},
    )
    await db.execute("DELETE FROM automation_rules WHERE id = ?", (rule_id,))
    await db.commit()

    await automation_engine.reload_rules(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Toggle enable / disable
# ---------------------------------------------------------------------------


@router.post(
    "/{rule_id}/toggle",
    response_model=AutomationRuleResponse,
    summary="Toggle rule enabled/disabled",
)
async def toggle_rule(
    rule_id: str,
    claims=Depends(require_role("admin")),
) -> AutomationRuleResponse:
    """Flip the enabled flag. Admin only."""
    db = get_db_conn()
    row = await _get_rule_or_404(rule_id)

    new_enabled = 0 if row["enabled"] else 1
    await db.execute(
        "UPDATE automation_rules SET enabled = ?, updated_at = ? WHERE id = ?",
        (new_enabled, time.time(), rule_id),
    )
    await db.commit()

    await log_action(
        db,
        user_id=claims["sub"],
        action=AuditAction.TOGGLE_AUTOMATION_RULE,
        details={"rule_id": rule_id, "enabled": bool(new_enabled)},
    )

    await automation_engine.reload_rules(db)

    row = await _get_rule_or_404(rule_id)
    return await _row_to_response(row)


# ---------------------------------------------------------------------------
# Execution logs
# ---------------------------------------------------------------------------


@router.get(
    "/{rule_id}/logs",
    response_model=List[AutomationLogResponse],
    summary="Get rule execution logs",
)
async def get_rule_logs(
    rule_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    claims=Depends(require_role("operator")),
) -> list[AutomationLogResponse]:
    """Paginated execution history for a rule. Operator+ access."""
    db = get_db_conn()
    await _get_rule_or_404(rule_id)

    async with db.execute(
        """SELECT * FROM automation_logs WHERE rule_id = ?
           ORDER BY triggered_at DESC LIMIT ? OFFSET ?""",
        (rule_id, limit, offset),
    ) as cursor:
        rows = await cursor.fetchall()

    return [
        AutomationLogResponse(
            id=row["id"],
            rule_id=row["rule_id"],
            node_id=row["node_id"],
            triggered_at=row["triggered_at"],
            status=row["status"],
            trigger_data=json.loads(row["trigger_data_json"] or "{}"),
            result=json.loads(row["result_json"] or "{}"),
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Manual test trigger
# ---------------------------------------------------------------------------


@router.post(
    "/{rule_id}/test",
    response_model=AutomationRuleResponse,
    summary="Force trigger rule on a node",
)
async def test_rule(
    rule_id: str,
    body: AutomationTestRequest,
    claims=Depends(require_role("admin")),
) -> AutomationRuleResponse:
    """
    Bypass cooldown and conditions and immediately execute all actions of this
    rule against the specified node. Useful for integration testing. Admin only.
    """
    db = get_db_conn()
    row = await _get_rule_or_404(rule_id)

    async with db.execute("SELECT id FROM nodes WHERE id = ?", (body.node_id,)) as cursor:
        node_row = await cursor.fetchone()
    if node_row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Node not found: {body.node_id}",
        )

    # Build a synthetic trigger_data dict
    trigger_data = {"manual_test": True, "triggered_by": claims["sub"]}

    # Parse rule into the format _fire_rule expects
    rule_dict = dict(row)
    rule_dict["trigger_config"] = json.loads(rule_dict.get("trigger_config_json") or "{}")
    rule_dict["conditions"] = []  # bypass conditions for manual test
    rule_dict["actions"] = json.loads(rule_dict.get("actions_json") or "[]")
    rule_dict["cooldown_seconds"] = 0  # bypass cooldown for manual test

    asyncio.create_task(
        automation_engine._fire_rule(rule_dict, body.node_id, trigger_data, db),
        name=f"automation:test:{rule_id}",
    )

    await log_action(
        db,
        user_id=claims["sub"],
        action=AuditAction.AUTOMATION_TRIGGERED,
        node_id=body.node_id,
        details={"rule_id": rule_id, "manual_test": True},
    )

    return await _row_to_response(row)
