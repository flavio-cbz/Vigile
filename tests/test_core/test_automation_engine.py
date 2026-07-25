from __future__ import annotations

"""
Tests for AutomationEngine core logic.

Covers:
  - Rule loading and reloading
  - Metric trigger evaluation (operators, field lookup)
  - Cooldown enforcement
  - Condition evaluation (always, time_window)
  - State trigger evaluation
  - Action execution (log_message, send_intent fallback, unknown action)
  - _write_log persistence
"""

import asyncio
import time

import aiosqlite
import pytest

from master.core.automation_engine import AutomationEngine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> AutomationEngine:
    """Fresh AutomationEngine instance (no shared state)."""
    return AutomationEngine()


def make_rule(
    rule_id: str = "rule-1",
    trigger_type: str = "metric_threshold",
    trigger_config: dict | None = None,
    conditions: list | None = None,
    actions: list | None = None,
    cooldown_seconds: int = 0,
    target_node_id: str | None = None,
    target_group: str | None = None,
) -> dict:
    """Build a minimal rule dict with defaults."""
    return {
        "id": rule_id,
        "name": f"Test Rule {rule_id}",
        "trigger_type": trigger_type,
        "trigger_config": trigger_config
        or {"metric": "cpu_percent", "operator": "gt", "threshold": 50.0},
        "conditions": conditions or [],
        "actions": actions or [{"type": "log_message", "message": "test"}],
        "cooldown_seconds": cooldown_seconds,
        "target_node_id": target_node_id,
        "target_group": target_group,
    }


# ---------------------------------------------------------------------------
# Metric trigger evaluation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "operator, value, threshold, expected",
    [
        ("gt", 95.0, 90.0, True),
        ("gt", 85.0, 90.0, False),
        ("lt", 50.0, 90.0, True),
        ("lt", 95.0, 90.0, False),
        ("gte", 90.0, 90.0, True),
        ("gte", 89.9, 90.0, False),
        ("lte", 90.0, 90.0, True),
        ("lte", 91.0, 90.0, False),
        ("eq", 90.0, 90.0, True),
        ("eq", 91.0, 90.0, False),
    ],
)
def test_metric_trigger_operators(engine: AutomationEngine, operator, value, threshold, expected):
    config = {"metric": "cpu_percent", "operator": operator, "threshold": threshold}
    snapshot = {"cpu_percent": value}
    result = engine._evaluate_metric_trigger_config(config, snapshot)
    assert result is expected


def test_metric_trigger_dict_snapshot(engine: AutomationEngine):
    config = {"metric": "mem_percent", "operator": "gt", "threshold": 80.0}
    snapshot = {"cpu_percent": 20.0, "mem_percent": 85.0}
    assert engine._evaluate_metric_trigger_config(config, snapshot) is True


def test_metric_trigger_pydantic_like_snapshot(engine: AutomationEngine):
    """Snapshot can also be an object with attributes (Pydantic model)."""

    class FakeSnapshot:
        cpu_percent = 95.0
        mem_percent = 50.0

    config = {"metric": "cpu_percent", "operator": "gte", "threshold": 90.0}
    assert engine._evaluate_metric_trigger_config(config, FakeSnapshot()) is True


def test_metric_trigger_missing_field(engine: AutomationEngine):
    config = {"metric": "cpu_load_1m", "operator": "gt", "threshold": 5.0}
    snapshot = {"cpu_percent": 90.0}  # cpu_load_1m not present
    assert engine._evaluate_metric_trigger_config(config, snapshot) is False


def test_metric_trigger_invalid_metric(engine: AutomationEngine):
    config = {"metric": "invalid_metric", "operator": "gt", "threshold": 50.0}
    snapshot = {"cpu_percent": 90.0}
    assert engine._evaluate_metric_trigger_config(config, snapshot) is False


def test_metric_trigger_invalid_operator(engine: AutomationEngine):
    config = {"metric": "cpu_percent", "operator": "contains", "threshold": 50.0}
    snapshot = {"cpu_percent": 90.0}
    assert engine._evaluate_metric_trigger_config(config, snapshot) is False


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------


def test_cooldown_not_active_initially(engine: AutomationEngine):
    assert engine._check_cooldown("rule-1", "node-1", 300) is False


def test_cooldown_active_after_set(engine: AutomationEngine):
    engine._set_cooldown("rule-1", "node-1")
    assert engine._check_cooldown("rule-1", "node-1", 300) is True


def test_cooldown_expired(engine: AutomationEngine):
    key = "rule-1:node-1"
    engine._cooldowns[key] = time.time() - 400  # expired 400s ago
    assert engine._check_cooldown("rule-1", "node-1", 300) is False


def test_cooldown_zero_always_ok(engine: AutomationEngine):
    engine._set_cooldown("rule-1", "node-1")
    # cooldown_seconds=0 → never on cooldown
    assert engine._check_cooldown("rule-1", "node-1", 0) is False


