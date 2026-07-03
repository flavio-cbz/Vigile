"""
Vigile — Automation Engine

Evaluates Trigger → Condition → Action rules autonomously.
Rules are loaded from the `automation_rules` DB table and cached in memory
for fast evaluation on every metric snapshot and node state transition.

Trigger types:
  - metric_threshold : fires when a metric snapshot value crosses a threshold
  - node_state       : fires when a node transitions to a specific state

Condition types:
  - always           : no condition, always execute (default)
  - time_window      : only if current time is within HH:MM-HH:MM

Action types:
  - send_intent      : send a command to the target Worker node
  - call_webhook     : HTTP POST to an external URL
  - log_message      : just write a message to automation_logs (no side effect)
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

# Supported metric field names for metric_threshold trigger
METRIC_FIELDS = {
    "cpu_percent",
    "cpu_load_1m",
    "cpu_load_5m",
    "cpu_load_15m",
    "mem_percent",
    "disk_percent",
    "uptime_seconds",
    "processes",
    "mem_used_bytes",
    "disk_used_bytes",
}

COMPARISON_OPERATORS = {"gt", "lt", "gte", "lte", "eq"}


class AutomationEngine:
    """
    Singleton engine that evaluates automation rules.
    Initialized at app startup; rules are reloaded in-memory after any CRUD.
    """

    def __init__(self) -> None:
        # List of active rule dicts loaded from DB
        self._rules: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        # In-memory cooldown tracking: "{rule_id}:{node_id}" -> last_triggered_at
        self._cooldowns: dict[str, float] = {}

    async def initialize(self, db: aiosqlite.Connection) -> None:
        """Load all enabled rules from DB into memory. Called at startup."""
        await self.reload_rules(db)
        logger.info("AutomationEngine initialized with %d rule(s).", len(self._rules))

    async def reload_rules(self, db: aiosqlite.Connection) -> None:
        """Reload all enabled rules from DB. Called after any CRUD operation."""
        async with db.execute(
            "SELECT * FROM automation_rules WHERE enabled = 1 ORDER BY created_at ASC"
        ) as cursor:
            rows = await cursor.fetchall()

        rules = []
        for row in rows:
            try:
                rule = dict(row)
                rule["trigger_config"] = json.loads(rule.get("trigger_config_json") or "{}")
                rule["conditions"] = json.loads(rule.get("conditions_json") or "[]")
                rule["actions"] = json.loads(rule.get("actions_json") or "[]")
                rules.append(rule)
            except Exception:
                logger.exception("Failed to parse rule %s — skipping.", row["id"])

        async with self._lock:
            self._rules = rules

        logger.debug("AutomationEngine: loaded %d rule(s).", len(rules))

    # -----------------------------------------------------------------------
    # Trigger evaluation — hooked via plugin_manager "on_status_report"
    # -----------------------------------------------------------------------

    async def evaluate_metric_trigger(
        self,
        node_id: str,
        snapshot: Any,
        db: aiosqlite.Connection,
    ) -> None:
        """
        Called via plugin_manager hook `on_status_report`.
        Evaluates all metric_threshold rules against the incoming snapshot.
        `snapshot` is a dict (from MetricsSnapshot.model_dump()).
        """
        async with self._lock:
            rules = list(self._rules)

        for rule in rules:
            if rule.get("trigger_type") != "metric_threshold":
                continue
            if not self._matches_node_scope(rule, node_id, snapshot):
                continue
            if not self._evaluate_metric_trigger_config(rule["trigger_config"], snapshot):
                continue
            # Fire asynchronously to not block the status report path
            asyncio.create_task(
                self._fire_rule(rule, node_id, {"snapshot": snapshot}, db),
                name=f"automation:{rule['id']}",
            )

    async def evaluate_state_trigger(
        self,
        node_id: str,
        new_state: Any,
        db: aiosqlite.Connection,
    ) -> None:
        """
        Called via node_manager state change callback.
        `new_state` is a NodeState enum value.
        """
        state_value = new_state.value if hasattr(new_state, "value") else str(new_state)

        async with self._lock:
            rules = list(self._rules)

        for rule in rules:
            if rule.get("trigger_type") != "node_state":
                continue
            expected_state = rule["trigger_config"].get("state", "")
            if expected_state != state_value:
                continue
            if not self._matches_node_scope(rule, node_id, {}):
                continue
            asyncio.create_task(
                self._fire_rule(rule, node_id, {"new_state": state_value}, db),
                name=f"automation:{rule['id']}",
            )

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _matches_node_scope(self, rule: dict, node_id: str, snapshot: Any) -> bool:
        """Return True if the rule applies to the given node."""
        target_node_id = rule.get("target_node_id")
        if target_node_id and target_node_id != node_id:
            return False
        # Group filtering is done in _fire_rule (requires DB lookup)
        return True

    def _evaluate_metric_trigger_config(self, config: dict, snapshot: Any) -> bool:
        """Return True if the snapshot satisfies the metric threshold condition."""
        metric = config.get("metric")
        operator = config.get("operator")
        threshold = config.get("threshold")

        if metric not in METRIC_FIELDS or operator not in COMPARISON_OPERATORS:
            return False

        # snapshot can be a dict or a Pydantic model
        if isinstance(snapshot, dict):
            value: Any = snapshot.get(metric)
        else:
            value = getattr(snapshot, metric, None)
        if value is None or not isinstance(value, (int, float)):
            return False

        if threshold is None or not isinstance(threshold, (int, float)):
            return False

        return {
            "gt": value > threshold,
            "lt": value < threshold,
            "gte": value >= threshold,
            "lte": value <= threshold,
            "eq": value == threshold,
        }[operator]

    def _check_cooldown(self, rule_id: str, node_id: str, cooldown_seconds: int) -> bool:
        """Return True if rule is on cooldown (should NOT fire), False if it can fire."""
        key = f"{rule_id}:{node_id}"
        last = self._cooldowns.get(key)
        if last is not None and (time.time() - last) < cooldown_seconds:
            return True  # on cooldown
        return False

    def _set_cooldown(self, rule_id: str, node_id: str) -> None:
        key = f"{rule_id}:{node_id}"
        self._cooldowns[key] = time.time()

    async def _evaluate_conditions(
        self, rule: dict, node_id: str, trigger_data: dict, db: aiosqlite.Connection
    ) -> bool:
        """Return True if all conditions pass. Empty conditions list = always True."""
        conditions = rule.get("conditions") or []

        # If target_group is set, check the node's group from DB
        target_group = rule.get("target_group")
        if target_group:
            async with db.execute(
                "SELECT node_group FROM nodes WHERE id = ?", (node_id,)
            ) as cursor:
                row = await cursor.fetchone()
            if row is None or row["node_group"] != target_group:
                return False

        for condition in conditions:
            ctype = condition.get("type")
            if ctype == "always":
                continue
            elif ctype == "time_window":
                if not self._check_time_window(condition):
                    return False
            else:
                logger.debug("Unknown condition type '%s' — skipping.", ctype)

        return True

    def _check_time_window(self, condition: dict) -> bool:
        """Return True if current time is within the HH:MM-HH:MM window."""
        window = condition.get("window", "00:00-23:59")
        try:
            start_str, end_str = window.split("-")
            sh, sm = map(int, start_str.strip().split(":"))
            eh, em = map(int, end_str.strip().split(":"))
            now = datetime.now(timezone.utc)
            current_minutes = now.hour * 60 + now.minute
            start_minutes = sh * 60 + sm
            end_minutes = eh * 60 + em
            return start_minutes <= current_minutes <= end_minutes
        except Exception:
            return True  # fail open for malformed conditions

    async def _fire_rule(
        self,
        rule: dict,
        node_id: str,
        trigger_data: dict,
        db: aiosqlite.Connection,
    ) -> None:
        """Orchestrate cooldown check → condition check → action execution → logging."""
        rule_id = rule["id"]
        cooldown_seconds = rule.get("cooldown_seconds", 300)

        # --- Cooldown check ---
        if self._check_cooldown(rule_id, node_id, cooldown_seconds):
            logger.debug("Rule %s on cooldown for node %s — skipping.", rule_id, node_id)
            await self._write_log(rule_id, node_id, "COOLDOWN", trigger_data, {}, db)
            return

        # --- Condition check ---
        try:
            conditions_ok = await self._evaluate_conditions(rule, node_id, trigger_data, db)
        except Exception:
            logger.exception("Rule %s condition evaluation failed.", rule_id)
            conditions_ok = False

        if not conditions_ok:
            logger.debug("Rule %s conditions not met for node %s — skipping.", rule_id, node_id)
            await self._write_log(rule_id, node_id, "SKIPPED", trigger_data, {}, db)
            return

        # --- Mark cooldown before executing to prevent parallel fires ---
        self._set_cooldown(rule_id, node_id)

        logger.info(
            "Automation rule '%s' (%s) triggered on node %s.",
            rule.get("name", rule_id),
            rule_id,
            node_id,
        )

        # --- Execute actions ---
        results: list[dict] = []
        overall_status = "SUCCESS"
        for action in rule.get("actions", []):
            try:
                result = await self._execute_action(action, node_id, trigger_data, db)
                results.append({"action": action.get("type"), "result": result, "status": "ok"})
            except Exception as exc:
                logger.exception("Action %s in rule %s failed.", action.get("type"), rule_id)
                results.append({"action": action.get("type"), "error": str(exc), "status": "error"})
                overall_status = "FAILED"

        # --- Write audit log ---
        try:
            from master.core.audit import AuditAction, log_action

            await log_action(
                db,
                user_id="system",
                action=AuditAction.AUTOMATION_TRIGGERED,
                node_id=node_id,
                details={
                    "rule_id": rule_id,
                    "rule_name": rule.get("name", ""),
                    "trigger_type": rule.get("trigger_type", ""),
                    "status": overall_status,
                },
            )
        except Exception:
            logger.exception("Failed to write audit log for rule %s.", rule_id)

        await self._write_log(
            rule_id, node_id, overall_status, trigger_data, {"actions": results}, db
        )

    async def _execute_action(
        self, action: dict, node_id: str, trigger_data: dict, db: aiosqlite.Connection
    ) -> dict:
        """Dispatch to the appropriate action executor."""
        atype = action.get("type")
        if atype == "send_intent":
            return await self._execute_send_intent(action, node_id, db)
        elif atype == "call_webhook":
            return await self._execute_call_webhook(action, node_id, trigger_data)
        elif atype == "log_message":
            return {"message": action.get("message", "")}
        else:
            raise ValueError(f"Unknown action type: {atype!r}")

    async def _execute_send_intent(
        self, action: dict, node_id: str, db: aiosqlite.Connection
    ) -> dict:
        """Send a worker intent via node_manager."""
        from master.core.node_manager import node_manager

        intent_action = action.get("action")
        params = action.get("params", {})
        if not intent_action:
            raise ValueError("send_intent action missing 'action' field.")

        is_connected = await node_manager.is_connected(node_id)
        if not is_connected:
            return {"status": "skipped", "reason": "node_offline"}

        result = await node_manager.send_intent(
            node_id,
            {"action": intent_action, "params": params},
            timeout=15.0,
        )
        return result

    async def _execute_call_webhook(self, action: dict, node_id: str, trigger_data: dict) -> dict:
        """HTTP POST to an external webhook URL."""
        import httpx

        url = action.get("url")
        if not url:
            raise ValueError("call_webhook action missing 'url' field.")

        headers = action.get("headers", {})
        if not isinstance(headers, dict):
            headers = {}
        headers.setdefault("Content-Type", "application/json")

        # Build body from template if provided
        body_template = action.get("body_template", "{}")
        try:
            body_str = body_template.replace("{node_id}", str(node_id)).replace(
                "{trigger_data}", json.dumps(trigger_data)
            )
            body = json.loads(body_str)
        except Exception:
            body = {"node_id": node_id, "trigger_data": trigger_data}

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=body, headers=headers)
            return {"status_code": r.status_code, "ok": r.is_success}

    async def _write_log(
        self,
        rule_id: str,
        node_id: str | None,
        status: str,
        trigger_data: dict,
        result: dict,
        db: aiosqlite.Connection,
    ) -> None:
        """Persist an automation_logs entry."""
        try:
            entry_id = str(uuid.uuid4())
            now = time.time()
            await db.execute(
                """INSERT INTO automation_logs
                   (id, rule_id, node_id, triggered_at, status, trigger_data_json, result_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry_id,
                    rule_id,
                    node_id,
                    now,
                    status,
                    json.dumps(trigger_data),
                    json.dumps(result),
                ),
            )
            await db.commit()
        except Exception:
            logger.exception("Failed to write automation log for rule %s.", rule_id)


# Module singleton
automation_engine = AutomationEngine()
