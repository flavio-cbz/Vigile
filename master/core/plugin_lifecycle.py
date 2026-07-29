"""
Vigile — Plugin Lifecycle Manager (3-Axis State Machine)

Implements the B6 decision for strict, auditable plugin lifecycle management
with three orthogonal state axes:

  Axe 1 — État désiré admin:  ENABLED, DISABLED
  Axe 2 — État runtime:       UNLOADED, LOADING, ACTIVE, ERROR, STOPPING
  Axe 3 — Opération lifecycle: IDLE, INSTALLING, UNINSTALLING, UPGRADING

**ERROR is sticky**: when a plugin enters ERROR runtime state, the desired
state is automatically set to DISABLED. The plugin cannot leave ERROR without
explicit admin re-activation (transition to ENABLED). This prevents automatic
recovery loops and forces an audited human decision.

Design rules:
  - DI strict: constructor receives ``db`` and ``engine`` — never reads
    ``settings.*`` or ``os.getenv``.
  - All DB mutations use the ``transaction()`` context manager for safe WAL
    serialisation.
  - State is tracked in-memory and synchronised to the ``plugins`` table
    (``enabled`` → desired state, ``status`` → runtime state).
"""

from __future__ import annotations

from typing import Any

import aiosqlite
import logging

from master.db.database import transaction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State enums (StrEnum for serialisation compat)
# ---------------------------------------------------------------------------

from enum import Enum

try:
    from enum import StrEnum
except ImportError:

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        def __str__(self) -> str:
            return str(self.value)


# ---------------------------------------------------------------------------
# Axe 1 — État désiré admin
# ---------------------------------------------------------------------------


class DesiredState(StrEnum):
    """Administrator-desired activation state (persisted in ``enabled`` column)."""

    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


# ---------------------------------------------------------------------------
# Axe 2 — État runtime
# ---------------------------------------------------------------------------


class RuntimeState(StrEnum):
    """Actual plugin runtime state tracked in-memory + ``status`` column."""

    UNLOADED = "UNLOADED"
    LOADING = "LOADING"
    ACTIVE = "ACTIVE"
    ERROR = "ERROR"
    STOPPING = "STOPPING"


# ---------------------------------------------------------------------------
# Axe 3 — Opération lifecycle
# ---------------------------------------------------------------------------


class OperationState(StrEnum):
    """Long-running lifecycle operation state (install/upgrade/uninstall)."""

    IDLE = "IDLE"
    INSTALLING = "INSTALLING"
    UNINSTALLING = "UNINSTALLING"
    UPGRADING = "UPGRADING"


# ---------------------------------------------------------------------------
# Convenience aggregate enum
# ---------------------------------------------------------------------------


class PluginLifecycleState(StrEnum):
    """All 11 lifecycle states across the 3 axes (convenience enumeration)."""

    # Axe 1
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    # Axe 2
    UNLOADED = "UNLOADED"
    LOADING = "LOADING"
    ACTIVE = "ACTIVE"
    ERROR = "ERROR"
    STOPPING = "STOPPING"
    # Axe 3
    IDLE = "IDLE"
    INSTALLING = "INSTALLING"
    UNINSTALLING = "UNINSTALLING"
    UPGRADING = "UPGRADING"


# ---------------------------------------------------------------------------
# Validation tables
# ---------------------------------------------------------------------------

# Valid runtime-state transitions (called by the engine, not directly)
_VALID_RUNTIME_TRANSITIONS: dict[str, set[str]] = {
    RuntimeState.UNLOADED: {RuntimeState.LOADING},
    RuntimeState.LOADING: {RuntimeState.ACTIVE, RuntimeState.ERROR},
    RuntimeState.ACTIVE: {RuntimeState.STOPPING, RuntimeState.ERROR},
    RuntimeState.ERROR: set(),  # Terminal — only leaves via admin re-activation
    RuntimeState.STOPPING: {RuntimeState.UNLOADED, RuntimeState.ERROR},
}

