import json
import pytest
from master.core.action_proposal import ActionProposal


def test_proposal_creation():
    """ActionProposal can be created with defaults."""
    p = ActionProposal(node_id="n1", action="RESTART_CONTAINER",
                       params={"container_id": "web"}, reasoning="It is down")
    assert bool(p.id)
    assert p.status == "PENDING"
    assert p.risk_level == "MEDIUM"
    assert p.created_by == "ai"
    assert p.approved_by is None


def test_proposal_approve():
    """approve() transitions to APPROVED."""
    p = ActionProposal(node_id="n1", action="RESTART_CONTAINER")
    p.approve(user_id="user-1")
    assert p.status == "APPROVED"
    assert p.approved_by == "user-1"


def test_proposal_reject():
    """reject() transitions to REJECTED."""
    p = ActionProposal(node_id="n1", action="RESTART_CONTAINER")
    p.reject(user_id="user-2", reason="not needed")
    assert p.status == "REJECTED"
    assert p.rejected_by == "user-2"
    assert p.rejection_reason == "not needed"


def test_proposal_complete_success():
    """complete(success=True) transitions to EXECUTED."""
    p = ActionProposal(node_id="n1", action="RESTART_CONTAINER")
    p.approve("user-1")
    p.complete(success=True, result_data={"output": "restarted"})
    assert p.status == "EXECUTED"
    assert p.executed_at is not None
    assert p.result == {"output": "restarted"}


def test_proposal_complete_fail():
    """complete(success=False) transitions to FAILED."""
    p = ActionProposal(node_id="n1", action="RESTART_CONTAINER")
    p.approve("user-1")
    p.complete(success=False, result_data={"error": "timeout"})
    assert p.status == "FAILED"
    assert p.result == {"error": "timeout"}


def test_proposal_invalid_transition():
    """Invalid transitions raise ValueError."""
    p = ActionProposal(node_id="n1", action="RESTART_CONTAINER")
    p.approve("user-1")
    with pytest.raises(ValueError):
        p.approve("user-2")


def test_proposal_approve_rejected():
    """Cannot approve a rejected proposal."""
    p = ActionProposal(node_id="n1", action="RESTART_CONTAINER")
    p.reject("user-1", "not needed")
    with pytest.raises(ValueError):
        p.approve("user-2")


def test_proposal_to_db_roundtrip():
    """to_db_dict() and from_db_row() roundtrip preserves data."""
    p = ActionProposal(
        node_id="n1",
        action="RESTART_CONTAINER",
        params={"container_id": "web"},
        reasoning="It is down",
        risk_level="HIGH",
    )
    p.approve("admin")
    p.complete(success=True, result_data={"output": "ok"})
    db_data = p.to_db_dict()
    assert json.loads(db_data["params_json"]) == {"container_id": "web"}
    assert json.loads(db_data["result_json"]) == {"output": "ok"}
    restored = ActionProposal.from_db_row(db_data)
    assert restored.id == p.id
    assert restored.action == p.action
    assert restored.params == {"container_id": "web"}
    assert restored.result == {"output": "ok"}
    assert restored.status == "EXECUTED"
    assert restored.approved_by == "admin"
