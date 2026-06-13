# Vigile — Coding Standards

Strict rules for code quality, dependency injection, typing, and testing.
**These rules are non-negotiable.** Apply them to every line of code written.

---

## 0. GENERAL PHILOSOPHY

**Quality over speed.** Always. If a task can be done in 10 minutes with any doubt (99.9% confidence) or in 3 days with absolute certainty (100%), we take the 3 days without hesitation. There is no rush. The code must be indisputable, tested, decoupled, and documented. No "we'll see later".

---

## 1. DEPENDENCY INJECTION (THE FUNDAMENTAL RULE)

**A core layer class NEVER reads `settings.XXX`, `os.getenv`, or the filesystem. It receives everything in its constructor.**

```python
# ✅ Acceptable
RateLimiter(max_requests=60, window_seconds=60)

# ❌ Forbidden — the constructor retrieves its configuration on its own
SecurityManager()  # reads settings.server_secret_key, settings.jwt_secret, file I/O
```

**Filesystem I/O belongs to the edge** (`main.py`, lifespan, `deps.py`).
Core classes receive already loaded objects. For example, an already parsed `Ed25519PrivateKey`, not a file path to read.

---

## 2. SINGLETONS

**A core singleton is created at import time ONLY if its constructor is lightweight: 0 parameters, 0 I/O, 0 side effects.**

```python
# ✅ Acceptable — empty constructor, no side effects
node_manager = NodeManager()

# ❌ Forbidden — side effects (file I/O, config reading)
security = SecurityManager()
```

