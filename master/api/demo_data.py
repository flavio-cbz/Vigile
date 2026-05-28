"""
Vigile — Demo Mode Mock Data

Volatile in-memory state for the 'demo' user.
All data lives in memory — no writes to SQLite.
Every mutation (proposals, chat sessions) is stored in dicts/lists here.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEMO_USER_ID = "demo-user"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo"

# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

DEMO_NODES: list[dict[str, Any]] = [
    {
        "id": "demo-node-01",
        "name": "prod-web-01",
        "hostname": "web-01.example.com",
        "machine_id": "abcdef1234567890abcdef1234567890",
        "arch": "x86_64",
        "os": "Linux 6.2.0-26-generic",
        "state": "CONNECTED",
        "online": True,
        "last_heartbeat": time.time() - 5,
        "enrolled_at": time.time() - 86400 * 30,
        "created_at": time.time() - 86400 * 30,
        "updated_at": time.time() - 100,
    },
    {
        "id": "demo-node-02",
        "name": "prod-db-01",
        "hostname": "db-01.example.com",
        "machine_id": "deadbeef1234567890abcdef12345678",
        "arch": "aarch64",
        "os": "Linux 6.2.0-26-generic",
        "state": "CONNECTED",
        "online": True,
        "last_heartbeat": time.time() - 3,
        "enrolled_at": time.time() - 86400 * 14,
        "created_at": time.time() - 86400 * 14,
        "updated_at": time.time() - 50,
    },
    {
        "id": "demo-node-03",
        "name": "backup-srv-02",
        "hostname": "backup-02.example.com",
        "machine_id": "cafebabe1234567890abcdef12345679",
        "arch": "x86_64",
        "os": "Linux 5.15.0-91-generic",
        "state": "LOST",
        "online": False,
        "last_heartbeat": time.time() - 7200,
        "enrolled_at": time.time() - 86400 * 60,
        "created_at": time.time() - 86400 * 60,
        "updated_at": time.time() - 7200,
    },
]


def get_demo_node(node_id: str) -> dict[str, Any] | None:
    """Return a demo node by ID, or None."""
    for n in DEMO_NODES:
        if n["id"] == node_id:
            return dict(n)  # copy
    return None


# ---------------------------------------------------------------------------
# Metrics snapshots (dynamic — generated at call time)
# ---------------------------------------------------------------------------

def get_demo_metrics(node_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Generate simulated time-series metrics for a demo node."""
    now = time.time()
    snapshots: list[dict[str, Any]] = []
    for i in range(limit):
        t = now - i * 60
        cpu = 25.0 + (i * 2.3) % 60
        mem_total = 16 * 1024 ** 3
        mem_used = int(mem_total * (0.35 + (i * 0.05) % 0.4))
        disk_total = 500 * 1024 ** 3
        disk_used = int(disk_total * (0.38 + (i * 0.03) % 0.15))
        snapshots.append({
            "collected_at": t,
            "cpu_percent": round(cpu, 1),
            "cpu_load_1m": round(cpu * 0.8, 2),
            "cpu_load_5m": round(cpu * 0.6, 2),
            "cpu_load_15m": round(cpu * 0.4, 2),
            "cpu_cores": 8,
            "mem_total_bytes": mem_total,
            "mem_used_bytes": mem_used,
            "mem_percent": round(mem_used / mem_total * 100, 1),
            "swap_total_bytes": 2 * 1024 ** 3,
            "swap_used_bytes": int(0.1 * 2 * 1024 ** 3),
            "disk_total_bytes": disk_total,
            "disk_used_bytes": disk_used,
            "disk_percent": round(disk_used / disk_total * 100, 1),
            "uptime_seconds": 3600 * 24 * 14 + i * 60,
            "processes": 287 + i % 10,
        })
    return snapshots


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

