# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-03T23:31:04+02:00
**Commit:** c9812a7
**Branch:** master

## OVERVIEW
Vigile is a zero-trust fleet management server and agent system. The Python/FastAPI Master node coordinates authenticated operator commands via an LLM agent with human-in-the-loop validation, communicating with autonomous, zero-dependency Go Workers over WebSocket.

## STRUCTURE
```text
master/                  # Control plane FastAPI server
├── api/                 # REST API layer (auth, nodes, services, chat)
├── core/                # Trusted domain logic (state, crypto, LLM, audit)
├── db/                  # Raw SQL SQLite database & Alembic migrations
├── plugins/             # OS systemd/Docker/metrics telemetry plugins
├── ws/                  # Two-phase WebSocket enrollment & operational connection handler
├── static/              # Compiled React SPA files served directly by FastAPI
worker/                  # Zero-dependency autonomous Go agent binary
frontend/                # React Vite SPA for operator interaction & Copilot
tests/                   # Pytest test suite (93% coverage)
scripts/                 # Dev launcher and Docker-based simulation tests
docs/                    # Planning, known limits, and session logs
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Core logic (state machine, crypto, audit, LLM, insights) | [master/core/](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core) | See [core/AGENTS.md](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/AGENTS.md) |
| REST API endpoints (auth, nodes, services, chat, admin, audit, demo) | [master/api/](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api) | See [api/AGENTS.md](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/AGENTS.md) |
| Go Worker binary | [worker/](file:///Users/flavio/Documents/Projets/Youcloud-API/worker) | See [worker/AGENTS.md](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/AGENTS.md) |
| Database (pure SQL, migrations, alembic) | [master/db/](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db) | See [db/AGENTS.md](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/AGENTS.md) |
| Plugins (metrics, systemd, docker) | [master/plugins/](file:///Users/flavio/Documents/Projets/Youcloud-API/master/plugins) | Auto-register via hooks; see [plugins/AGENTS.md](file:///Users/flavio/Documents/Projets/Youcloud-API/master/plugins/AGENTS.md) |
| WebSocket protocol handler | [master/ws/](file:///Users/flavio/Documents/Projets/Youcloud-API/master/ws) | Two-phase enrollment + operational; see [ws/AGENTS.md](file:///Users/flavio/Documents/Projets/Youcloud-API/master/ws/AGENTS.md) |
| Pytest test suite | [tests/](file:///Users/flavio/Documents/Projets/Youcloud-API/tests) | See [tests/AGENTS.md](file:///Users/flavio/Documents/Projets/Youcloud-API/tests/AGENTS.md) |
| Simulation & dev launcher | [scripts/](file:///Users/flavio/Documents/Projets/Youcloud-API/scripts) | See [scripts/AGENTS.md](file:///Users/flavio/Documents/Projets/Youcloud-API/scripts/AGENTS.md) |
| React SPA | [frontend/](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend) | See [frontend/AGENTS.md](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/AGENTS.md) |

## CODE MAP

| Symbol | Type | Location | Refs | Role |
|--------|------|----------|------|------|
| `SecurityManager` | Class | [security_manager.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/security_manager.py) | High | Cryptography, JOIN_TOKEN (HMAC), JWT, Ed25519 challenge/response verification |
| `NodeManager` | Class | [node_manager.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py) | High | Worker lifecycle state machine and active WebSocket registries |
| `PluginManager` | Class | [plugin_manager.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/plugin_manager.py) | Medium | Hook-based plugin loading and sync/async hook dispatching |
| `RateLimiter` | Class | [rate_limiter.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/rate_limiter.py) | Medium | Sliding window rate limiting per IP + endpoint with lifespan cleanups |
| `LLMClient` | Class | [llm_client.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/llm_client.py) | Medium | Native HTTP client for OpenAI-compatible chat completion & streams |
| `StructuredLLM` | Class | [structured_llm.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/structured_llm.py) | Medium | System prompts for JSON schema validation & LLM retry feedback loops |
| `ActionProposal` | Class | [action_proposal.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/action_proposal.py) | Medium | Operator-approved action model (PENDING to APPROVED to EXECUTED/FAILED) |
| `worker_join_handler` | Function | [worker_handler.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/ws/worker_handler.py) | High | Entry point router `/ws/worker/join` for worker connections |
| `verify_chain` | Function | [audit.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/audit.py) | Medium | Full SHA256 chain verification walking the entire audit log table |
| `run_migrations` | Function | [migrations.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/migrations.py) | Medium | Idempotent table creation, indexes registration, and admin seeder |

## CONVENTIONS
- **No ORM**: Raw SQL text queries via `aiosqlite`.
- **No pyproject.toml**: Only bare `requirements.txt`. Execution relies on setting `PYTHONPATH="."`.
- **DI at edge**: Domain logic constructors in `master/core/` are lightweight and receive raw configuration/arguments, never reading env vars or settings directly.
- **WebSocket Handshake**: Ed25519 challenge-response sequence over raw WS frames implemented from scratch in both Python and Go (zero external WS libraries in Go worker).

## ANTI-PATTERNS (THIS PROJECT)
- **CORS Wildcard**: CORS origins allow wildcards mapped dynamically via echoing middleware, but must be configured securely in production.
- **Dependency Injection leakage**: Module-level import `from master.config import settings` in `master/api/deps.py` (lines 63, 213) violates DI rules.
- **Sync call of async hooks**: Running async plugin hooks via sync `call()` emits a warning and is ignored. Always use `async_call()`.
- **Database transaction locks**: Shared single aiosqlite Connection; multi-statement mutations must be wrapped in `transaction()` context to prevent sequence conflicts.
- **Dynamic execution**: `compile()` and `exec()` inside `master/api/admin.py:337` allow dynamic python running; access must remain strictly role-gated.

## UNIQUE STYLES
- **Hash Chain Audit Trail**: Cryptographically linked logs where each entry contains `SHA256(previous_hash + sequence + data)`.
- **Two-phase WebSocket Enrollment**: challenge-response protocol with `JOIN_TOKEN` verification before operational heartbeats start.
- **Zero-Dependency Go worker**: Raw network socket frame decoding for RFC 6455 WebSocket connectivity without standard library extensions.

## COMMANDS
```bash
# Lancer les tests unitaires (ne requiert pas le serveur actif)
$env:PYTHONPATH="."  # Windows PowerShell
python -m pytest -m "not integration" -v

