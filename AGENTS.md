# Vigile — Agent Guide

## Session start

Read `docs/SESSION_INIT.md` first — it has the current sprint status.
Read `CLAUDE.md` for project rules (zero-dependency, security).
Read `docs/LIMITS.md` for known bugs and architectural limits.

## Commit & Push policy

**Never commit or push without explicit approval.**
At the end of each sprint or feature, ask the user for permission:
  1. Present the summary of changes (files changed, tests passed)
  2. Wait for a "go ahead" before committing
  3. Only push after the commit is confirmed

## Project structure

```
master/main.py           # FastAPI entrypoint
master/config.py         # Settings from env vars (.env.example)
master/core/             # SecurityManager, NodeManager, PluginManager, audit, rate_limiter
master/api/              # auth.py, nodes.py (REST), deps.py (FastAPI dependencies)
master/ws/               # worker_handler.py (WebSocket enrollment + operational)
master/db/               # database.py, models.py (pure SQL), migrations.py
master/plugins/          # metrics_plugin.py (CPU/RAM/disque/swap/uptime), + à venir
tests/unit/              # test_core.py (57), test_worker_handler.py (15), test_plugins.py (88), test_logs_api.py (22), test_services_api.py (36) = 218 tests
tests/integration/       # test_api.py (22 tests, requires running server)
docs/                    # INIT.md (architecture plan), SESSION_INIT.md, LIMITS.md
worker/                  # Go binary (stdlib only, zero imports)
  main.go               # Entrypoint, CLI flags, signal handling
  wsclient.go            # WebSocket client — RFC 6455 pur stdlib
  connection.go          # Connect, reconnect backoff, heartbeat, status reports
  enrollment.go          # Ed25519 keypair generation, handshake protocol
  dispatcher.go          # Intent whitelist + dispatch to actions
  discovery.go           # Hostname, machine-id, OS, arch detection
  stats.go               # CPU/RAM/disk/uptime from /proc (Linux)
  logs.go                # Log reading (journalctl, file)
  containers.go          # Docker API via Unix socket
  services.go            # systemd service management
  Dockerfile             # Multi-stage build (golang:1.23-alpine → alpine)
scripts/
  setup_test.sh          # Docker Compose test environment automation
Dockerfile.master        # Python Master container image
docker-compose.yml       # Full test stack (Master + Workers)
```

`worker/` (Go binary) — implémenté en Sprint 2, zéro dépendance externe.

## Zero-dependency rule

**Never add a pip/go dependency without explicit permission.**
Whitelist (master): `fastapi`, `uvicorn`, `aiosqlite`, `python-jose`, `passlib`, `httpx`, `pydantic`
Whitelist (worker): Go stdlib only — zero imports.

Implement patterns natively (PluginManager, RateLimiter, LLMClient, StructuredLLM are all hand-written, inspired by OSS but zero imports).

## Key architecture facts

- **No ORM** — pure SQL via aiosqlite. All DDL in `master/db/models.py`.
- **No SSH** — Workers initiate connections via WebSocket (`/ws/worker/join`).
- **No interactive shell** — Worker has a hardcoded action whitelist.
- **State machine** in `NodeManager`: `PENDING → ENROLLING → CONNECTED → LOST/REVOKED → STALE`. Transitions are validated.
- **Audit trail** — append-only SHA256 hash chain. Every DB mutation must call `log_action()`.
- **Ed25519 handshake** for Worker enrollment (challenge/response over WebSocket).
- **JOIN_TOKEN** = HMAC-SHA256, single-use, 30-min TTL. Atomic consumption via `UPDATE ... WHERE consumed=0`.
- **Rate limiter** in-memory sliding window (60 req/min per route, 10 req/min on `/login`).

## Commands

```bash
# Run all unit tests (no server required)
# Linux/macOS:
PYTHONPATH="." PYTHONIOENCODING=utf-8 .venv/bin/python tests/unit/test_core.py
PYTHONPATH="." PYTHONIOENCODING=utf-8 .venv/bin/python tests/unit/test_worker_handler.py
PYTHONPATH="." PYTHONIOENCODING=utf-8 .venv/bin/python tests/unit/test_plugins.py

# Windows:
set PYTHONPATH=. && set PYTHONIOENCODING=utf-8 && .venv\Scripts\python tests/unit/test_core.py
set PYTHONPATH=. && set PYTHONIOENCODING=utf-8 && .venv\Scripts\python tests/unit/test_worker_handler.py
set PYTHONPATH=. && set PYTHONIOENCODING=utf-8 && .venv\Scripts\python tests/unit/test_plugins.py

# Run integration tests (requires server running on :8000)
PYTHONPATH="." uvicorn master.main:app --host 127.0.0.1 --port 8000 --reload
# then in another terminal:
PYTHONPATH="." .venv/bin/python tests/integration/test_api.py

# Start dev server
PYTHONPATH="." uvicorn master.main:app --host 127.0.0.1 --port 8000 --reload

# Default admin: admin / admin
```

## Gotchas

- `data/` and `__pycache__/` are gitignored — but `data/` contains the DB and the master Ed25519 private key. Never commit them.
- Secrets are auto-generated if env vars are empty — fine for dev, **never for prod**. Always set `SERVER_SECRET_KEY` and `JWT_SECRET_KEY` in production.
- `generate_join_token()` returns `(token_string, payload_dict)`, not just a string.
- `NodeManager` methods `get_connection`, `touch_heartbeat`, `is_connected` are `async` — always `await` them.
- The `transaction()` context manager exists in `database.py` — use it for multi-statement DB operations.
- Plugin hooks have sync (`call()`) and async (`async_call()`) dispatch. Async hooks called via `call()` emit a `warning` log.
- `PYTHONIOENCODING=utf-8` is required on Windows (emoji in test names crash cp1252).
- The `.venv` may have broken symlinks when moving between OS — system Python works with `PYTHONPATH="."`.
- New plugins go in `master/plugins/` and auto-register via hooks — no config change needed.

## Reference files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project rules, security, zero-dependency |
| `docs/INIT.md` | Full architecture plan, protocol specs, future sprints |
| `docs/LIMITS.md` | Known bugs, races, scalability limits |
| `.env.example` | All configurable env vars with defaults |