# Valid operation-state transitions
_VALID_OPERATION_TRANSITIONS: dict[str, set[str]] = {
    OperationState.IDLE: {
        OperationState.INSTALLING,
        OperationState.UNINSTALLING,
        OperationState.UPGRADING,
    },
    OperationState.INSTALLING: {OperationState.IDLE, OperationState.UNINSTALLING},
    OperationState.UNINSTALLING: {OperationState.IDLE},
    OperationState.UPGRADING: {OperationState.IDLE},
}


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class PluginLifecycleManager:
    """3-axis state machine for plugin lifecycle management.

    Responsibilities:
      1. Track the three state axes per plugin (in-memory + DB sync).
      2. Validate desired-state transitions against the current compound state.
      3. Enforce the ERROR-is-sticky rule (admin re-activation required).
      4. Provide ``reconcile_after_crash`` to recover stuck plugins.
      5. Offer internal helpers (``_set_runtime``, ``_remove``) for the engine
         to report runtime transitions.

    The engine is responsible for executing the actual runtime work
    (loading, unloading); this manager only validates, records, and persists.
    """

    def __init__(self, engine: Any, db: aiosqlite.Connection | None = None) -> None:
        self._engine = engine
        self._db = db
        # In-memory store: plugin_id -> {desired, runtime, operation}
        self._states: dict[str, dict[str, str]] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _db_conn(self) -> Any | None:
        """Resolve a database connection via explicit ref or engine."""
        if self._db is not None:
            return self._db
        if self._engine is not None:
            return getattr(self._engine, "db", None)
        return None

    def _ensure(self, plugin_id: str) -> None:
        """Initialise in-memory state defaults if not yet tracked."""
        if plugin_id not in self._states:
            self._states[plugin_id] = {
                "desired": DesiredState.DISABLED.value,
                "runtime": RuntimeState.UNLOADED.value,
                "operation": OperationState.IDLE.value,
            }

    def _set_in_memory(
        self, plugin_id: str, desired: str, runtime: str, operation: str
    ) -> None:
        self._states[plugin_id] = {
            "desired": desired,
            "runtime": runtime,
            "operation": operation,
        }

    def _validate_desired_transition(
        self, plugin_id: str, curr_desired: str, curr_runtime: str, curr_operation: str, new_desired: str
    ) -> None:
        """Raise ValueError if the desired-state transition is invalid."""
        # Same state → no-op (allowed)
        if new_desired == curr_desired:
            return

        # Block transitions during lifecycle operations
        if curr_operation != OperationState.IDLE.value:
            raise ValueError(
                f"Plugin '{plugin_id}' operation is '{curr_operation}' "
                f"(must be IDLE to change desired state)"
            )

        # Block transitions while runtime is STOPPING
        if curr_runtime == RuntimeState.STOPPING.value:
            raise ValueError(
                f"Plugin '{plugin_id}' runtime is STOPPING "
                f"(wait for completion before changing desired state)"
            )

        # ERROR is sticky — only ENABLED is a valid target from ERROR
        if curr_runtime == RuntimeState.ERROR.value:
            if new_desired != DesiredState.ENABLED.value:
                raise ValueError(
                    f"Plugin '{plugin_id}' is in ERROR state. "
                    f"Only explicit re-activation (ENABLED) is allowed. "
                    f"Cannot transition to '{new_desired}'."
                )
            return  # ERROR → ENABLED is valid (admin re-activation)

    # ------------------------------------------------------------------
    # Public queries
    # ------------------------------------------------------------------

    async def get_desired_state(self, plugin_id: str) -> str:
        """Return the admin-desired state (ENABLED | DISABLED) from DB.

        Falls back to in-memory cache when DB is unavailable.
        """
        self._ensure(plugin_id)
        db = self._db_conn()
        if db is not None:
            try:
                async with db.execute(
                    "SELECT enabled FROM plugins WHERE id = ?", (plugin_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row is not None:
                        return (
                            DesiredState.ENABLED.value
                            if row[0]
                            else DesiredState.DISABLED.value
                        )
            except Exception:
                pass
        return self._states[plugin_id]["desired"]

    async def get_runtime_state(self, plugin_id: str) -> str:
        """Return the current runtime state."""
        self._ensure(plugin_id)
        return self._states[plugin_id]["runtime"]

    async def get_operation_state(self, plugin_id: str) -> str:
        """Return the current operation state."""
        self._ensure(plugin_id)
        return self._states[plugin_id]["operation"]

    async def get_state(self, plugin_id: str) -> dict[str, str]:
        """Return all three axes as a dict.

        Example::

            {"desired_state": "ENABLED", "runtime_state": "ACTIVE", "operation_state": "IDLE"}
        """
        return {
            "desired_state": await self.get_desired_state(plugin_id),
            "runtime_state": await self.get_runtime_state(plugin_id),
            "operation_state": await self.get_operation_state(plugin_id),
        }

    # ------------------------------------------------------------------
    # Desired-state transition (admin intent)
    # ------------------------------------------------------------------

    async def transition(
        self, plugin_id: str, desired_state: str, *, reason: str = ""
    ) -> bool:
        """Validate and apply a desired-state transition.

        This is the primary entry point for admin intent. It:

        1. Validates the transition against the current (desired, runtime,
           operation) triple.
        2. Updates in-memory state and persists to DB (inside a transaction).
        3. Returns ``True`` on success.
        4. Raises ``ValueError`` for invalid transitions.

        ERROR → ENABLED is the only valid transition from ERROR state and
        represents explicit admin re-activation (the sticky-ERROR rule).

        The engine is responsible for acting on the new desired state to
        trigger the corresponding runtime transitions (e.g. LOADING → ACTIVE
        or STOPPING → UNLOADED).
        """
        current = await self.get_state(plugin_id)
        curr_desired = current["desired_state"]
        curr_runtime = current["runtime_state"]
        curr_operation = current["operation_state"]

        new_desired = desired_state.upper()
        if new_desired not in (
            DesiredState.ENABLED.value,
            DesiredState.DISABLED.value,
        ):
            raise ValueError(f"Invalid desired state: {desired_state!r}")

        # Validate the transition (raises ValueError if invalid)
        self._validate_desired_transition(
            plugin_id, curr_desired, curr_runtime, curr_operation, new_desired
        )

        # No-op guard (after validation)
        if new_desired == curr_desired:
            return True

        db = self._db_conn()

        # -----------------------------------------------------------
        # ERROR → ENABLED  (admin re-activation)
        # -----------------------------------------------------------
        if curr_runtime == RuntimeState.ERROR.value:
            # Reaching here means new_desired == ENABLED (validation above)
            self._set_in_memory(
                plugin_id,
                DesiredState.ENABLED.value,
                RuntimeState.UNLOADED.value,
                OperationState.IDLE.value,
            )
            if db is not None:
                async with transaction(db) as tx_db:
                    await tx_db.execute(
                        "UPDATE plugins SET enabled = 1, status = 'UNLOADED' WHERE id = ?",
                        (plugin_id,),
                    )
            logger.info(
                "Plugin '%s' re-activated by admin: ERROR → ENABLED/UNLOADED%s",
                plugin_id,
                f" (reason: {reason})" if reason else "",
            )
            return True

        # -----------------------------------------------------------
        # Normal ENABLE
        # -----------------------------------------------------------
        if new_desired == DesiredState.ENABLED.value:
            if curr_runtime in (RuntimeState.UNLOADED.value, RuntimeState.LOADING.value):
                self._set_in_memory(
                    plugin_id,
                    DesiredState.ENABLED.value,
                    RuntimeState.LOADING.value,
                    curr_operation,
                )
                if db is not None:
                    async with transaction(db) as tx_db:
                        await tx_db.execute(
                            "UPDATE plugins SET enabled = 1, status = 'LOADING' WHERE id = ?",
                            (plugin_id,),
                        )
                logger.info(
                    "Plugin '%s' → desired=ENABLED, runtime=LOADING%s",
                    plugin_id,
                    f" (reason: {reason})" if reason else "",
                )
                return True

            if curr_runtime == RuntimeState.ACTIVE.value:
                self._set_in_memory(
                    plugin_id,
                    DesiredState.ENABLED.value,
                    RuntimeState.ACTIVE.value,
                    curr_operation,
                )
                if db is not None:
                    async with transaction(db) as tx_db:
                        await tx_db.execute(
                            "UPDATE plugins SET enabled = 1 WHERE id = ?",
                            (plugin_id,),
                        )
                return True

        # -----------------------------------------------------------
        # Normal DISABLE
        # -----------------------------------------------------------
        if new_desired == DesiredState.DISABLED.value:
            if curr_runtime in (RuntimeState.ACTIVE.value, RuntimeState.LOADING.value):
                self._set_in_memory(
                    plugin_id,
                    DesiredState.DISABLED.value,
                    RuntimeState.STOPPING.value,
                    curr_operation,
                )
                if db is not None:
                    async with transaction(db) as tx_db:
                        await tx_db.execute(
                            "UPDATE plugins SET enabled = 0, status = 'STOPPING' WHERE id = ?",
                            (plugin_id,),
                        )
                logger.info(
                    "Plugin '%s' → desired=DISABLED, runtime=STOPPING%s",
                    plugin_id,
                    f" (reason: {reason})" if reason else "",
                )
                return True

            if curr_runtime == RuntimeState.UNLOADED.value:
                self._set_in_memory(
                    plugin_id,
                    DesiredState.DISABLED.value,
                    RuntimeState.UNLOADED.value,
                    curr_operation,
                )
                if db is not None:
                    async with transaction(db) as tx_db:
                        await tx_db.execute(
                            "UPDATE plugins SET enabled = 0, status = 'DISABLED' WHERE id = ?",
                            (plugin_id,),
                        )
                return True

        # -----------------------------------------------------------
        # Unreachable guard
        # -----------------------------------------------------------
        raise ValueError(
            f"Invalid transition for plugin '{plugin_id}': "
            f"desired={curr_desired}→{new_desired}, "
            f"runtime={curr_runtime}, operation={curr_operation}"
        )

    # ------------------------------------------------------------------
    # Runtime state updates (engine-internal)
    # ------------------------------------------------------------------

    async def update_runtime_state(self, plugin_id: str, runtime_state: str) -> None:
        """Update the runtime axis (called by the engine).

        Validates against ``_VALID_RUNTIME_TRANSITIONS`` to ensure only
        legitimate runtime transitions are accepted. Silently ignores invalid
        transitions with a warning.
        """
        self._ensure(plugin_id)
        curr_runtime = self._states[plugin_id]["runtime"]
        allowed = _VALID_RUNTIME_TRANSITIONS.get(curr_runtime, set())
        if runtime_state not in allowed:
            logger.warning(
                "Ignored invalid runtime transition for '%s': %s → %s",
                plugin_id,
                curr_runtime,
                runtime_state,
            )
            return
        self._states[plugin_id]["runtime"] = runtime_state
        # Best-effort DB sync (non-critical, state is tracked in-memory)
        db = self._db_conn()
        if db is not None:
            try:
                await db.execute(
                    "UPDATE plugins SET status = ? WHERE id = ?",
                    (runtime_state, plugin_id),
                )
            except Exception:
                pass

    async def update_operation_state(
        self, plugin_id: str, operation_state: str
    ) -> None:
        """Update the operation axis (called by the engine)."""
        self._ensure(plugin_id)
        curr_op = self._states[plugin_id]["operation"]
        allowed = _VALID_OPERATION_TRANSITIONS.get(curr_op, set())
        if operation_state not in allowed:
            logger.warning(
                "Ignored invalid operation transition for '%s': %s → %s",
                plugin_id,
                curr_op,
                operation_state,
            )
            return
        self._states[plugin_id]["operation"] = operation_state

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    async def set_error(self, plugin_id: str, error_msg: str) -> None:
        """Transition the plugin to ERROR state.

        Side effects:
        - Runtime state → ERROR
        - Desired state → DISABLED (prevents auto-recovery)
        - Admin must explicitly call ``transition(plugin_id, "ENABLED")``
          to re-activate.
        - DB is updated inside a transaction.
        """
        self._ensure(plugin_id)
        self._set_in_memory(
            plugin_id,
            DesiredState.DISABLED.value,
            RuntimeState.ERROR.value,
            OperationState.IDLE.value,
        )
        db = self._db_conn()
        if db is not None:
            async with transaction(db) as tx_db:
                await tx_db.execute(
                    "UPDATE plugins SET enabled = 0, status = 'ERROR' WHERE id = ?",
                    (plugin_id,),
                )
        logger.error("Plugin '%s' → ERROR: %s", plugin_id, error_msg)

    # ------------------------------------------------------------------
    # Crash recovery
    # ------------------------------------------------------------------

    async def reconcile_after_crash(self) -> list[str]:
        """Reset plugins stuck in LOADING or STOPPING to DISABLED/UNLOADED.

        Called after an unexpected Master restart. Scans both in-memory state
        and the DB for plugins in transient runtime states and resets them to
        a safe baseline: desired=DISABLED, runtime=UNLOADED, operation=IDLE.

        Returns the list of reconciled plugin IDs.
        """
        reconciled: list[str] = []
        stuck = {RuntimeState.LOADING.value, RuntimeState.STOPPING.value}

        # Check in-memory tracked plugins
        for plugin_id, state in list(self._states.items()):
            if state["runtime"] in stuck:
                self._set_in_memory(
                    plugin_id,
                    DesiredState.DISABLED.value,
                    RuntimeState.UNLOADED.value,
                    OperationState.IDLE.value,
                )
                reconciled.append(plugin_id)

        # Check DB for stuck states not yet in memory
        db = self._db_conn()
        if db is not None:
            try:
                async with db.execute(
                    "SELECT id FROM plugins WHERE status IN ('LOADING', 'STOPPING')"
                ) as cursor:
                    rows = await cursor.fetchall()
                    for (row_id,) in rows:
                        if row_id not in self._states:
                            self._set_in_memory(
                                row_id,
                                DesiredState.DISABLED.value,
                                RuntimeState.UNLOADED.value,
                                OperationState.IDLE.value,
                            )
                            reconciled.append(row_id)

                if reconciled:
                    async with transaction(db) as tx_db:
                        for pid in reconciled:
                            await tx_db.execute(
                                "UPDATE plugins SET enabled = 0, status = 'DISABLED' WHERE id = ?",
                                (pid,),
                            )
            except Exception:
                logger.exception("Error reconciling plugins after crash")

        if reconciled:
            logger.info(
                "Reconciled %d plugin(s) after crash: %s",
                len(reconciled),
                reconciled,
            )
        return reconciled

    # ------------------------------------------------------------------
    # Engine-internal backward-compat helpers
    # ------------------------------------------------------------------

    def _set_runtime(self, plugin_id: str, runtime_state: str) -> None:
        """Synchronously update in-memory runtime state (engine-internal).

        No validation — the engine is trusted. Does NOT persist to DB.
        """
        self._ensure(plugin_id)
        self._states[plugin_id]["runtime"] = runtime_state

    def _remove(self, plugin_id: str) -> None:
        """Remove all tracked state for a plugin (engine-internal)."""
        self._states.pop(plugin_id, None)

    # ------------------------------------------------------------------
    # Backward compat: old-style flat state access
    # ------------------------------------------------------------------

    def get_flat_state(self, plugin_id: str) -> str | None:
        """Return the legacy flat runtime state string, or None if unknown.

        Used by scanner.py and other old code that expects the pre-v2 API.
        """
        if plugin_id in self._states:
            return self._states[plugin_id]["runtime"]
        return None

    def get_all_flat_states(self) -> dict[str, str]:
        """Return all tracked runtime states as a flat dict (legacy compat)."""
        return {
            pid: s["runtime"] for pid, s in self._states.items()
        }