# Lancer le serveur de dev Master
python -m uvicorn master.main:app --host 127.0.0.1 --port 8000 --reload

# Lancer les tests d'intégration (nécessite le serveur sur le port 8000)
python -m pytest -m "integration" -v

# Lancer la totalité des tests (nécessite le serveur actif)
python -m pytest -v

# Simulation tests (requires Docker Compose stack)
./scripts/setup_test.sh
PYTHONPATH="." .venv/bin/python scripts/test_all_simulation.py

# Docker test stack
docker compose build
docker compose up -d master
./scripts/setup_test.sh --workers 2

# Default admin: admin / admin (Changement obligatoire à la première connexion)
```

## AGENT BEHAVIORAL PROTOCOLS
To ensure the integrity, consistency, and long-term maintainability of the project, the agent MUST strictly adhere to the following behavioral protocols before, during, and after any task:
- **Mandatory Global Scanning**: Before modifying any shared behavior, API contract, or core component, the agent must perform a global scan to identify all downstream impacts, references, and dependencies across Python (master), Go (worker), and React (frontend) codebases.
- **Proactive Inconsistency Detection**: During any audit, refactoring, or code modification task, the agent must actively look for and report implicit inconsistencies, code duplication, hardcoded values, style deviations, or tech debt in neighboring or related modules.
- **Long-Term Memory Updates**: Every architectural decision, design pattern discovery, new convention, style invariant, or tech debt finding must be recorded and updated in the project's markdown memory files (`AGENTS.md` and `RULES.md`). The agent must systematically keep these files synchronized with the current state of the code.
- **No Blind Local Patching**: Local hotfixes or workarounds are strictly forbidden if they introduce style divergence, bypass defined abstractions, or conflict with the architectural guidelines of this project.

## NOTES
- `data/` and `__pycache__` are gitignored.
- `AGENTS.md` and `RULES.md` are gitignored to preserve developer workspace preferences.
- SQLite WAL mode enables parallel reads but writes are serialized.
- Auto-generated secrets (`secrets.token_hex(32)`) occur dynamically if config values are blank in development.

## AUDIT FINDINGS (2026-06-04)
File-by-file audit (4 specialists + cross-critique + Oracle verification) found **79 issues** the 8 audit documents in `docs/` missed:
- **Cross-cutting**: 8 mega-issues (e.g., no TLS anywhere, no fix enforcement, no worker concurrency)
- **Backend**: 13 new issues (require_role bypasses must_change_password/is_active, migration stamping broken)
- **Worker**: 10 new issues (no TLS, no exec timeouts, frame parse panic)
- **Frontend**: 18 new issues (zero AbortSignal, stale closures, localStorage token bypass)
- **Infra**: 30 new issues (live API key in .env, zero Go/frontend tests, CI no pre-commit/securité)

Full report: `.sisyphus/reports/audit-missed-report.md`
