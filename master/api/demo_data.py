"""
Vigile — Demo Mode Mock Data

Volatile in-memory state for the 'demo' user.
All data lives in memory — no writes to SQLite.
Every mutation (proposals, chat sessions) is stored in dicts/lists here.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEMO_USER_ID = "demo-user"
DEMO_USERNAME = "guest"
DEMO_PASSWORD = "guest"

# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

_NOW = time.time()

DEMO_NODES: list[dict[str, Any]] = [
    {
        "id": "demo-node-01",
        "name": "prod-web-01",
        "hostname": "web-prod-01.cluster.internal",
        "machine_id": "abcdef1234567890abcdef1234567890",
        "arch": "x86_64",
        "os": "Ubuntu 24.04 LTS (Linux 6.8.0-31-generic)",
        "state": "CONNECTED",
        "online": True,
        "last_heartbeat": _NOW - 5,
        "enrolled_at": _NOW - 86400 * 30,
        "created_at": _NOW - 86400 * 30,
        "updated_at": _NOW - 100,
    },
    {
        "id": "demo-node-02",
        "name": "prod-db-01",
        "hostname": "db-prod-01.cluster.internal",
        "machine_id": "deadbeef1234567890abcdef12345678",
        "arch": "aarch64",
        "os": "Debian 12 (Linux 6.1.0-21-arm64)",
        "state": "CONNECTED",
        "online": True,
        "last_heartbeat": _NOW - 3,
        "enrolled_at": _NOW - 86400 * 60,
        "created_at": _NOW - 86400 * 60,
        "updated_at": _NOW - 50,
    },
    {
        "id": "demo-node-03",
        "name": "stg-api-01",
        "hostname": "api-staging-01.cluster.internal",
        "machine_id": "cafebabe1234567890abcdef12345679",
        "arch": "x86_64",
        "os": "Ubuntu 22.04 LTS (Linux 5.15.0-91-generic)",
        "state": "CONNECTED",
        "online": True,
        "last_heartbeat": _NOW - 12,
        "enrolled_at": _NOW - 86400 * 14,
        "created_at": _NOW - 86400 * 14,
        "updated_at": _NOW - 120,
    },
    {
        "id": "demo-node-04",
        "name": "dev-box-01",
        "hostname": "dev-01.cluster.internal",
        "machine_id": "f00dcafe1234567890abcdef12345680",
        "arch": "x86_64",
        "os": "Fedora 40 (Linux 6.9.3-200.fc40.x86_64)",
        "state": "CONNECTED",
        "online": True,
        "last_heartbeat": _NOW - 30,
        "enrolled_at": _NOW - 86400 * 7,
        "created_at": _NOW - 86400 * 7,
        "updated_at": _NOW - 200,
    },
    {
        "id": "demo-node-05",
        "name": "lost-monitoring-01",
        "hostname": "mon-01.cluster.internal",
        "machine_id": "baadf00d1234567890abcdef12345681",
        "arch": "x86_64",
        "os": "Ubuntu 22.04 LTS (Linux 5.15.0-107-generic)",
        "state": "LOST",
        "online": False,
        "last_heartbeat": _NOW - 10800,
        "enrolled_at": _NOW - 86400 * 90,
        "created_at": _NOW - 86400 * 90,
        "updated_at": _NOW - 10800,
    },
    {
        "id": "demo-node-06",
        "name": "stale-cache-01",
        "hostname": "cache-01.cluster.internal",
        "machine_id": "decafc0f1234567890abcdef12345682",
        "arch": "aarch64",
        "os": "Debian 12 (Linux 6.1.0-22-arm64)",
        "state": "STALE",
        "online": False,
        "last_heartbeat": _NOW - 7200,
        "enrolled_at": _NOW - 86400 * 45,
        "created_at": _NOW - 86400 * 45,
        "updated_at": _NOW - 7200,
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
    """Generate simulated time-series metrics for a demo node.

    Each node has a distinct "personality" so the dashboard feels alive.
    """
    now = time.time()

    # Node profiles — different workloads
    profiles = {
        "demo-node-01": {"cpu_base": 18, "mem_base": 0.35, "mem_scale": 0.30, "disk_base": 0.38, "disk_scale": 0.12, "cores": 8, "mem_gb": 16, "disk_gb": 500, "swap_gb": 2, "processes": 287},
        "demo-node-02": {"cpu_base": 12, "mem_base": 0.55, "mem_scale": 0.15, "disk_base": 0.42, "disk_scale": 0.08, "cores": 4, "mem_gb": 32, "disk_gb": 2000, "swap_gb": 4, "processes": 198},
        "demo-node-03": {"cpu_base": 8, "mem_base": 0.22, "mem_scale": 0.18, "disk_base": 0.15, "disk_scale": 0.10, "cores": 4, "mem_gb": 8, "disk_gb": 250, "swap_gb": 2, "processes": 145},
        "demo-node-04": {"cpu_base": 35, "mem_base": 0.45, "mem_scale": 0.35, "disk_base": 0.55, "disk_scale": 0.20, "cores": 16, "mem_gb": 64, "disk_gb": 1000, "swap_gb": 8, "processes": 412},
        "demo-node-05": {"cpu_base": 5, "mem_base": 0.10, "mem_scale": 0.05, "disk_base": 0.60, "disk_scale": 0.05, "cores": 2, "mem_gb": 4, "disk_gb": 120, "swap_gb": 1, "processes": 89},
        "demo-node-06": {"cpu_base": 3, "mem_base": 0.08, "mem_scale": 0.04, "disk_base": 0.30, "disk_scale": 0.05, "cores": 2, "mem_gb": 4, "disk_gb": 60, "swap_gb": 1, "processes": 67},
    }
    profile = profiles.get(node_id, profiles["demo-node-01"])

    snapshots: list[dict[str, Any]] = []
    for i in range(limit):
        t = now - i * 60
        # Sine wave around base CPU with occasional spike
        cycle = (i * 1.3) % 60
        spike = 40 if i % 7 == 3 and node_id in ("demo-node-01", "demo-node-04") else 0
        cpu = profile["cpu_base"] + (cycle * 0.5) % 30 + spike
        mem_gb = profile["mem_gb"]
        mem_total = mem_gb * 1024 ** 3
        mem_used = int(mem_total * (profile["mem_base"] + (cycle * 0.008) % profile["mem_scale"]))
        disk_gb = profile["disk_gb"]
        disk_total = disk_gb * 1024 ** 3
        disk_used = int(disk_total * (profile["disk_base"] + (cycle * 0.004) % profile["disk_scale"]))
        snapshots.append({
            "collected_at": t,
            "cpu_percent": round(cpu, 1),
            "cpu_load_1m": round(cpu * 0.8, 2),
            "cpu_load_5m": round(cpu * 0.6, 2),
            "cpu_load_15m": round(cpu * 0.4, 2),
            "cpu_cores": profile["cores"],
            "mem_total_bytes": mem_total,
            "mem_used_bytes": mem_used,
            "mem_percent": round(mem_used / mem_total * 100, 1),
            "swap_total_bytes": profile["swap_gb"] * 1024 ** 3,
            "swap_used_bytes": int(0.1 * profile["swap_gb"] * 1024 ** 3),
            "disk_total_bytes": disk_total,
            "disk_used_bytes": disk_used,
            "disk_percent": round(disk_used / disk_total * 100, 1),
            "uptime_seconds": 3600 * 24 * 14 + i * 60,
            "processes": profile["processes"] + i % 10,
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
    {"name": "prometheus.service", "state": "active", "status": "enabled"},
    {"name": "grafana-server.service", "state": "active", "status": "enabled"},
    {"name": "cron.service", "state": "active", "status": "enabled"},
    {"name": "rsyslog.service", "state": "active", "status": "enabled"},
    {"name": "netdata.service", "state": "inactive", "status": "disabled"},
    {"name": "systemd-journald.service", "state": "active", "status": "static"},
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
        "state": "running",
        "status": "Up 14 days",
        "ports": ["0.0.0.0:80->80/tcp", "0.0.0.0:443->443/tcp"],
        "created": _NOW - 86400 * 20,
        "node_id": "demo-node-01",
    },
    {
        "id": "b2c3d4e5f6a7",
        "name": "reverse-proxy",
        "image": "traefik:v3.0",
        "state": "running",
        "status": "Up 14 days",
        "ports": ["0.0.0.0:8080->80/tcp"],
        "created": _NOW - 86400 * 20,
        "node_id": "demo-node-01",
    },
    {
        "id": "c3d4e5f6a7b8",
        "name": "pg-replica",
        "image": "postgres:16",
        "state": "running",
        "status": "Up 10 days",
        "ports": [],
        "created": _NOW - 86400 * 10,
        "node_id": "demo-node-02",
    },
    {
        "id": "d4e5f6a7b8c9",
        "name": "redis-cache",
        "image": "redis:7-alpine",
        "state": "running",
        "status": "Up 15 days",
        "ports": [],
        "created": _NOW - 86400 * 15,
        "node_id": "demo-node-02",
    },
    {
        "id": "e5f6a7b8c9d0",
        "name": "plex-media",
        "image": "plexinc/pms-docker:latest",
        "state": "running",
        "status": "Up 42 days",
        "ports": ["0.0.0.0:32400->32400/tcp"],
        "created": _NOW - 86400 * 60,
        "node_id": "demo-node-03",
    },
    {
        "id": "f6a7b8c9d0e1",
        "name": "home-assistant",
        "image": "ghcr.io/home-assistant/home-assistant:stable",
        "state": "restarting",
        "status": "Restarting (1) 5 seconds ago",
        "ports": ["0.0.0.0:8123->8123/tcp"],
        "created": _NOW - 86400 * 30,
        "node_id": "demo-node-03",
    },
    {
        "id": "a7b8c9d0e1f2",
        "name": "grafana",
        "image": "grafana/grafana:10.4",
        "state": "exited",
        "status": "Exited (1) 2 hours ago",
        "ports": ["0.0.0.0:3000->3000/tcp"],
        "created": _NOW - 86400 * 5,
        "node_id": "demo-node-04",
    },
    {
        "id": "b8c9d0e1f2a3",
        "name": "radarr",
        "image": "lscr.io/linuxserver/radarr:latest",
        "state": "exited",
        "status": "Exited (0) 5 minutes ago",
        "ports": [],
        "created": _NOW - 86400 * 10,
        "node_id": "demo-node-04",
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
# Helpers
# ---------------------------------------------------------------------------

def _ts(offset_seconds: float) -> float:
    """Return a timestamp offset from now."""
    return _NOW - offset_seconds


def _compute_audit_hash(
    previous_hash: str,
    sequence: int,
    timestamp: float,
    action: str,
    user_id: str,
    node_id: str | None,
    details_json: str,
) -> str:
    """Compute a SHA256 entry hash matching the real audit chain formula."""
    raw = "|".join([
        previous_hash,
        str(sequence),
        f"{timestamp:.6f}",
        action,
        user_id,
        node_id or "",
        details_json,
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Action Proposals (mutable — in-memory)
# ---------------------------------------------------------------------------

def _initial_proposals() -> list[dict[str, Any]]:
    """Factory returning default proposal set."""
    return [
        # 0: PENDING LOW — web-app container memory
        {
            "id": str(uuid.uuid4()),
            "node_id": "demo-node-01",
            "action": "RESTART_CONTAINER",
            "params_json": '{"container_id": "web-app"}',
            "reasoning": "Utilisation élevée de la mémoire détectée sur le conteneur web-app (92% de 512 Mo). Redémarrer libérera de la mémoire et restaurera la réactivité.",
            "risk_level": "LOW",
            "status": "PENDING",
            "created_by": "ai",
            "created_at": _ts(300),
            "updated_at": _ts(300),
            "approved_by": None,
            "rejected_by": None,
            "rejection_reason": None,
            "executed_at": None,
            "result_json": None,
        },
        # 1: PENDING MEDIUM — PostgreSQL pool exhausted
        {
            "id": str(uuid.uuid4()),
            "node_id": "demo-node-02",
            "action": "RESTART_SERVICE",
            "params_json": '{"service": "postgresql.service"}',
            "reasoning": "Le pool de connexions PostgreSQL est épuisé (98/100 connexions). Un redémarrage est recommandé pour réinitialiser les connexions et récupérer les sockets perdus.",
            "risk_level": "MEDIUM",
            "status": "PENDING",
            "created_by": "ai",
            "created_at": _ts(600),
            "updated_at": _ts(600),
            "approved_by": None,
            "rejected_by": None,
            "rejection_reason": None,
            "executed_at": None,
            "result_json": None,
        },
        # 2: PENDING HIGH — lost node SSH restart
        {
            "id": str(uuid.uuid4()),
            "node_id": "demo-node-05",
            "action": "RESTART_SERVICE",
            "params_json": '{"service": "ssh.service"}',
            "reasoning": "Le nœud est injoignable depuis 3 heures. Tenter de redémarrer le service SSH peut restaurer la connectivité si le processus est bloqué.",
            "risk_level": "HIGH",
            "status": "PENDING",
            "created_by": "ai",
            "created_at": _ts(900),
            "updated_at": _ts(900),
            "approved_by": None,
            "rejected_by": None,
            "rejection_reason": None,
            "executed_at": None,
            "result_json": None,
        },
        # 3: APPROVED — Docker restart approved, pending execute
        {
            "id": str(uuid.uuid4()),
            "node_id": "demo-node-01",
            "action": "RESTART_SERVICE",
            "params_json": '{"service": "docker.service"}',
            "reasoning": "Le démon Docker ne répond pas aux appels API depuis 15 minutes. Redémarrer le service restaurera la gestion des conteneurs.",
            "risk_level": "MEDIUM",
            "status": "APPROVED",
            "created_by": "ai",
            "created_at": _ts(1800),
            "updated_at": _ts(1200),
            "approved_by": DEMO_USER_ID,
            "rejected_by": None,
            "rejection_reason": None,
            "executed_at": None,
            "result_json": None,
        },
        # 4: EXECUTED — reverse-proxy restart success
        {
            "id": str(uuid.uuid4()),
            "node_id": "demo-node-01",
            "action": "RESTART_CONTAINER",
            "params_json": '{"container_id": "reverse-proxy"}',
            "reasoning": "Traefik a signalé un échec de renouvellement de certificat TLS. Redémarrage du conteneur pour déclencher une nouvelle liaison ACME.",
            "risk_level": "LOW",
            "status": "EXECUTED",
            "created_by": "ai",
            "created_at": _ts(3600),
            "updated_at": _ts(3500),
            "approved_by": DEMO_USER_ID,
            "rejected_by": None,
            "rejection_reason": None,
            "executed_at": _ts(3400),
            "result_json": '{"success": true, "exit_code": 0, "output": "Conteneur reverse-proxy redémarré. Certificats TLS renouvelés avec succès.", "duration_ms": 2340}',
        },
        # 5: FAILED — nginx restart attempted but failed
        {
            "id": str(uuid.uuid4()),
            "node_id": "demo-node-01",
            "action": "RESTART_SERVICE",
            "params_json": '{"service": "nginx.service"}',
            "reasoning": "Nginx renvoie des erreurs 502 sur les routes /api/*. Redémarrage pour effacer les serveurs amonts obsolètes en cache.",
            "risk_level": "MEDIUM",
            "status": "FAILED",
            "created_by": "operator",
            "created_at": _ts(7200),
            "updated_at": _ts(7100),
            "approved_by": DEMO_USER_ID,
            "rejected_by": None,
            "rejection_reason": None,
            "executed_at": _ts(7000),
            "result_json": '{"success": false, "exit_code": 1, "error": "Le travail pour nginx.service a échoué car le processus de contrôle a quitté avec un code d\'erreur. Voir \\"systemctl status nginx.service\\" et \\"journalctl -xeu nginx.service\\" pour plus de détails.", "duration_ms": 5120}',
        },
        # 6: REJECTED — redis cache restart rejected
        {
            "id": str(uuid.uuid4()),
            "node_id": "demo-node-02",
            "action": "RESTART_CONTAINER",
            "params_json": '{"container_id": "redis-cache"}',
            "reasoning": "Le taux de hit du cache Redis est tombé à 62%. Un redémarrage peut améliorer les performances en libérant la mémoire fragmentée.",
            "risk_level": "LOW",
            "status": "REJECTED",
            "created_by": "ai",
            "created_at": _ts(4800),
            "updated_at": _ts(4700),
            "approved_by": None,
            "rejected_by": DEMO_USER_ID,
            "rejection_reason": "Un faible taux de hit de cache ne justifie pas un redémarrage. Envisagez d'augmenter maxmemory à la place.",
            "executed_at": None,
            "result_json": None,
        },
        # 7: PENDING MEDIUM — fail2ban restart proposal
        {
            "id": str(uuid.uuid4()),
            "node_id": "demo-node-04",
            "action": "RESTART_SERVICE",
            "params_json": '{"service": "fail2ban.service"}',
            "reasoning": "Plusieurs tentatives de force brute SSH détectées depuis la plage IP 203.0.113.0/24. Redémarrage de fail2ban pour s'assurer que les dernières règles de bannissement sont actives.",
            "risk_level": "MEDIUM",
            "status": "PENDING",
            "created_by": "ai",
            "created_at": _ts(200),
            "updated_at": _ts(200),
            "approved_by": None,
            "rejected_by": None,
            "rejection_reason": None,
            "executed_at": None,
            "result_json": None,
        },
        # 8: CRITICAL PENDING — Node-06 appears compromised
        {
            "id": str(uuid.uuid4()),
            "node_id": "demo-node-06",
            "action": "RESTART_CONTAINER",
            "params_json": '{"container_id": "home-assistant"}',
            "reasoning": "Le conteneur Home Assistant sur edge-01 consomme 4,2 Go de RAM (sur 4 Go alloués). Fuite de mémoire possible ou attaque par épuisement des ressources. Redémarrage immédiat recommandé.",
            "risk_level": "CRITICAL",
            "status": "PENDING",
            "created_by": "ai",
            "created_at": _ts(60),
            "updated_at": _ts(60),
            "approved_by": None,
            "rejected_by": None,
            "rejection_reason": None,
            "executed_at": None,
            "result_json": None,
        },
        # 9: REJECTED — prometheus restart
        {
            "id": str(uuid.uuid4()),
            "node_id": "demo-node-04",
            "action": "RESTART_SERVICE",
            "params_json": '{"service": "prometheus.service"}',
            "reasoning": "2 cibles Prometheus sur 12 sont injoignables. Redémarrer le service peut rafraîchir la découverte de cibles.",
            "risk_level": "LOW",
            "status": "REJECTED",
            "created_by": "ai",
            "created_at": _ts(5400),
            "updated_at": _ts(5300),
            "approved_by": None,
            "rejected_by": DEMO_USER_ID,
            "rejection_reason": "Seulement 2 cibles hors service est dans la tolérance. Lancez un cycle complet de découverte avant d'envisager un redémarrage.",
            "executed_at": None,
            "result_json": None,
        },
    ]


DEMO_PROPOSALS: list[dict[str, Any]] = _initial_proposals()


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

def _initial_chat_sessions() -> dict[str, dict[str, Any]]:
    """Factory returning default pre-seeded chat sessions."""
    return {
        "demo-session-en": {
            "id": "demo-session-en",
            "user_id": DEMO_USER_ID,
            "node_id": "demo-node-01",
            "title": "Analyse de performance",
            "history": [
                {"role": "user", "content": "Peux-tu analyser les performances du processeur (CPU) sur prod-web-01 ?"},
                {"role": "assistant", "content": "Voici mon analyse de **prod-web-01** (web-01.vigile.local) :\n\n**Processeur (CPU)** : Moyenne de 42.3% sur la dernière heure, avec un pic à 78% il y a 30 minutes. Ce pic est corrélé à une tâche de transcodage Plex.\n\n**Mémoire** : 7,2 Go / 16 Go utilisés (45%). Stable, aucune pression sur le swap.\n\n**Disque** : 210 Go / 500 Go utilisés (42%). Taux de croissance : +1,2 Go/jour — estimé à 242 jours avant saturation.\n\n**Conteneurs clés** sur ce nœud :\n- web-app (nginx) — actif, charge normale\n- reverse-proxy (traefik) — actif, certificats TLS OK\n- pg-replica — actif, délai de réplication 240ms\n- redis-cache — actif, taux de hit 94%\n\n**Recommandation** : Le pic de CPU est temporaire et reste dans les limites normales pour du transcodage Plex. Aucune action n'est requise."},
                {"role": "user", "content": "Et pour la croissance du disque, devrais-je m'inquiéter ?"},
                {"role": "assistant", "content": "Au rythme de croissance actuel de +1,2 Go/jour, vous disposez d'environ **242 jours** avant que le disque ne soit saturé.\n\nJe vous recommande de configurer une alerte de surveillance à 85% d'utilisation pour vous donner une marge de sécurité de 30 jours. La cause principale semble être les journaux applicatifs (logs) — vous devriez vérifier les paramètres de rotation des logs dans `/etc/logrotate.d/`.\n\nSouhaitez-vous que je propose une action de nettoyage de la rotation des logs ?"},
            ],
            "created_at": _ts(18000),
            "updated_at": _ts(1200),
        },
        "demo-session-status": {
            "id": "demo-session-status",
            "user_id": DEMO_USER_ID,
            "node_id": None,
            "title": "Vérification de l'état de la flotte",
            "history": [
                {"role": "user", "content": "Quel est l'état actuel de mes nœuds ?"},
                {"role": "assistant", "content": "Voici l'état actuel de votre flotte :\n\n• **prod-web-01** — ✅ Connecté | CPU: 42.3% | RAM: 7.2/16 Go\n• **prod-db-01** — ✅ Connecté | CPU: 18.7% | RAM: 18.5/32 Go\n• **stg-api-01** — ✅ Connecté | CPU: 12.1% | RAM: 2.1/8 Go\n• **dev-box-01** — ✅ Connecté | CPU: 68.4% | RAM: 31.2/64 Go\n• **lost-monitoring-01** — ⚠️ Perdu (dernier contact: il y a 3h)\n• **stale-cache-01** — ⚠️ Stale (heartbeat en retard)\n\n4 nœuds opérationnels sur 6. Les services critiques sont stables."},
                {"role": "user", "content": "Que s'est-il passé sur le nœud perdu ?"},
                {"role": "assistant", "content": "Le nœud **lost-monitoring-01** (mon-01.cluster.internal) n'a pas envoyé de heartbeat depuis environ 3 heures. Cela peut indiquer :\n\n1. **Panne réseau** — le lien entre le Worker et le Master est coupé\n2. **Crash OS** — le serveur a planté et n'a pas redémarré\n3. **Surcharge** — le processus Worker a été tué par OOM Killer\n\nJe vous suggère de vérifier le dernier heartbeat et d'envisager une action de diagnostic si le nœud redevient joignable."},
                {"role": "user", "content": "Garde un œil là-dessus et préviens-moi si ça change."},
                {"role": "assistant", "content": "Bien compris. Je surveille le nœud **lost-monitoring-01** et vous notifierai dès qu'un heartbeat est reçu ou qu'une action peut être prise. Vous pouvez aussi consulter la page d'audit pour voir l'historique complet des événements."},
            ],
            "created_at": _ts(86400),
            "updated_at": _ts(3600),
        },
        "demo-session-restart": {
            "id": "demo-session-restart",
            "user_id": DEMO_USER_ID,
            "node_id": "demo-node-01",
            "title": "Demande de redémarrage nginx",
            "history": [
                {"role": "user", "content": "Le serveur web semble lent, peux-tu redémarrer nginx ?"},
                {"role": "assistant", "content": "Je détecte effectivement une latence anormale sur nginx (temps de réponse moyen: 3.2s).\n\nAvant de redémarrer, je dois créer une proposition d'action pour validation humaine.\n\nVoici ce que je propose :\n\n**Action**: RESTART_SERVICE\n**Service**: nginx.service\n**Raison**: Latence élevée détectée, redémarrage pour réinitialiser les workers.\n**Risque**: MEDIUM\n\nVous pouvez approuver ou rejeter cette proposition depuis l'interface."},
                {"role": "user", "content": "D'accord, approuve-la."},
                {"role": "assistant", "content": "✅ Proposition créée et soumise pour approbation. Rendez-vous dans l'onglet **Propositions** pour valider l'action.\n\nUne fois approuvée, l'exécution prendra environ 2-3 secondes et nginx sera opérationnel immédiatement après."},
            ],
            "created_at": _ts(7200),
            "updated_at": _ts(3800),
        },
        "demo-session-security": {
            "id": "demo-session-security",
            "user_id": DEMO_USER_ID,
            "node_id": None,
            "title": "Rapport de sécurité",
            "history": [
                {"role": "user", "content": "Donne-moi un rapport de sécurité complet."},
                {"role": "assistant", "content": "## Rapport de sécurité — Vigile Demo\n\n### 🔒 Pare-feu\n• **UFW** — Actif | 3 règles actuellement chargées\n• Ports ouverts: 22, 80, 443, 8080\n\n### 🚨 Tentatives d'intrusion\n• **Dernière 24h**: 12 tentatives SSH bloquées (IP source: 203.0.113.42)\n• **fail2ban**: 3 IP bannies cette semaine\n\n### 🔑 Accès\n• Sessions actives: 2 (admin via web, guest en démo)\n• Clés SSH: Aucune clé compromise détectée\n\n### 📋 Recommandations\n1. Mettre à jour le noyau du nœud **stale-cache-01** (Debian 6.1.0-22)\n2. Activer le module de sécurité pour les conteneurs Docker\n3. Vérifier les logs d'authentification sur **lost-monitoring-01**"},
                {"role": "user", "content": "Y a-t-il des menaces actives ?"},
                {"role": "assistant", "content": "Aucune menace active détectée sur les nœuds connectés. Les tentatives SSH bloquées par fail2ban sont routinières (moyenne de 15-20 tentatives/jour, typique pour un serveur exposé).\n\nJe vous recommande néanmoins de vérifier l'état du nœud **lost-monitoring-01** dès qu'il refait surface — une absence prolongée peut indiquer un compromis silencieux."},
            ],
            "created_at": _ts(14400),
            "updated_at": _ts(4000),
        },
    }


DEMO_CHAT_SESSIONS: dict[str, dict[str, Any]] = _initial_chat_sessions()


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
# Audit entries  (30 entries spanning ~24h with real SHA256 hash chain)
# ---------------------------------------------------------------------------

_DEMO_GENESIS = "0" * 64

_DEMO_AUDIT_RAW: list[tuple[str, str | None, dict[str, Any]]] = [
    ("USER_LOGIN", None, {"username": "guest"}),
    ("LIST_NODES", None, {"filter": None}),
    ("GET_NODE_STATS", "demo-node-01", {"node_id": "demo-node-01"}),
    ("CHAT_MESSAGE", "demo-node-01", {"message_length": 42, "session_id": "demo-session-status"}),
    ("PROPOSAL_CREATED", "demo-node-01", {"action": "RESTART_CONTAINER", "target": "web-app", "risk": "LOW"}),
    ("PROPOSAL_APPROVED", "demo-node-01", {"proposal_id": None, "action": "RESTART_CONTAINER", "target": "web-app"}),
    ("GENERATE_JOIN_TOKEN", "demo-node-04", {"node_name": "cache-01"}),
    ("NODE_ENROLLED", "demo-node-04", {"hostname": "cache-01.vigile.local", "arch": "x86_64"}),
    ("LIST_SERVICES", "demo-node-01", {"node_id": "demo-node-01"}),
    ("RESTART_SERVICE", "demo-node-01", {"service": "nginx.service", "result": "success"}),
    ("LIST_CONTAINERS", "demo-node-04", {"node_id": "demo-node-04"}),
    ("CHAT_MESSAGE", "demo-node-01", {"message_length": 78, "session_id": "demo-session-restart"}),
    ("USER_LOGIN", None, {"username": "guest"}),
    ("LIST_NODES", None, {"filter": "prod"}),
    ("GET_NODE_STATS", "demo-node-02", {"node_id": "demo-node-02"}),
    ("PROPOSAL_CREATED", "demo-node-02", {"action": "RESTART_SERVICE", "target": "postgresql.service", "risk": "MEDIUM"}),
    ("PROPOSAL_APPROVED", "demo-node-02", {"proposal_id": None, "action": "RESTART_SERVICE", "target": "postgresql.service"}),
    ("RESTART_SERVICE", "demo-node-02", {"service": "postgresql.service", "result": "success"}),
    ("LIST_NODES", None, {"filter": None}),
    ("PROPOSAL_CREATED", "demo-node-05", {"action": "RESTART_SERVICE", "target": "ssh.service", "risk": "HIGH"}),
    ("PROPOSAL_REJECTED", "demo-node-05", {"proposal_id": None, "action": "RESTART_SERVICE", "target": "ssh.service", "reason": "Node is unreachable, cannot execute"}),
    ("CHAT_MESSAGE", None, {"message_length": 156, "session_id": "demo-session-security"}),
    ("READ_LOGS", "demo-node-01", {"service": "nginx", "lines": 50}),
    ("USER_LOGOUT", None, {"username": "guest"}),
    ("USER_LOGIN", None, {"username": "guest"}),
    ("PROPOSAL_CREATED", "demo-node-06", {"action": "RESTART_CONTAINER", "target": "home-assistant", "risk": "CRITICAL"}),
    ("LIST_SERVICES", "demo-node-04", {"node_id": "demo-node-04"}),
    ("CONTAINER_RESTART", "demo-node-04", {"container": "home-assistant", "result": "success"}),
    ("PROPOSAL_REJECTED", "demo-node-04", {"proposal_id": None, "action": "RESTART_SERVICE", "target": "nginx.service", "reason": "Within tolerance"}),
    ("SYSTEM_INIT", None, {"message": "Demo data initialized with 6 nodes, 15 services, 8 containers"}),
    ("STOP_CONTAINER", "demo-node-03", {"container": "plex-media", "reason": "Scheduled maintenance"}),
    ("UPDATE_CONFIG", "demo-node-04", {"setting": "nginx.workers", "old_value": "4", "new_value": "8"}),
    ("NODE_REVOKE", "demo-node-05", {"reason": "Node unreachable for 24+ hours", "previous_state": "LOST"}),
]

DEMO_AUDIT_ENTRIES: list[dict[str, Any]] = []
_seq = 1000
_prev = _DEMO_GENESIS
for i, (action, node_id, details) in enumerate(_DEMO_AUDIT_RAW):
    ts = _ts((len(_DEMO_AUDIT_RAW) - i) * 2880)  # spread over ~24h
    details_json = json.dumps(details, separators=(",", ":"), ensure_ascii=False)
    entry_hash = _compute_audit_hash(
        previous_hash=_prev,
        sequence=_seq,
        timestamp=ts,
        action=action,
        user_id=DEMO_USER_ID,
        node_id=node_id,
        details_json=details_json,
    )
    DEMO_AUDIT_ENTRIES.append({
        "id": str(uuid.uuid4()),
        "sequence": _seq,
        "timestamp": ts,
        "user_id": DEMO_USER_ID,
        "actor": DEMO_USERNAME,
        "action": action,
        "node_id": node_id,
        "details": details,
        "previous_hash": _prev,
        "entry_hash": entry_hash,
    })
    _prev = entry_hash
    _seq += 1


# ---------------------------------------------------------------------------
# Helper: is_demo_user
# ---------------------------------------------------------------------------

def is_demo(claims: dict[str, Any]) -> bool:
    return claims.get("username") in {"guest", "demo"}


# ---------------------------------------------------------------------------
# Simulated chat streaming
# ---------------------------------------------------------------------------

DEMO_RESPONSES = {
    "status": (
        "Voici l'état actuel de votre flotte de démonstration :\n\n"
        "**prod-web-01** — ✅ Connecté | CPU: 42.3% | RAM: 7.2/16 Go | Disk: 42% | Uptime: 14j\n"
        "**prod-db-01** — ✅ Connecté | CPU: 18.7% | RAM: 18.5/32 Go | Disk: 38% | Uptime: 60j\n"
        "**stg-api-01** — ✅ Connecté | CPU: 12.1% | RAM: 2.1/8 Go | Disk: 15% | Uptime: 14j\n"
        "**dev-box-01** — ✅ Connecté | CPU: 68.4% | RAM: 31.2/64 Go | Disk: 55% | Uptime: 7j\n"
        "**lost-monitoring-01** — ⚠️ Perdu | Dernier heartbeat: il y a 3h\n"
        "**stale-cache-01** — ⚠️ Stale | Heartbeat en retard\n\n"
        "4 nœuds opérationnels sur 6. Deux nœuds nécessitent une attention."
    ),
    "health": (
        "Rapport de santé de la flotte démo :\n\n"
        "• **nginx** — actif (uptime: 14j, requêtes/s: 142)\n"
        "• **postgresql** — actif (connexions: 12/100, taille DB: 2.4 Go)\n"
        "• **redis** — actif (hit rate: 94.2%, mémoire: 245 Mo/1 Go)\n"
        "• **docker** — actif (7 conteneurs, 5 en cours d'exécution)\n"
        "• **prometheus** — actif (cibles: 12/12 up)\n"
        "• **netdata** — désactivé\n\n"
        "Aucun problème critique détecté sur les nœuds connectés."
    ),
    "restart": (
        "J'ai détecté un besoin de redémarrage.\n\n"
        "Pour redémarrer un service ou un conteneur, je dois d'abord créer une proposition d'action qui nécessite votre approbation.\n\n"
        "Voici ce que je peux faire :\n"
        "1. **Redémarrer nginx** — pour réinitialiser les workers et libérer la mémoire\n"
        "2. **Redémarrer PostgreSQL** — pour réinitialiser le pool de connexions\n"
        "3. **Redémarrer un conteneur** — pour forcer un recycle\n\n"
        "Quelle action souhaitez-vous entreprendre ?"
    ),
    "security": (
        "## Rapport de sécurité — Vigile Demo\n\n"
        "### 🔒 Pare-feu\n"
        "- **UFW**: Actif — 3 règles chargées\n"
        "- Ports: 22 (SSH), 80 (HTTP), 443 (HTTPS), 8080 (Traefik)\n\n"
        "### 🚨 Événements récents\n"
        "- **12 tentatives SSH** bloquées par fail2ban (24h)\n"
        "- **3 IP bannies** cette semaine\n"
        "- **0** compromission détectée\n\n"
        "### 📋 Recommandations\n"
        "1. Mettre à jour le noyau des nœuds aarch64\n"
        "2. Activer le monitoring idle sur **stale-cache-01**\n"
        "3. Vérifier les logs système sur **lost-monitoring-01** dès reconnexion"
    ),
    "logs": (
        "Voici un résumé des journaux récents :\n\n"
        "**nginx** (10 dernières lignes):\n"
        "- 192.168.1.100 — GET /api/health → 200\n"
        "- 10.0.0.5 — GET / → 200\n"
        "- 10.0.0.6 — GET /api/chat → 401 (non authentifié)\n\n"
        "**PostgreSQL** (derniers événements):\n"
        "- Checkpoints réguliers toutes les 2 minutes\n"
        "- Durée moyenne des requêtes: 5-12 ms\n\n"
        "**Syslog**:\n"
        "- Connexion SSH admin depuis 192.168.1.100\n"
        "- Tentative SSH root bloquée depuis 203.0.113.42\n"
        "- Interface réseau eth0: 1000 Mbps full-duplex"
    ),
    "default": (
        "Bienvenue dans la session de démonstration Vigile !\n\n"
        "Vous pouvez explorer librement toutes les fonctionnalités :\n"
        "- **Nœuds** — 6 serveurs avec métriques en temps réel\n"
        "- **Services** — 15 services systemd (dont un désactivé)\n"
        "- **Conteneurs** — 8 conteneurs Docker répartis sur 4 nœuds\n"
        "- **Propositions** — 10 propositions avec différents statuts\n"
        "- **Audit** — 30 entrées avec chaîne de hachage complète\n"
        "- **Chat** — Sessions pré-générées avec historique réaliste\n\n"
        "Toutes les modifications sont volatiles et réinitialisées au redémarrage du serveur."
    ),
}


def get_demo_chat_tokens(message: str) -> list[str]:
    """Generate simulated response tokens for the demo chat."""
    msg_lower = message.lower()
    if "status" in msg_lower or "état" in msg_lower or "santé" in msg_lower:
        text = DEMO_RESPONSES["status"]
    elif "health" in msg_lower or "santé" in msg_lower:
        text = DEMO_RESPONSES["health"]
    elif "restart" in msg_lower or "redémarrer" in msg_lower or "redemarrer" in msg_lower:
        text = DEMO_RESPONSES["restart"]
    elif "sécurité" in msg_lower or "securite" in msg_lower or "security" in msg_lower:
        text = DEMO_RESPONSES["security"]
    elif "logs" in msg_lower or "journaux" in msg_lower:
        text = DEMO_RESPONSES["logs"]
    else:
        text = DEMO_RESPONSES["default"]
    return text.split(" ")


def get_demo_proposal_from_text(message: str) -> dict[str, Any] | None:
    """Try to create a demo action proposal based on user message keywords."""
    for p in DEMO_PROPOSALS:
        if p["status"] == "PENDING":
            return p
    return None


# ---------------------------------------------------------------------------
# State reset
# ---------------------------------------------------------------------------

def reset_demo_state() -> None:
    """Reset all mutable demo state to defaults."""
    DEMO_PROPOSALS.clear()
    DEMO_PROPOSALS.extend(_initial_proposals())
    DEMO_CHAT_SESSIONS.clear()
    DEMO_CHAT_SESSIONS.update(_initial_chat_sessions())
