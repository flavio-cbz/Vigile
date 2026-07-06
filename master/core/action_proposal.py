"""
Vigile — Action Proposal Model

Represents an action proposed by the AI, pending human approval.
The Human-in-the-Loop cycle:
  1. LLM proposes an action → status=PENDING
  2. Operator reviews → approves or rejects
  3. On approve → INTENT sent to Worker → status=EXECUTED or FAILED
  4. On reject → status=REJECTED
"""

import json
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field


class ActionProposal(BaseModel):
    """
    An action proposed by the AI, awaiting human approval.

    Stored in the action_proposals table. Status transitions:
      PENDING → APPROVED → EXECUTED | FAILED
      PENDING → REJECTED
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    node_id: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""
    risk_level: str = "MEDIUM"
    status: str = "PENDING"
    created_by: str = "ai"
    approved_by: str | None = None
    rejected_by: str | None = None
    rejection_reason: str | None = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    executed_at: float | None = None
    result: dict[str, Any] | None = None

    def approve(self, user_id: str) -> None:
        """Transition to APPROVED."""
        if self.status != "PENDING":
            raise ValueError(f"Cannot approve proposal in state {self.status}")
        self.status = "APPROVED"
        self.approved_by = user_id
        self.updated_at = time.time()

    def reject(self, user_id: str, reason: str = "") -> None:
        """Transition to REJECTED."""
        if self.status != "PENDING":
            raise ValueError(f"Cannot reject proposal in state {self.status}")
        self.status = "REJECTED"
        self.rejected_by = user_id
        self.rejection_reason = reason
        self.updated_at = time.time()

    def complete(self, success: bool, result_data: dict[str, Any]) -> None:
        """Mark as EXECUTED or FAILED after intent execution."""
        if self.status != "APPROVED":
            raise ValueError(f"Cannot complete proposal in state {self.status}")
        self.status = "EXECUTED" if success else "FAILED"
        self.executed_at = time.time()
        self.result = result_data
        self.updated_at = time.time()

    def to_db_dict(self) -> dict[str, Any]:
        """Serialize to a flat dict for DB insertion."""
        return {
            "id": self.id,
            "node_id": self.node_id,
            "action": self.action,
            "params_json": _json_dumps(self.params),
            "reasoning": self.reasoning,
            "risk_level": self.risk_level,
            "status": self.status,
            "created_by": self.created_by,
            "approved_by": self.approved_by,
            "rejected_by": self.rejected_by,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "executed_at": self.executed_at,
            "result_json": _json_dumps(self.result) if self.result else None,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "ActionProposal":
        """Deserialize from a DB row dict."""
        data = dict(row)
        data["params"] = _json_loads(data.pop("params_json", "{}"))
        data["result"] = _json_loads(data.pop("result_json", "null"))
        return cls(**data)


RISK_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

_VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"APPROVED", "REJECTED"},
    "APPROVED": {"EXECUTED", "FAILED"},
    "REJECTED": set(),
    "EXECUTED": set(),
    "FAILED": set(),
}


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"))


def _json_loads(s: str | None) -> Any:
    if s is None:
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None
