#!/usr/bin/env python3
"""
Vigile — Action Proposal Unit Tests
Tests the ActionProposal model and its status transitions.
"""
import json
import os
import sys
import time

import pathlib
PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent.parent)
sys.path.insert(0, PROJECT_ROOT)

PASS = "\033[92m\u2713\033[0m"
FAIL = "\033[91m\u2717\033[0m"
results = []

def check(name, condition, detail=""):
    icon = PASS if condition else FAIL
    print(f"  {icon} {name}" + (f" ({detail})" if detail else ""))
    results.append((name, condition))
    return condition

from master.core.action_proposal import ActionProposal


def test_proposal_creation():
    """ActionProposal can be created with defaults."""
    p = ActionProposal(node_id="n1", action="RESTART_CONTAINER",
                       params={"container_id": "web"}, reasoning="It is down")
    check("proposal: has id", bool(p.id))
    check("proposal: status is PENDING", p.status == "PENDING")
    check("proposal: risk default MEDIUM", p.risk_level == "MEDIUM")
    check("proposal: created_by default ai", p.created_by == "ai")
    check("proposal: no approved_by", p.approved_by is None)

test_proposal_creation()


def test_proposal_approve():
    """approve() transitions to APPROVED."""
    p = ActionProposal(node_id="n1", action="RESTART_CONTAINER")
    p.approve(user_id="user-1")
    check("proposal approve: status APPROVED", p.status == "APPROVED")
    check("proposal approve: approved_by set", p.approved_by == "user-1")

test_proposal_approve()


def test_proposal_reject():
    """reject() transitions to REJECTED."""
    p = ActionProposal(node_id="n1", action="RESTART_CONTAINER")
    p.reject(user_id="user-2", reason="not needed")
    check("proposal reject: status REJECTED", p.status == "REJECTED")
    check("proposal reject: rejected_by set", p.rejected_by == "user-2")
    check("proposal reject: reason set", p.rejection_reason == "not needed")

test_proposal_reject()


def test_proposal_complete_success():
    """complete(success=True) transitions to EXECUTED."""
    p = ActionProposal(node_id="n1", action="RESTART_CONTAINER")
    p.approve("user-1")
    p.complete(success=True, result_data={"output": "restarted"})
    check("proposal complete: status EXECUTED", p.status == "EXECUTED")
    check("proposal complete: executed_at set", p.executed_at is not None)
    check("proposal complete: result stored",
          p.result == {"output": "restarted"})

test_proposal_complete_success()


def test_proposal_complete_fail():
    """complete(success=False) transitions to FAILED."""
    p = ActionProposal(node_id="n1", action="RESTART_CONTAINER")
    p.approve("user-1")
    p.complete(success=False, result_data={"error": "timeout"})
    check("proposal fail: status FAILED", p.status == "FAILED")
    check("proposal fail: error stored",
          p.result == {"error": "timeout"})

test_proposal_complete_fail()


def test_proposal_invalid_transition():
    """Invalid transitions raise ValueError."""
    p = ActionProposal(node_id="n1", action="RESTART_CONTAINER")
    p.approve("user-1")
    try:
        p.approve("user-2")
        check("proposal double approve: no exception", False)
    except ValueError:
        check("proposal double approve: raises ValueError", True)

test_proposal_invalid_transition()


def test_proposal_approve_rejected():
    """Cannot approve a rejected proposal."""
    p = ActionProposal(node_id="n1", action="RESTART_CONTAINER")
    p.reject("user-1", "not needed")
    try:
        p.approve("user-2")
        check("proposal approve rejected: no exception", False)
    except ValueError:
        check("proposal approve rejected: raises ValueError", True)

test_proposal_approve_rejected()


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
    check("proposal db: has params_json",
          json.loads(db_data["params_json"]) == {"container_id": "web"})
    check("proposal db: has result_json",
          json.loads(db_data["result_json"]) == {"output": "ok"})
    restored = ActionProposal.from_db_row(db_data)
    check("proposal restore: id matches", restored.id == p.id)
    check("proposal restore: action matches", restored.action == p.action)
    check("proposal restore: params restored",
          restored.params == {"container_id": "web"})
    check("proposal restore: result restored",
          restored.result == {"output": "ok"})
    check("proposal restore: status EXECUTED", restored.status == "EXECUTED")
    check("proposal restore: approved_by", restored.approved_by == "admin")

test_proposal_to_db_roundtrip()


print("\n" + "=" * 60)
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
total = len(results)
print(f"Results: {passed}/{total} passed", end="")
if failed:
    print(f"  ({failed} FAILED)")
    for name, ok in results:
        if not ok:
            print(f"  {FAIL} {name}")
    sys.exit(1)
else:
    print(" \U0001f389")