DEMO_SERVICES: list[dict[str, str]] = [
    {"name": "ssh.service", "state": "active", "status": "enabled"},
    {"name": "nginx.service", "state": "active", "status": "enabled"},
    {"name": "gunicorn.service", "state": "active", "status": "enabled"},
    {"name": "postgresql.service", "state": "active", "status": "enabled"},
    {"name": "redis.service", "state": "active", "status": "enabled"},
    {"name": "fail2ban.service", "state": "active", "status": "enabled"},
    {"name": "ufw.service", "state": "active", "status": "enabled"},
    {"name": "certbot.timer", "state": "active", "status": "enabled"},
    {"name": "docker.service", "state": "active", "status": "enabled"},
]


def get_demo_service(service_name: str) -> dict[str, str] | None:
    """Return a demo service by name, or None."""
    for s in DEMO_SERVICES:
        if s["name"] == service_name:
            return dict(s)
    return None


# ---------------------------------------------------------------------------
# Docker containers
# ---------------------------------------------------------------------------

DEMO_CONTAINERS: list[dict[str, Any]] = [
    {
        "id": "a1b2c3d4e5f6",
        "name": "web-app",
        "image": "nginx:1.25",
        "status": "running",
        "ports": ["0.0.0.0:80->80/tcp", "0.0.0.0:443->443/tcp"],
        "created": time.time() - 86400 * 20,
        "uptime": "14 days",
    },
    {
        "id": "b2c3d4e5f6a7",
        "name": "reverse-proxy",
        "image": "traefik:v3.0",
        "status": "running",
        "ports": ["0.0.0.0:8080->80/tcp"],
        "created": time.time() - 86400 * 20,
        "uptime": "14 days",
    },
    {
        "id": "c3d4e5f6a7b8",
        "name": "pg-replica",
        "image": "postgres:16",
        "status": "running",
        "ports": [],
        "created": time.time() - 86400 * 10,
        "uptime": "10 days",
    },
    {
        "id": "d4e5f6a7b8c9",
        "name": "redis-cache",
        "image": "redis:7-alpine",
        "status": "running",
        "ports": [],
        "created": time.time() - 86400 * 15,
        "uptime": "15 days",
    },
]


def get_demo_container(container_id: str) -> dict[str, Any] | None:
    """Return a demo container by ID or name, or None."""
    for c in DEMO_CONTAINERS:
        if c["id"] == container_id or c["name"] == container_id:
            return dict(c)
    return None


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

_NGINX_LOGS = [
    '192.168.1.100 - - [23/May/2026:10:15:23 +0200] "GET /api/health HTTP/1.1" 200 72 "-" "curl/8.4.0"',
    '192.168.1.101 - admin [23/May/2026:10:14:55 +0200] "POST /api/auth/login HTTP/1.1" 200 412 "-" "Mozilla/5.0"',
    '10.0.0.5 - - [23/May/2026:10:14:30 +0200] "GET / HTTP/1.1" 200 1234 "-" "Mozilla/5.0"',
    '192.168.1.100 - - [23/May/2026:10:13:12 +0200] "GET /api/nodes HTTP/1.1" 200 1024 "-" "python-requests/2.31"',
    '10.0.0.6 - - [23/May/2026:10:12:45 +0200] "GET /api/chat HTTP/1.1" 401 57 "-" "curl/8.4.0"',
    '192.168.1.102 - admin [23/May/2026:10:11:30 +0200] "POST /api/chat HTTP/1.1" 200 5678 "-" "Mozilla/5.0"',
    '192.168.1.100 - - [23/May/2026:10:10:22 +0200] "GET /api/nodes/demo-node-01/stats HTTP/1.1" 200 890 "-" "python-requests/2.31"',
    '10.0.0.7 - - [23/May/2026:10:09:15 +0200] "POST /api/auth/refresh HTTP/1.1" 200 412 "-" "Mozilla/5.0"',
    '192.168.1.103 - - [23/May/2026:10:08:00 +0200] "DELETE /api/nodes/demo-node-03 HTTP/1.1" 204 0 "-" "curl/8.4.0"',
    '192.168.1.100 - - [23/May/2026:10:07:30 +0200] "GET /api/audit HTTP/1.1" 200 2048 "-" "python-requests/2.31"',
]

