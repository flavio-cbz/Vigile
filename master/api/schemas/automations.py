"""
Vigile — Automation API Schemas

Pydantic models for the automation rules and logs REST API.
"""

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Trigger configs
# ---------------------------------------------------------------------------

class MetricThresholdTrigger(BaseModel):
    """Trigger configuration for 'metric_threshold' type."""
    metric: Literal[
        "cpu_percent", "cpu_load_1m", "cpu_load_5m", "cpu_load_15m",
        "mem_percent", "disk_percent", "uptime_seconds", "processes",
        "mem_used_bytes", "disk_used_bytes",
    ]
    operator: Literal["gt", "lt", "gte", "lte", "eq"]
    threshold: float


class NodeStateTrigger(BaseModel):
    """Trigger configuration for 'node_state' type."""
    state: Literal["CONNECTED", "LOST", "STALE", "DISCONNECTED", "RECONNECTING"]


# ---------------------------------------------------------------------------
# Condition configs
# ---------------------------------------------------------------------------

class AlwaysCondition(BaseModel):
    type: Literal["always"] = "always"


class TimeWindowCondition(BaseModel):
    type: Literal["time_window"] = "time_window"
    window: str = Field(
        ...,
        description="Time window in HH:MM-HH:MM format (UTC)",
        examples=["08:00-20:00"],
    )

    @field_validator("window")
    @classmethod
    def validate_window(cls, v: str) -> str:
        parts = v.split("-")
        if len(parts) != 2:
            raise ValueError("window must be in HH:MM-HH:MM format")
        for part in parts:
            hm = part.strip().split(":")
            if len(hm) != 2 or not all(x.isdigit() for x in hm):
                raise ValueError(f"Invalid time part: {part!r}")
        return v


# ---------------------------------------------------------------------------
# Action configs
# ---------------------------------------------------------------------------

class SendIntentAction(BaseModel):
    type: Literal["send_intent"] = "send_intent"
    action: str = Field(..., description="Worker intent action name (e.g. RESTART_SERVICE)")
    params: dict[str, Any] = Field(default_factory=dict)


class CallWebhookAction(BaseModel):
    type: Literal["call_webhook"] = "call_webhook"
    url: str
    body_template: str = Field(
        default='{"node_id": "{node_id}", "trigger_data": {trigger_data}}',
        description="JSON body template. Supports {node_id} and {trigger_data} placeholders.",
    )
    headers: dict[str, str] = Field(default_factory=dict)


class LogMessageAction(BaseModel):
    type: Literal["log_message"] = "log_message"
    message: str


# ---------------------------------------------------------------------------
# Rule CRUD
# ---------------------------------------------------------------------------

class AutomationRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)
    trigger_type: Literal["metric_threshold", "node_state"]
    trigger_config: dict[str, Any] = Field(
        ...,
        description="Trigger configuration dict. See MetricThresholdTrigger / NodeStateTrigger schemas.",
    )
    conditions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of condition dicts. Empty list = always execute.",
    )
    actions: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="List of action dicts. At least one action is required.",
    )
    target_node_id: str | None = Field(
        default=None,
        description="Restrict this rule to a specific node UUID. NULL = all nodes.",
    )
    target_group: str | None = Field(
        default=None,
        description="Restrict this rule to nodes in this group. NULL = all groups.",
    )
    cooldown_seconds: int = Field(
        default=300,
        ge=0,
        le=86400,
        description="Minimum seconds between rule executions per node.",
    )


class AutomationRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    trigger_config: dict[str, Any] | None = None
    conditions: list[dict[str, Any]] | None = None
    actions: list[dict[str, Any]] | None = None
    target_node_id: str | None = None
    target_group: str | None = None
    cooldown_seconds: int | None = Field(default=None, ge=0, le=86400)


class AutomationRuleResponse(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool
    trigger_type: str
    trigger_config: dict[str, Any]
    conditions: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    target_node_id: str | None
    target_group: str | None
    cooldown_seconds: int
    created_by: str
    created_at: float
    updated_at: float
    # Computed field — injected at query time
    total_executions: int = 0
    last_triggered_at: float | None = None


class AutomationLogResponse(BaseModel):
    id: str
    rule_id: str
    node_id: str | None
    triggered_at: float
    status: str
    trigger_data: dict[str, Any]
    result: dict[str, Any]


class AutomationTestRequest(BaseModel):
    node_id: str = Field(..., description="Node UUID to use as target for the test trigger.")