def test_cooldown_separate_nodes(engine: AutomationEngine):
    engine._set_cooldown("rule-1", "node-1")
    assert engine._check_cooldown("rule-1", "node-2", 300) is False


# ---------------------------------------------------------------------------
# Time window condition
# ---------------------------------------------------------------------------


def test_time_window_valid_format(engine: AutomationEngine):
    """Smoke test — just checks no exception is thrown."""
    condition = {"type": "time_window", "window": "00:00-23:59"}
    result = engine._check_time_window(condition)
    assert isinstance(result, bool)


def test_time_window_malformed_returns_true(engine: AutomationEngine):
    """Malformed window fails open (returns True = condition passes)."""
    condition = {"type": "time_window", "window": "INVALID"}
    assert engine._check_time_window(condition) is True


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conditions_empty_always_passes(engine: AutomationEngine, db: aiosqlite.Connection):
    rule = make_rule(conditions=[])
    result = await engine._evaluate_conditions(rule, "node-1", {}, db)
    assert result is True


@pytest.mark.asyncio
async def test_conditions_always_passes(engine: AutomationEngine, db: aiosqlite.Connection):
    rule = make_rule(conditions=[{"type": "always"}])
    result = await engine._evaluate_conditions(rule, "node-1", {}, db)
    assert result is True


@pytest.mark.asyncio
async def test_conditions_group_filter_no_match(engine: AutomationEngine, db: aiosqlite.Connection):
    """Rule with target_group='production' should fail if node is in a different group."""
    now = time.time()
    node_id = "test-node-group"
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at, node_group) VALUES (?,?,?,?,?,?)",
        (node_id, "gn", "CONNECTED", now, now, "staging"),
    )
    await db.commit()

    rule = make_rule(conditions=[], target_group="production")
    result = await engine._evaluate_conditions(rule, node_id, {}, db)
    assert result is False


@pytest.mark.asyncio
async def test_conditions_group_filter_match(engine: AutomationEngine, db: aiosqlite.Connection):
    now = time.time()
    node_id = "test-node-grp2"
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at, node_group) VALUES (?,?,?,?,?,?)",
        (node_id, "gn2", "CONNECTED", now, now, "production"),
    )
    await db.commit()

    rule = make_rule(conditions=[], target_group="production")
    result = await engine._evaluate_conditions(rule, node_id, {}, db)
    assert result is True


# ---------------------------------------------------------------------------
# _write_log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_log_creates_entry(engine: AutomationEngine, db: aiosqlite.Connection):
    # We need a dummy rule in the DB (due to FK)
    now = time.time()
    rule_id = "rule-log-test"
    await db.execute(
        """INSERT INTO automation_rules
           (id, name, enabled, trigger_type, trigger_config_json, conditions_json,
            actions_json, cooldown_seconds, created_by, created_at, updated_at)
           VALUES (?, 'Test', 1, 'metric_threshold', '{}', '[]', '[]', 300, 'test-user', ?, ?)""",
        (rule_id, now, now),
    )
    await db.commit()

    await engine._write_log(rule_id, None, "SUCCESS", {"cpu": 95.0}, {"ok": True}, db)

    async with db.execute("SELECT * FROM automation_logs WHERE rule_id = ?", (rule_id,)) as cursor:
        rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "SUCCESS"


# ---------------------------------------------------------------------------
# reload_rules
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reload_rules_loads_enabled_only(engine: AutomationEngine, db: aiosqlite.Connection):
    now = time.time()
    for rule_id, enabled in [("r1", 1), ("r2", 0), ("r3", 1)]:
        await db.execute(
            """INSERT INTO automation_rules
               (id, name, enabled, trigger_type, trigger_config_json, conditions_json,
                actions_json, cooldown_seconds, created_by, created_at, updated_at)
               VALUES (?, ?, ?, 'metric_threshold', '{}', '[]', '[]', 300, 'test-user', ?, ?)""",
            (rule_id, f"Rule {rule_id}", enabled, now, now),
        )
    await db.commit()

    await engine.reload_rules(db)
    assert len(engine._rules) == 2
    ids = [r["id"] for r in engine._rules]
    assert "r1" in ids
    assert "r3" in ids
    assert "r2" not in ids


# ---------------------------------------------------------------------------
# Node scope filtering
# ---------------------------------------------------------------------------


def test_node_scope_no_restriction(engine: AutomationEngine):
    rule = make_rule(target_node_id=None)
    assert engine._matches_node_scope(rule, "any-node", {}) is True


def test_node_scope_specific_match(engine: AutomationEngine):
    rule = make_rule(target_node_id="node-abc")
    assert engine._matches_node_scope(rule, "node-abc", {}) is True


def test_node_scope_specific_no_match(engine: AutomationEngine):
    rule = make_rule(target_node_id="node-abc")
    assert engine._matches_node_scope(rule, "node-xyz", {}) is False
