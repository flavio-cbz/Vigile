from __future__ import annotations

"""
Vigile — Canonical Enum Definitions

Single source of truth for all enum-like constants used across the master codebase.
New code MUST import from here. Existing code SHOULD migrate to these definitions.

Conventions:
  - StrEnum when the value IS the canonical string (used in DB, API, or wire format).
  - IntEnum for numeric codes (WebSocket close codes).
  - Auto-generated values only when the string form is never serialised externally.
"""

from enum import Enum, IntEnum

try:
    from enum import StrEnum
except ImportError:
    class StrEnum(str, Enum):
        def __str__(self) -> str:
            return str(self.value)

# ---------------------------------------------------------------------------
# Node state machine
# ---------------------------------------------------------------------------


class NodeState(str, Enum):
    """Worker lifecycle states as stored in `nodes.state` column."""

    PENDING = "PENDING"
    ENROLLING = "ENROLLING"
    UNCONFIGURED = "UNCONFIGURED"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    LOST = "LOST"
    STALE = "STALE"
    DISABLED = "DISABLED"
    REVOKED = "REVOKED"  # Legacy — never written post-migration, kept for back-compat


# ---------------------------------------------------------------------------
# Worker action names (wire protocol between Master ↔ Worker)
# ---------------------------------------------------------------------------


class WorkerAction(StrEnum):
    """Actions the Master can send to a Worker via intent dispatch."""

    PING = "PING"
    GET_STATS = "GET_STATS"
    STATUS_REPORT = "STATUS_REPORT"
    LIST_SERVICES = "LIST_SERVICES"
    STATUS_SERVICE = "STATUS_SERVICE"
    RESTART_SERVICE = "RESTART_SERVICE"
    LIST_CONTAINERS = "LIST_CONTAINERS"
    RESTART_CONTAINER = "RESTART_CONTAINER"
    READ_LOGS = "READ_LOGS"
    READ_LOGS_SERVICE = "READ_LOGS_SERVICE"
    UPDATE_WORKER = "UPDATE_WORKER"
    DISK_SCAN = "DISK_SCAN"


# ---------------------------------------------------------------------------
# Proposal / action risk levels
# ---------------------------------------------------------------------------


class RiskLevel(StrEnum):
    """Risk classification for AI-proposed actions."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Proposal lifecycle status
# ---------------------------------------------------------------------------


class ProposalStatus(StrEnum):
    """State machine for ActionProposal lifecycle."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"

    @classmethod
    def valid_transitions(cls) -> dict[str, set[str]]:
        return {
            cls.PENDING.value: {cls.APPROVED.value, cls.REJECTED.value},
            cls.APPROVED.value: {cls.EXECUTED.value, cls.FAILED.value},
            cls.REJECTED.value: set(),
            cls.EXECUTED.value: set(),
            cls.FAILED.value: set(),
        }


# ---------------------------------------------------------------------------
# WebSocket close codes (Vigile-specific range 44xx)
# ---------------------------------------------------------------------------


class WebSocketCloseCode(IntEnum):
    """Vigile-specific WebSocket close codes sent by the Master."""

    SERVER_SHUTDOWN = 1001
    REPLACED_BY_NEW = 4400
    DELETED_BY_OPERATOR = 4403
    WSS_REQUIRED = 4426
    DISABLED_BY_OPERATOR = 4429
    SECURITY_COMPROMISE = 4433


# ---------------------------------------------------------------------------
# Plugin hook names (canonical registry for HookBus)
# ---------------------------------------------------------------------------


class HookName(StrEnum):
    """Lexicon of all known hook verbs used by the plugin engine.

    Add new hooks here when defining a new extension point.  HookBus.validate()
    warns on registration of unknown hook names.
    """

    ON_NODE_CONNECT = "on_node_connect"
    ON_NODE_DISCONNECT = "on_node_disconnect"
    ON_STATUS_REPORT = "on_status_report"
    ON_PROPOSE_ACTION = "on_propose_action"
    ON_METRICS = "on_metrics"
    ON_PLUGIN_LOAD = "on_plugin_load"
    ON_PLUGIN_UNLOAD = "on_plugin_unload"
    ON_SHUTDOWN = "on_shutdown"
    NORMALIZE_STATUS_REPORT = "normalize_status_report"
    GET_SUPPORTED_ACTIONS = "get_supported_actions"


# ---------------------------------------------------------------------------
# User role hierarchy
# ---------------------------------------------------------------------------


class UserRole(StrEnum):
    """RBAC roles sorted by privilege level."""

    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"

    @classmethod
    def hierarchy(cls) -> dict[str, int]:
        return {role.value: idx + 1 for idx, role in enumerate(cls)}