_POSTGRES_LOGS = [
    "2026-05-23 10:15:00 UTC LOG: checkpoint starting: time",
    "2026-05-23 10:14:30 UTC LOG: checkpoint complete: wrote 42 buffers (0.3%); 0 WAL file(s) added, 0 removed",
    "2026-05-23 10:12:00 UTC LOG: checkpoint starting: time",
    "2026-05-23 10:11:30 UTC LOG: checkpoint complete: wrote 38 buffers (0.2%); 0 WAL file(s) added, 0 removed",
    "2026-05-23 10:10:00 UTC LOG: checkpoint starting: time",
    "2026-05-23 10:09:30 UTC LOG: checkpoint complete: wrote 45 buffers (0.3%); 0 WAL file(s) added, 0 removed",
    "2026-05-23 10:08:00 UTC LOG: duration: 12.345 ms statement: SELECT * FROM users WHERE id = $1",
    "2026-05-23 10:07:00 UTC LOG: duration: 5.678 ms statement: INSERT INTO audit_log (...) VALUES (...)",
    "2026-05-23 10:06:00 UTC LOG: checkpoint starting: time",
]

_SYSLOG = [
    "May 23 10:15:00 web-01 systemd[1]: Started Session 482 of user admin.",
    "May 23 10:14:55 web-01 sshd[12345]: Accepted publickey for admin from 192.168.1.100 port 54321",
    "May 23 10:14:30 web-01 kernel: [UFW BLOCK] IN=eth0 OUT= MAC=... SRC=45.33.32.156 DST=... PROTO=TCP DPT=22",
    "May 23 10:13:00 web-01 cron[9876]: (root) CMD (cd / && run-parts --report /etc/cron.hourly)",
    "May 23 10:12:00 web-01 systemd[1]: Starting system activity accounting tool...",
    "May 23 10:11:30 web-01 rsyslogd[789]: [origin software=\"rsyslogd\" swVersion=\"8.2312.0\" x-pid=\"789\"] start",
    "May 23 10:10:00 web-01 kernel: eth0: link up, 1000 Mbps full-duplex",
    "May 23 10:09:00 web-01 sshd[12345]: Failed password for root from 203.0.113.42 port 22 ssh2",
    "May 23 10:08:00 web-01 systemd[1]: Stopped Session 481 of user admin.",
]


def get_demo_logs(
    service: str | None = None,
    path: str | None = None,
    lines: int = 50,
) -> list[str]:
    """Return simulated log lines for a given service or file."""
    if service == "nginx":
        logs = _NGINX_LOGS
    elif service == "postgresql":
        logs = _POSTGRES_LOGS
    elif path and "syslog" in path:
        logs = _SYSLOG
    else:
        logs = _SYSLOG
    return logs[: min(lines, len(logs))]


# ---------------------------------------------------------------------------
# Action Proposals (mutable — in-memory)
# ---------------------------------------------------------------------------

DEMO_PROPOSALS: list[dict[str, Any]] = [
    {
        "id": str(uuid.uuid4()),
        "node_id": "demo-node-01",
        "action": "RESTART_CONTAINER",
        "params_json": '{"container_id": "web-app"}',
        "reasoning": "High memory usage detected on web-app container. Restarting will free memory and restore responsiveness.",
        "risk_level": "LOW",
        "status": "PENDING",
        "created_by": "ai",
        "created_at": time.time() - 300,
        "updated_at": time.time() - 300,
        "approved_by": None,
        "rejected_by": None,
        "rejection_reason": None,
        "executed_at": None,
        "result_json": None,
    },
    {
        "id": str(uuid.uuid4()),
        "node_id": "demo-node-02",
        "action": "RESTART_SERVICE",
        "params_json": '{"service": "postgresql.service"}',
        "reasoning": "PostgreSQL connection pool is exhausted. Restart is recommended to reset connections.",
        "risk_level": "MEDIUM",
        "status": "PENDING",
        "created_by": "ai",
        "created_at": time.time() - 600,
        "updated_at": time.time() - 600,
        "approved_by": None,
        "rejected_by": None,
        "rejection_reason": None,
        "executed_at": None,
        "result_json": None,
    },
    {
        "id": str(uuid.uuid4()),
        "node_id": "demo-node-03",
        "action": "RESTART_SERVICE",
        "params_json": '{"service": "ssh.service"}',
        "reasoning": "Backup node has been unreachable for 2 hours. Restarting SSH service to restore connectivity.",
        "risk_level": "HIGH",
        "status": "PENDING",
        "created_by": "ai",
        "created_at": time.time() - 900,
        "updated_at": time.time() - 900,
        "approved_by": None,
        "rejected_by": None,
        "rejection_reason": None,
        "executed_at": None,
        "result_json": None,
    },
]