When the constructor needs parameters (DI rule #1), the creation occurs in the `lifespan` of `main.py` and the factory is in `deps.py`.

---

## 3. CONFIGURATION

**Every environment variable listed in `.env.example` MUST be read by `config.py`. If it is documented, it must work.** No ghost variables.

**One env variable = one field in `Settings`.** No scattered `os.getenv` in the code outside of `config.py`.

---

## 4. IMPORTS

**All imports are at the top of the file. NO deferred imports** in the body of functions except in cases of proven and documented circular imports.

**No `from master.config import settings` in `core/` or `api/`.** Core classes receive config via DI (rule #1).

---

## 5. ERROR HANDLING

**Loops iterating over potentially invalid data must isolate each iteration with a `try/except` block.**

```python
# ✅ A failure does not kill the loop
for node in nodes:
    try:
        transition(node, new_state)
    except Exception:
        logger.exception("Failure for %s", node)
        continue

# ❌ A failure kills everything
for node in nodes:
    transition(node, new_state)  # if an exception occurs, subsequent items are skipped
```

---

## 6. TYPING

**All function parameters and return values must be typed.**
No parameter without annotation (except `*args`, `**kwargs`).
No return without annotation (except `-> None` if the function returns nothing).

```python
# ✅
async def send_intent(self, node_id: str, intent: dict[str, Any], *, timeout: float = 30.0) -> dict[str, Any]:

# ❌
async def send_intent(self, node_id, intent, timeout=30.0):
```

---

## 7. TESTING

**A unit test NEVER depends on the filesystem, real tokens, the real database, or the real singleton.**

```python
# ✅ Acceptable — everything is injected, no real I/O
sec = SecurityManager(server_secret="test", jwt_secret="test",
                      master_private_key=Ed25519PrivateKey.generate(), ...)

# ❌ Forbidden — reads /etc/vigile/ and real secrets
sec = SecurityManager()
```

**Each test creates its own environment** (tmpdir, mocks, fresh instances). No shared state between tests. No implicit execution order.

---

## 8. SPRINT VALIDATION — 5 LEVELS OF TESTING

Each sprint is validated by **5 layers of testing**, from fastest to most realistic.
A sprint is only complete when all 5 levels pass.

### Level 1 — Internal Unit Tests

Automated tests, no network I/O, no real files.

```bash
PYTHONPATH="." python3 tests/unit/test_core.py
PYTHONPATH="." python3 tests/unit/test_plugins.py
# ... each suite
```

- Mock everything external (HTTP, DB, filesystem)
- One test = one clean environment (tmpdir, fresh instances)
- **All green** before moving to Level 2

### Level 2 — External Integration Tests

Tests against the actual HTTP API (server running).

```bash
# Terminal 1: run server
uvicorn master.main:app --port 8000
# Terminal 2: run tests
PYTHONPATH="." python3 tests/integration/test_api.py
```

- Tests routes, RBAC, HTTP status codes
- Uses httpx against the real server
- **All green** before moving to Level 3

### Level 3 — Realistic Simulation

Tests in a containerized environment with perfect simulated data.

```bash
scripts/test_all_simulation.py  # 41 simulation tests
```

- Alpine worker with mocked systemctl/journalctl
- **Realistic services**: running, failed (mysql OOM, prometheus disk full), inactive (apache2, backup), exited (apparmor, networking)
- **Realistic logs**: SSH intrusions, WordPress scans, MySQL crashes, OOM killer
- **Real containers** via mounted Docker socket
- **Real CPU/RAM/DISK statistics** via /proc
- Tests all endpoints: services, logs, containers, stats, restart, chat, proposals
- **All green** before moving to Level 4

### Level 4 — Staging Deployment

Deployment to the production/staging server.

```bash
rsync -avz . youcloud.ovh:/opt/vigile/
docker compose build master worker
docker compose up -d master
```

- Containerized Master + containerized Worker
- Verify `GET /health` → `connected_nodes >= 1`
- **All endpoints respond** before moving to Level 5

### Level 5 — Real-World Conditions

Native deployment (Worker on host, no Docker).

```bash
sudo /usr/local/bin/vigile-worker --master https://vigile.local --token "..."
```

- Worker runs **natively** on target machine
- Real systemd, real Docker, real logs
- AI interacts with the real system
- Complete cycle is tested: chat → proposal → approval → execution → result
- **Final validation** of the sprint

---

## 9. COMMITS

**One commit = one logical unit.** No "fix typos + refactor + feature" in the same commit.

Message format:

```text
Sprint X — Short description (max 72 chars)

- Detail 1
- Detail 2

Tests: N green (M modified)
```

Reminder: never commit without explicit user authorization.

---

## 10. NOMENCLATURE

| Element | Convention | Example |
| --- | --- | --- |
| Files and directories | `snake_case` | `worker_handler.py` |
| Classes | `PascalCase` | `SecurityManager` |
| Functions / methods | `snake_case` | `generate_join_token` |
| Constants | `UPPER_SNAKE_CASE` | `VALID_TRANSITIONS` |
| Private | `_` prefix | `self._connections` |

---

## 11. SECURITY (SECOPS) — Tangible Rules

- **Zero SSH**: Master never connects to Workers. Workers always initiate the connection via WebSocket (NAT bypass).
- **Strong Cryptography**: HMAC-SHA256 for tokens, Ed25519 for Worker auth.
- **No Interactive Shell**: Worker has a hardcoded dictionary of allowed actions. Never use arbitrary `exec()` or shell execution.
- **Audit Trail**: Every DB mutation must go through `log_action()` (SHA256 chain).
- **Zero Third-party Dependencies on Core**: Whitelist is sacred (see Section 12).

---

## 12. ZERO DEPENDENCY (NO BLOATWARE)

**No external dependencies without explicit authorization.**

**Python (Master) Whitelist:** `fastapi`, `uvicorn`, `aiosqlite`, `python-jose`, `passlib`, `httpx`, `pydantic`

**Go (Worker) Whitelist:** Standard Library only. `go get` forbidden.

If a complex feature is needed (LLM client, plugins, retry logic), study existing open-source code and implement the pattern natively.

---

## 13. AI FLOW (HUMAN-IN-THE-LOOP)

- AI **never** touches a Worker directly.
- AI generates typed Pydantic objects via `StructuredLLM`.
- A human always validates the action before execution.

---

## 14. DEV VS TARGET ENVIRONMENT

- **Dev / tests**: Docker Compose.
- **Final target**: Go Worker runs **natively** on target machine (standalone binary, no Docker). Master can run in Docker or not.
- Docker is a dev/test tool, not a dependency for the final user.

---

## 15. AGENT BEHAVIORAL PROTOCOLS

The agent must maintain absolute rigor. The following four protocols are mandatory for any intervention:

- **Mandatory Global Scanning**: Before modifying any shared behavior, API contract, or core component, the agent must perform a global scan to identify all downstream impacts, references, and dependencies across Python (master), Go (worker), and React (frontend) codebases. Isolated local modifications without checking global context are strictly prohibited.
- **Proactive Inconsistency Detection**: During any audit, refactoring, or code modification task, the agent must actively look for and report implicit inconsistencies, code duplication, hardcoded values, style deviations, or tech debt in neighboring or related modules.
- **Long-Term Memory Updates**: Every architectural decision, design pattern discovery, new convention, style invariant, or tech debt finding must be recorded and updated in the project's markdown memory files (`AGENTS.md` and `RULES.md`). The agent must systematically keep these files synchronized with the current state of the code.
- **No Blind Local Patching**: Local hotfixes or workarounds are strictly forbidden if they introduce style divergence, bypass defined abstractions, or conflict with the architectural guidelines of this project. If a fix requires updating an abstraction, the abstraction itself must be refactored globally.

---

*Every line of committed code commits the project for years to come.
You make no compromises on the rules above.*
