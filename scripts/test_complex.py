#!/usr/bin/env python3
"""
Vigile — Complex task testing for the Human-in-the-Loop chat.
Tests multi-step diagnosis, log analysis, and remediation proposals.
"""
import json
import time
import urllib.request

BASE = "http://localhost:8002"


def login():
    r = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/api/auth/login",
        data=json.dumps({"username": "admin", "password": "admin"}).encode(),
        headers={"Content-Type": "application/json"},
    )).read())
    return r["access_token"]


def get_node_id(token):
    r = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/api/nodes",
        headers={"Authorization": f"Bearer {token}"},
    )).read())
    for n in r:
        if n["state"] == "CONNECTED":
            return n["id"]
    return None


def chat(token, node_id, message):
    """Send a chat message and return the proposal_id if any."""
    print(f"\n>>> {message}")
    req = urllib.request.Request(
        f"{BASE}/api/chat",
        data=json.dumps({"message": message, "node_id": node_id}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    resp = urllib.request.urlopen(req, timeout=120)
    body = resp.read().decode()
    proposal_id = None
    for line in body.split("\n"):
        if not line.startswith("data: "):
            continue
        d = json.loads(line[6:])
        if d["type"] == "proposal":
            proposal_id = d["proposal_id"]
            print(f"  [PROPOSAL] {d['action']} risk={d['risk_level']}")
        elif d["type"] == "token":
            print(d["content"], end="", flush=True)
        elif d["type"] == "error":
            print(f"\n  [ERROR] {d.get('detail', '')}")
        elif d["type"] == "done":
            print("")
    return proposal_id


def approve(token, proposal_id):
    """Approve a proposal and return the result."""
    if not proposal_id:
        return None
    print(f"  Approving {proposal_id[:12]}...")
    try:
        a = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"{BASE}/api/chat/proposals/{proposal_id}/approve",
            data=b"{}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )).read())
        print(f"  Result: {a['status']}")
        if a.get("result_json"):
            print(f"  Output: {a['result_json'][:200]}")
        return a
    except urllib.error.HTTPError as e:
        print(f"  HTTP Error: {e.code} {e.reason}")
        body = e.read().decode()
        print(f"  Body: {body[:200]}")
        return None


def check_pending(token):
    """Check for any pending proposals."""
    r = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/api/chat/proposals",
        headers={"Authorization": f"Bearer {token}"},
    )).read())
    pending = [p for p in r if p["status"] == "PENDING"]
    return pending


def main():
    token = login()
    print("1. Login OK")

    node_id = get_node_id(token)
    if not node_id:
        print("ERROR: No connected node found")
        return
    print(f"2. Node: {node_id[:8]}...")

    # ── Test 1: Diagnose and act ────────────────────────────────────
    print("\n" + "=" * 70)
    print("TEST 1: Status check + restart proposal")
    print("=" * 70)

    pid = chat(token, node_id,
        "Check if nginx service is running. If it's active, "
        "propose to restart it for a config reload."
    )
    if pid:
        time.sleep(3)
        approve(token, pid)
    else:
        print("  (waiting for proposal detection...)")
        time.sleep(15)
        for p in check_pending(token):
            print(f"  Found pending: {p['action']}")
            approve(token, p["id"])

    # ── Test 2: Log analysis + action ───────────────────────────────
    print("\n" + "=" * 70)
    print("TEST 2: SSH log analysis + remediation")
    print("=" * 70)

    pid = chat(token, node_id,
        "Read the ssh service logs with journalctl. "
        "Check for any failed login attempts or suspicious activity. "
        "If you find failed attempts, propose a security action."
    )
    if pid:
        time.sleep(3)
        approve(token, pid)
    else:
        print("  (waiting for proposal detection...)")
        time.sleep(15)
        for p in check_pending(token):
            print(f"  Found pending: {p['action']}")
            approve(token, p["id"])

    # ── Test 3: Full server health check ────────────────────────────
    print("\n" + "=" * 70)
    print("TEST 3: Full server health check")
    print("=" * 70)

    pid = chat(token, node_id,
        "Give me a complete health check of my server: "
        "check CPU usage, memory, disk space, list critical services "
        "(ssh, nginx, docker, postgresql), and check recent syslog errors. "
        "Summarize everything in a clear report."
    )

    print("\n" + "=" * 70)
    print("ALL COMPLEX TESTS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