def get_demo_proposal(proposal_id: str) -> dict[str, Any] | None:
    """Return a demo proposal by ID, or None."""
    for p in DEMO_PROPOSALS:
        if p["id"] == proposal_id:
            return p
    return None


def update_demo_proposal(proposal_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Update fields on a demo proposal in-place."""
    for p in DEMO_PROPOSALS:
        if p["id"] == proposal_id:
            p.update(updates)
            p["updated_at"] = time.time()
            return p
    return None


# ---------------------------------------------------------------------------
# Chat Sessions (mutable — in-memory)
# ---------------------------------------------------------------------------

DEMO_CHAT_SESSIONS: dict[str, dict[str, Any]] = {}


def get_demo_chat_sessions(user_id: str = DEMO_USER_ID) -> list[dict[str, Any]]:
    """Return all demo chat sessions for a user."""
    return [
        {**s, "history": s.get("history", [])}
        for s in DEMO_CHAT_SESSIONS.values()
        if s.get("user_id") == user_id
    ]


def get_demo_chat_session(session_id: str) -> dict[str, Any] | None:
    """Return a single demo chat session, or None."""
    s = DEMO_CHAT_SESSIONS.get(session_id)
    if s:
        return {**s, "history": s.get("history", [])}
    return None


def save_demo_chat_session(
    session_id: str,
    user_id: str = DEMO_USER_ID,
    node_id: str | None = None,
    title: str = "Demo Chat Session",
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create or update a demo chat session in-memory."""
    now = time.time()
    if session_id in DEMO_CHAT_SESSIONS:
        existing = DEMO_CHAT_SESSIONS[session_id]
        existing["node_id"] = node_id
        existing["title"] = title
        if history is not None:
            existing["history"] = history
        existing["updated_at"] = now
        return {**existing, "history": existing.get("history", [])}
    else:
        session = {
            "id": session_id,
            "user_id": user_id,
            "node_id": node_id,
            "title": title,
            "history": history or [],
            "created_at": now,
            "updated_at": now,
        }
        DEMO_CHAT_SESSIONS[session_id] = session
        return {**session, "history": session.get("history", [])}


def delete_demo_chat_session(session_id: str) -> bool:
    """Delete a demo chat session. Returns True if deleted."""
    return DEMO_CHAT_SESSIONS.pop(session_id, None) is not None


# ---------------------------------------------------------------------------
# Audit entries
# ---------------------------------------------------------------------------

DEMO_AUDIT_ENTRIES: list[dict[str, Any]] = [
    {
        "id": str(uuid.uuid4()),
        "sequence": 1001,
        "timestamp": time.time() - 3600,
        "user_id": DEMO_USER_ID,
        "action": "USER_LOGIN",
        "node_id": None,
        "details": {"username": "demo"},
        "previous_hash": "0" * 64,
        "entry_hash": "a" * 64,
    },
    {
        "id": str(uuid.uuid4()),
        "sequence": 1002,
        "timestamp": time.time() - 3500,
        "user_id": DEMO_USER_ID,
        "action": "LIST_NODES",
        "node_id": None,
        "details": {"filter": None},
        "previous_hash": "a" * 64,
        "entry_hash": "b" * 64,
    },
    {
        "id": str(uuid.uuid4()),
        "sequence": 1003,
        "timestamp": time.time() - 3000,
        "user_id": DEMO_USER_ID,
        "action": "GET_NODE_STATS",
        "node_id": "demo-node-01",
        "details": {"node_id": "demo-node-01"},
        "previous_hash": "b" * 64,
        "entry_hash": "c" * 64,
    },
    {
        "id": str(uuid.uuid4()),
        "sequence": 1004,
        "timestamp": time.time() - 2400,
        "user_id": DEMO_USER_ID,
        "action": "PROPOSAL_APPROVED",
        "node_id": "demo-node-01",
        "details": {
            "proposal_id": "demo-proposal-01",
            "action": "RESTART_CONTAINER",
            "status": "EXECUTED",
        },
        "previous_hash": "c" * 64,
        "entry_hash": "d" * 64,
    },
    {
        "id": str(uuid.uuid4()),
        "sequence": 1005,
        "timestamp": time.time() - 1800,
        "user_id": DEMO_USER_ID,
        "action": "CHAT_MESSAGE",
        "node_id": "demo-node-01",
        "details": {"message_length": 42},
        "previous_hash": "d" * 64,
        "entry_hash": "e" * 64,
    },
]


# ---------------------------------------------------------------------------
# Helper: is_demo_user
# ---------------------------------------------------------------------------

def is_demo(claims: dict[str, Any]) -> bool:
    """Check if the authenticated user is the demo user."""
    return claims.get("username") == DEMO_USERNAME


# ---------------------------------------------------------------------------
# Simulated chat streaming
# ---------------------------------------------------------------------------

DEMO_RESPONSES = {
    "status": (
        "Voici l'état actuel de votre flotte de démonstration :\n\n"
        "**prod-web-01** — ✅ Connecté | CPU: 32.4% | RAM: 5.6/16 Go | Disk: 42% | Uptime: 14j\n"
        "**prod-db-01** — ✅ Connecté | CPU: 18.7% | RAM: 8.2/16 Go | Disk: 38% | Uptime: 14j\n"
        "**backup-srv-02** — ⚠️ Perdu | Dernier heartbeat: il y a 2h\n\n"
        "Tous les services principaux sont opérationnels. Le nœud de backup nécessite une attention."
    ),
    "health": (
        "Rapport de santé de la flotte démo :\n\n"
        "• **nginx** — actif (uptime: 14j)\n"
        "• **postgresql** — actif (connexions: 12/100)\n"
        "• **redis** — actif (hit rate: 94.2%)\n"
        "• **docker** — actif (4 conteneurs en cours d'exécution)\n\n"
        "Aucun problème critique détecté sur les nœuds connectés."
    ),
    "default": (
        "Bienvenue dans la session de démonstration Vigile !\n\n"
        "Vous pouvez explorer librement toutes les fonctionnalités :\n"
        "- Consultez les nœuds et leurs métriques en temps réel\n"
        "- Parcourez les services systemd et conteneurs Docker\n"
        "- Approuvez ou rejetez des propositions d'action\n"
        "- Consultez le journal d'audit infalsifiable\n\n"
        "Toutes les modifications sont volatiles et réinitialisées à chaque connexion."
    ),
}


def get_demo_chat_tokens(message: str) -> list[str]:
    """Generate simulated response tokens for the demo chat."""
    msg_lower = message.lower()
    if "status" in msg_lower or "état" in msg_lower or "santé" in msg_lower:
        text = DEMO_RESPONSES["status"]
    elif "health" in msg_lower or "santé" in msg_lower:
        text = DEMO_RESPONSES["health"]
    else:
        text = DEMO_RESPONSES["default"]
    return text.split(" ")


def get_demo_proposal_from_text(message: str) -> dict[str, Any] | None:
    """Try to create a demo action proposal based on user message keywords."""
    msg_lower = message.lower()
    for p in DEMO_PROPOSALS:
        if p["status"] == "PENDING":
            return p
    return None
