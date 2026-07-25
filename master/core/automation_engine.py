from __future__ import annotations

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
import httpx

from master.core.action_proposal import ActionProposal
from master.core.audit import AuditAction, log_action
from master.core.node_manager import node_manager

logger = logging.getLogger(__name__)

# Supported metric field names for metric_threshold trigger
METRIC_FIELDS = {
    # CPU
    "cpu_percent",
    "cpu_load_1m",
    "cpu_load_5m",
    "cpu_load_15m",
    "cpu_cores",
    "cpu_throttled_count",
    # Memory
    "mem_percent",
    "mem_used_bytes",
    "mem_total_bytes",
    # Swap
    "swap_used_bytes",
    "swap_total_bytes",
    # Disk
    "disk_percent",
    "disk_used_bytes",
    "disk_total_bytes",
    "disk_reads",
    "disk_writes",
    "disk_read_bytes",
    "disk_write_bytes",
    # System
    "uptime_seconds",
    "processes",
    "context_switches",
    # Network I/O
    "net_bytes_recv",
    "net_bytes_sent",
    "net_packets_recv",
    "net_packets_sent",
    "net_errors_in",
    "net_errors_out",
    "net_drops_in",
    "net_drops_out",
    # Temperature
    "temp_celsius",
    # PSI
    "psi_cpu_avg10",
    "psi_mem_avg10",
    "psi_io_avg10",
    # File handles
    "file_handles_used",
    "file_handles_max",
    # Entropy
    "entropy_avail",
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

        # Also evaluate node_health triggers based on the state transition
        health_event = self._state_to_health_event(state_value)
        if health_event is not None:
            await self.evaluate_node_health(node_id, health_event, db)

    # -----------------------------------------------------------------------
    # New trigger types: node_intent_failure, node_health, audit_alert
    # -----------------------------------------------------------------------

    async def evaluate_intent_failure(
        self,
        node_id: str,
        action: str,
        success: bool,
        db: aiosqlite.Connection,
    ) -> None:
        """
        Called when an intent result is received (from worker_handler).
        Evaluates all node_intent_failure rules for the given node.
        """
        if success:
            return

        async with self._lock:
            rules = list(self._rules)

        now = time.time()
        for rule in rules:
            if rule.get("trigger_type") != "node_intent_failure":
                continue
            if not self._matches_node_scope(rule, node_id, {}):
                continue

            config = rule.get("trigger_config", {})
            window = config.get("window_seconds", 300)
            action_filter = config.get("action")

            # Query recent failed intents for this node
            query = (
                "SELECT COUNT(*) as failed_count FROM action_proposals "
                "WHERE node_id = ? AND status = 'FAILED' AND created_at > ?"
            )
            params: tuple = (node_id, now - window)
            if action_filter:
                query += " AND action = ?"
                params = (node_id, now - window, action_filter)

            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
            failed_count = row["failed_count"] if row else 0

            context = {
                "action": action,
                "success": success,
                "node_id": node_id,
                "failed_count": failed_count,
                "window_seconds": window,
            }
            if self._evaluate_intent_failure(rule, context):
                asyncio.create_task(
                    self._fire_rule(rule, node_id, context, db),
                    name=f"automation:{rule['id']}",
                )

    async def evaluate_node_health(
        self,
        node_id: str,
        event: str,
        db: aiosqlite.Connection,
    ) -> None:
        """
        Called on node health events (enrolled, lost, stale, reconnected, revoked).
        Evaluates all node_health rules for the given node.
        """
        async with self._lock:
            rules = list(self._rules)

        for rule in rules:
            if rule.get("trigger_type") != "node_health":
                continue
            if not self._matches_node_scope(rule, node_id, {}):
                continue

            context = {"event": event, "node_id": node_id}
            if self._evaluate_node_health(rule, context):
                asyncio.create_task(
                    self._fire_rule(rule, node_id, context, db),
                    name=f"automation:{rule['id']}",
                )

    async def evaluate_audit_event(
        self,
        node_id: str | None,
        action: str,
        db: aiosqlite.Connection,
    ) -> None:
        """
        Called on audit events. Evaluates all audit_alert rules.
        `node_id` may be None for fleet-wide audit events.
        """
        async with self._lock:
            rules = list(self._rules)

        for rule in rules:
            if rule.get("trigger_type") != "audit_alert":
                continue
            if not self._matches_node_scope(rule, node_id or "", {}):
                continue

            context = {"action": action, "node_id": node_id}
            if self._evaluate_audit_alert(rule, context):
                asyncio.create_task(
                    self._fire_rule(rule, node_id or "", context, db),
                    name=f"automation:{rule['id']}",
                )

    async def evaluate_alert_callback(
        self,
        node_id: str,
        alert_name: str,
        severity: str,
        db: aiosqlite.Connection,
    ) -> None:
        """
        Called by AlertEngine when an alert fires.
        Evaluates all alert_* trigger rules that match the alert name.
        """
        async with self._lock:
            rules = list(self._rules)

        for rule in rules:
            trigger_type = rule.get("trigger_type", "")
            if not trigger_type.startswith("alert_"):
                continue
            # Match trigger_type (e.g. "alert_cpu_high") to alert_name
            if trigger_type != alert_name:
                continue
            if not self._matches_node_scope(rule, node_id, {}):
                continue

            context = {
                "alert_name": alert_name,
                "severity": severity,
                "node_id": node_id,
            }
            asyncio.create_task(
                self._fire_rule(rule, node_id, context, db),
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

    @staticmethod
    def _state_to_health_event(state_value: str) -> str | None:
        """Map a NodeState value to a node_health event string."""
        mapping = {
            "LOST": "lost",
            "STALE": "stale",
            "CONNECTED": "reconnected",
            "ENROLLING": "enrolled",
            "UNCONFIGURED": "enrolled",
            "DISABLED": "revoked",
        }
        return mapping.get(state_value)

    def _evaluate_intent_failure(self, rule: dict, context: dict) -> bool:
        """Return True if the intent failure conditions are met."""
        config = rule.get("trigger_config", {})
        min_failures = config.get("min_failures", 1)
        action_filter = config.get("action")

        if action_filter and context.get("action") != action_filter:
            return False

        failed_count = context.get("failed_count", 0)
        return failed_count >= min_failures

    def _evaluate_node_health(self, rule: dict, context: dict) -> bool:
        """Return True if the node health event matches the rule."""
        config = rule.get("trigger_config", {})
        expected_event = config.get("event", "")
        return expected_event == context.get("event")

    def _evaluate_audit_alert(self, rule: dict, context: dict) -> bool:
        """Return True if the audit action matches the rule."""
        config = rule.get("trigger_config", {})
        expected_action = config.get("action", "")
        return expected_action == context.get("action")

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
        trust_level = rule.get("trust_level", "auto")
        results: list[dict] = []
        overall_status = "SUCCESS"
        for action in rule.get("actions", []):
            try:
                result = await self._execute_action(
                    action, node_id, trigger_data, db, trust_level=trust_level
                )
                results.append({"action": action.get("type"), "result": result, "status": "ok"})
            except Exception as exc:
                logger.exception("Action %s in rule %s failed.", action.get("type"), rule_id)
                results.append({"action": action.get("type"), "error": str(exc), "status": "error"})
                overall_status = "FAILED"

        # --- Write audit log ---
        try:
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
        self, action: dict, node_id: str, trigger_data: dict, db: aiosqlite.Connection,
        trust_level: str = "auto",
    ) -> dict:
        """Dispatch to the appropriate action executor."""
        atype = action.get("type")
        if atype == "send_intent":
            return await self._execute_send_intent(action, node_id, db, trust_level=trust_level)
        elif atype == "call_webhook":
            return await self._execute_call_webhook(action, node_id, trigger_data)
        elif atype == "log_message":
            return {"message": action.get("message", "")}
        else:
            raise ValueError(f"Unknown action type: {atype!r}")

    async def _execute_send_intent(
        self, action: dict, node_id: str, db: aiosqlite.Connection,
        trust_level: str = "auto",
    ) -> dict:
        """Send a worker intent via node_manager or create a pending proposal.

        Trust levels:
          - auto: auto-approve the ActionProposal and execute immediately.
          - always_approve / manual: create a PENDING ActionProposal for operator review.
        """
        intent_action = action.get("action")
        params = action.get("params", {})
        if not intent_action:
            raise ValueError("send_intent action missing 'action' field.")

        is_connected = await node_manager.is_connected(node_id)
        if not is_connected:
            return {"status": "skipped", "reason": "node_offline"}

        if trust_level in ("always_approve", "manual"):
            risk = "HIGH" if trust_level == "manual" else "MEDIUM"
            proposal = ActionProposal(
                node_id=node_id,
                action=intent_action,
                params=params,
                reasoning=f"Automation rule triggered this action (trust_level={trust_level}).",
                risk_level=risk,
                created_by="automation",
            )

            data = proposal.to_db_dict()
            await db.execute(
                """INSERT INTO action_proposals
                   (id, node_id, action, params_json, reasoning, risk_level,
                    status, created_by, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data["id"], data["node_id"], data["action"], data["params_json"],
                    data["reasoning"], data["risk_level"],
                    data["status"], data["created_by"],
                    data["created_at"], data["updated_at"],
                ),
            )
            await db.commit()

            await log_action(
                db,
                user_id="system",
                action=AuditAction.AUTOMATION_TRIGGERED,
                node_id=node_id,
                details={
                    "proposal_id": proposal.id,
                    "action": intent_action,
                    "trust_level": trust_level,
                    "status": "PENDING_APPROVAL",
                },
            )

            return {"status": "pending_approval", "proposal_id": proposal.id}

        proposal = ActionProposal(
            node_id=node_id,
            action=intent_action,
            params=params,
            reasoning=f"Automation rule triggered this action (trust_level=auto).",
            risk_level="LOW",
            created_by="automation",
            status="APPROVED",
            approved_by="system",
        )

        data = proposal.to_db_dict()
        await db.execute(
            """INSERT INTO action_proposals
               (id, node_id, action, params_json, reasoning, risk_level,
                status, created_by, approved_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["id"], data["node_id"], data["action"], data["params_json"],
                data["reasoning"], data["risk_level"],
                data["status"], data["created_by"], data["approved_by"],
                data["created_at"], data["updated_at"],
            ),
        )
        await db.commit()

        try:
            result = await node_manager.send_intent(
                node_id,
                {"action": intent_action, "params": params},
                timeout=15.0,
            )
            success = result.get("success", False)
            proposal.complete(success=success, result_data=result)

            db_data = proposal.to_db_dict()
            await db.execute(
                """UPDATE action_proposals SET
                    status = ?, updated_at = ?, executed_at = ?, result_json = ?
                   WHERE id = ?""",
                (
                    db_data["status"], db_data["updated_at"],
                    db_data["executed_at"], db_data["result_json"],
                    proposal.id,
                ),
            )
            await db.commit()

            await log_action(
                db,
                user_id="system",
                action=AuditAction.AUTOMATION_TRIGGERED,
                node_id=node_id,
                details={
                    "proposal_id": proposal.id,
                    "action": intent_action,
                    "trust_level": "auto",
                    "status": proposal.status,
                },
            )

            return result
        except RuntimeError as exc:
            proposal.complete(success=False, result_data={"error": str(exc)})
            db_data = proposal.to_db_dict()
            await db.execute(
                """UPDATE action_proposals SET
                    status = ?, updated_at = ?, executed_at = ?, result_json = ?
                   WHERE id = ?""",
                (
                    db_data["status"], db_data["updated_at"],
                    db_data["executed_at"], db_data["result_json"],
                    proposal.id,
                ),
            )
            await db.commit()
            return {"success": False, "error": str(exc)}
        except TimeoutError:
            proposal.complete(success=False, result_data={"error": "worker_timeout"})
            db_data = proposal.to_db_dict()
            await db.execute(
                """UPDATE action_proposals SET
                    status = ?, updated_at = ?, executed_at = ?, result_json = ?
                   WHERE id = ?""",
                (
                    db_data["status"], db_data["updated_at"],
                    db_data["executed_at"], db_data["result_json"],
                    proposal.id,
                ),
            )
            await db.commit()
            return {"success": False, "error": "Worker did not respond in time"}

    async def _execute_call_webhook(self, action: dict, node_id: str, trigger_data: dict) -> dict:
        """HTTP POST to an external webhook URL."""
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
