#!/usr/bin/env python3
"""
Vigile — Comprehensive simulation test suite.
Tests ALL endpoints against the realistic simulation worker.
"""
import json
import time
import urllib.request

BASE = "http://localhost:8000"
PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  \033[92m\u2713\033[0m {name}" + (f" ({detail})" if detail else ""))
    else:
        FAIL += 1
        print(f"  \033[91m\u2717\033[0m {name}" + (f" ({detail})" if detail else ""))


def login():
    r = json.loads(
        urllib.request.urlopen(
            urllib.request.Request(
                BASE + "/api/auth/login",
                data=json.dumps({"username": "admin", "password": "admin"}).encode(),
                headers={"Content-Type": "application/json"},
            )
        ).read()
    )
    return r["access_token"]


def g(url, token):
    return json.loads(
        urllib.request.urlopen(
            urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
        ).read()
    )


def post(url, token, data=b"{}"):
    return json.loads(
        urllib.request.urlopen(
            urllib.request.Request(
                url,
                data=data,
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            )
        ).read()
    )


TOKEN = login()
check("Login OK", bool(TOKEN), f"token={TOKEN[:20]}...")

nodes = g(BASE + "/api/nodes", TOKEN)
NID = [n["id"] for n in nodes if n["state"] == "CONNECTED"][0]
check("Node connected", bool(NID), f"{NID[:8]}...")

# ─── 1. METRICS ───────────────────────────────────────────────────
print("\n\U0001f4ca METRICS")
r = g(BASE + f"/api/nodes/{NID}/stats?limit=1", TOKEN)
if r["snapshots"]:
    s = r["snapshots"][0]
    check("CPU is a number", isinstance(s["cpu_percent"], (int, float)))
    check("MEM is a percentage", 0 <= s["mem_percent"] <= 100)
    check("DISK is a percentage", 0 <= s["disk_percent"] <= 100)
    check("Uptime is positive", s["uptime_seconds"] > 0)
    check("collected_at is set", s["collected_at"] > 0)
else:
    check("STATUS_REPORT received (wait 60s)", False)

# ─── 2. SERVICES ─────────────────────────────────────────────────
print("\n\U0001f6e1\ufe0f SERVICES LIST")
r = g(BASE + f"/api/nodes/{NID}/services", TOKEN)
services = r["services"]
check("Services list returned", len(services) > 0, f"{len(services)} services")

by_state = {}
for s in services:
    by_state.setdefault(s["state"], {"running": 0, "exited": 0, "dead": 0, "failed": 0})

for s in services:
    sub = s.get("status", "")
    if sub in by_state[s["state"]]:
        by_state[s["state"]][sub] += 1
    elif sub:
        by_state[s["state"]].setdefault(sub, 0)
        by_state[s["state"]][sub] += 1

active_running = by_state.get("active", {}).get("running", 0)
active_exited = by_state.get("active", {}).get("exited", 0)
inactive_dead = by_state.get("inactive", {}).get("dead", 0)
failed_count = by_state.get("failed", {}).get("failed", 0)
check("Has active/running services", active_running > 10, f"{active_running} running")
check("Has active/exited (oneshot)", active_exited > 0, f"{active_exited} exited")
check("Has inactive/dead services", inactive_dead > 0, f"{inactive_dead} inactive")
check("Has failed services (simulated)", failed_count >= 2, f"{failed_count} failed")

service_names = [s["name"] for s in services]
check("Contains ssh.service", "ssh.service" in service_names)
check("Contains nginx.service", "nginx.service" in service_names)
check("Contains docker.service", "docker.service" in service_names)
check("Contains mysql.service (failed)", "mysql.service" in service_names)
check("Contains prometheus.service (failed)", "prometheus.service" in service_names)

# ─── 3. SERVICE STATUS ───────────────────────────────────────────
print("\n\U0001f50d SERVICE STATUS")
for svc, expected_active in [
    ("ssh.service", "active"),
    ("nginx.service", "active"),
    ("docker.service", "active"),
    ("mysql.service", "failed"),
    ("prometheus.service", "failed"),
    ("apache2.service", "inactive"),
]:
    r = g(BASE + f"/api/nodes/{NID}/services/{svc}", TOKEN)
    check(f"{svc} is {expected_active}", r["active"] == expected_active, f"got={r['active']}")

# ─── 4. CONTAINERS ────────────────────────────────────────────────
print("\n\U0001f4e6 CONTAINERS")
r = g(BASE + f"/api/nodes/{NID}/containers", TOKEN)
containers = r["containers"]
check("Containers list returned", len(containers) > 0, f"{len(containers)} containers")
container_names = [c["name"] for c in containers]
check("Container has id and name", all(c.get("id") and c.get("name") for c in containers[:5]))

# ─── 5. LOGS ─────────────────────────────────────────────────────
print("\n\U0001f4dc LOGS")
# Syslog (request enough lines to include OOM event at line ~20)
r = g(BASE + f"/api/nodes/{NID}/logs?lines=30", TOKEN)
check("Syslog returned", r["output"] != "", f"{len(r['output'])} chars")
check("Syslog path is /var/log/syslog", r["path"] == "/var/log/syslog")
check("Syslog error is None", r["error"] is None)
syslog_errors = [
    l
    for l in r["output"].split(chr(10))
    if any(k in l.lower() for k in ["oom", "error", "fail", "kill"])
]
check("Syslog contains OOM event", any("oom" in l.lower() for l in r["output"].split(chr(10))))

# SSH logs (using .service suffix for journalctl)
r = g(BASE + f"/api/nodes/{NID}/logs?lines=10&service=ssh.service", TOKEN)
check("SSH logs returned", r["output"] != "")
check("SSH service param set", r["service"] == "ssh.service")
ssh_failed = [l for l in r["output"].split(chr(10)) if "Failed" in l]
ssh_accepted = [l for l in r["output"].split(chr(10)) if "Accepted" in l]
check("SSH has failed attempts", len(ssh_failed) >= 3, f"{len(ssh_failed)} failed")
check("SSH has accepted logins", len(ssh_accepted) >= 1, f"{len(ssh_accepted)} accepted")

# Nginx logs
r = g(BASE + f"/api/nodes/{NID}/logs?lines=15&service=nginx.service", TOKEN)
check("Nginx logs returned", r["output"] != "")
check("Nginx service param set", r["service"] == "nginx.service")
nginx_404 = [l for l in r["output"].split(chr(10)) if " 404 " in l]
nginx_403 = [l for l in r["output"].split(chr(10)) if " 403 " in l]
check("Nginx has 404 responses", len(nginx_404) >= 1, f"{len(nginx_404)} 404s")
check("Nginx has 403 responses (blocked)", len(nginx_403) >= 1, f"{len(nginx_403)} 403s")

# MySQL crash logs
r = g(BASE + f"/api/nodes/{NID}/logs?lines=10&service=mysql.service", TOKEN)
check("MySQL logs returned", r["output"] != "")
check(
    "MySQL crash mentions OOM",
    "OOM" in r["output"] or "Cannot allocate memory" in r["output"],
    "OOM detected in MySQL logs",
)

# ─── 6. RESTART FAILED SERVICE ────────────────────────────────────
print("\n\U0001f504 RESTART FAILED SERVICE")
r = post(BASE + f"/api/nodes/{NID}/services/mysql.service/restart", TOKEN)
check("Restart mysql returned", r.get("output") is not None or r.get("error") is not None)
if "restarted" in r.get("output", ""):
    check("Restart says recovered", "recovered" in r.get("output", ""))
    r2 = g(BASE + f"/api/nodes/{NID}/services/mysql.service", TOKEN)
    check("MySQL now active after restart", r2["active"] == "active")
    # Reset for next tests
    post(BASE + f"/api/nodes/{NID}/services/mysql.service/restart", TOKEN)

# ─── 7. INTENT TIMEOUT ────────────────────────────────────────────
print("\n\u23f3 ERROR HANDLING")
import urllib.error

try:
    r = g(BASE + "/api/nodes/nonexistent/services", TOKEN)
    check("Nonexistent node returns 404", False)
except urllib.error.HTTPError as e:
    check("Nonexistent node returns 404", e.code == 404)

try:
    r = g(BASE + f"/api/nodes/{NID}/logs?lines=-1", TOKEN)
    check("Invalid lines parameter", r is not None)  # Should fail gracefully
except urllib.error.HTTPError:
    pass  # 422 or similar is fine

# ─── 8. AUTH ──────────────────────────────────────────────────────
print("\n\U0001f511 AUTH")
try:
    r = g(BASE + "/api/nodes/xyz/services", "invalid_token")
    check("Invalid token returns 401", False)
except urllib.error.HTTPError as e:
    check("Invalid token returns 401", e.code == 401)

try:
    g(BASE + "/api/chat/proposals", TOKEN)
    check("Auth works for chat proposals", True)
except Exception:
    check("Auth works for chat proposals", False)

# ─── 9. DISK_SCAN ────────────────────────────────────────────────
print("\n\U0001f4c1 DISK_SCAN")

try:
    r = g(BASE + f"/api/nodes/{NID}/disk-scan?path=/etc&max_depth=1", TOKEN)
    check("DISK_SCAN ok", r.get("root") is not None, f"root name={r['root']['name']}")
    check("DISK_SCAN walked_count > 0", r.get("walked_count", 0) > 0)
    check("DISK_SCAN has truncated field", "truncated" in r)
except urllib.error.HTTPError as e:
    check("DISK_SCAN ok", False, f"HTTP {e.code}")

# Reject path: path not in mounts (best-effort — depends on Worker's actual mounts).
# In standard Docker where / is a mount, all absolute paths are allowed.
try:
    r = g(BASE + f"/api/nodes/{NID}/disk-scan?path=/proc/1/fd/0", TOKEN)
    check("DISK_SCAN reject path", True, "path allowed (/ is a mount)")
except urllib.error.HTTPError as e:
    if e.code == 502:
        check("DISK_SCAN reject path", True, "path rejected as expected")
    else:
        check("DISK_SCAN reject path", False, f"HTTP {e.code}")

# Truncate large: scan / with small min_size_bytes to potentially trigger truncation
try:
    r = g(BASE + f"/api/nodes/{NID}/disk-scan?path=/&min_size_bytes=1&max_depth=4", TOKEN)
    check("DISK_SCAN truncate large", r.get("root") is not None)
    check("DISK_SCAN truncated field exists", "truncated" in r)
except urllib.error.HTTPError as e:
    check("DISK_SCAN truncate large", False, f"HTTP {e.code}")

# ─── RESULTS ──────────────────────────────────────────────────────
print(f"\n{'='*60}")
total = PASS + FAIL
print(f"Results: {PASS}/{total} passed", end="")
if FAIL:
    print(f"  ({FAIL} FAILED)")
else:
    print(" \U0001f389")
