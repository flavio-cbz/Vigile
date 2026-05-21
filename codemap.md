# Repository Atlas: Youcloud-API (Vigile)

## Project Responsibility

Zero-trust fleet management server with a Go agent running on each target node. The Python/FastAPI Master authenticates operators via JWT, manages Worker node lifecycles through a strict state machine (PENDING to REVOKED), orchestrates Ed25519-based enrollment handshakes over WebSocket, dispatches approved intents to connected Workers, persists all state in SQLite, maintains an append-only SHA256 audit chain, provides LLM-powered chat with human-in-the-loop action proposals, and enforces rate limiting and RBAC at every endpoint.

## System Entry Points

- `master/main.py` — FastAPI app entrypoint, lifespan (startup/shutdown), route registration, admin endpoints
- `master/config.py` — Settings via `os.getenv` + `pydantic.BaseModel` (not pydantic-settings), auto-secret generation for dev
- `requirements.txt` — 8 pinned Python dependencies (fastapi, uvicorn, aiosqlite, python-jose, passlib, bcrypt, httpx, pydantic)
- `docker-compose.yml` — Multi-service orchestration (Master + Workers + optional LLM proxy)
- `Dockerfile.master` — Multi-stage Python Docker build for Master
- `.env.example` — All 51 configurable env vars with defaults and documentation
- `opencode.json` — OpenCode agent configuration
- `RULES.md` — Non-negotiable coding standards (DI, typing, zero-dependency, tests)
- `AGENTS.md` — Agent guide with sprint status, project structure, commands, gotchas

## Directory Map (Aggregated)

| Directory | Responsibility Summary | Detailed Map |
|-----------|------------------------|--------------|
| `master/` | FastAPI backend control plane — route registration, lifespan orchestration, middleware stack (CORS, rate limiter, HTTPS enforcement), admin debug endpoints. | [View Map](master/codemap.md) |
| `master/api/` | REST API layer — 4 domain routers (auth, nodes, services, chat) exposing core capabilities over HTTP with FastAPI DI, JWT auth, RBAC, rate limiting, SSE streaming, and audit trail. | [View Map](master/api/codemap.md) |
| `master/core/` | Trusted business logic — Ed25519 crypto/JWT/HMAC tokens, Worker node state machine, append-only SHA256 audit trail, sliding-window rate limiter, plugin hook dispatch, LLM client + structured output + action proposals. Strict DI rules. | [View Map](master/core/codemap.md) |
| `master/db/` | Pure SQL database layer — aiosqlite connection singleton with WAL mode, async transaction context manager, inline DDL as SQL strings, idempotent migrations, default admin seeding, genesis audit chain anchor. No ORM. | [View Map](master/db/codemap.md) |
| `master/ws/` | Single-file WebSocket handler (491 lines) — two-phase protocol: Ed25519 challenge/response enrollment secured by HMAC-SHA256 JOIN_TOKEN, followed by long-lived operational loop for heartbeats, intent dispatch, and status report collection. | [View Map](master/ws/codemap.md) |
| `master/plugins/` | Master-side plugin modules — declare Worker-supported actions (`get_supported_actions`), validate responses via Pydantic, normalize and persist STATUS_REPORT metrics. Auto-register via `PluginManager.load_plugins_from_dir()`. | [View Map](master/plugins/codemap.md) |
| `worker/` | Zero-dependency Go binary — stdlib-only RFC 6455 WebSocket client, Ed25519 identity, hardcoded action whitelist (8 actions: stats, logs, containers, services). Runs on target servers as on-premise agent. | [View Map](worker/codemap.md) |
| `frontend/` | Sprint 4 React SPA (placeholder) — Vite + TailwindCSS + shadcn/ui. Planned components: ChatPanel (SSE streaming from LLM), ActionProposal (human-in-the-loop approval), NodeCard/NodeTable (node monitoring), LogViewer, ServiceList, ContainerList, AuditLog, PluginCatalogue. Consumes all `master/api/` REST endpoints with JWT auth and RBAC. | [View Map](frontend/codemap.md) |
| `scripts/` | Test infrastructure — Docker Compose orchestration (`setup_test.sh`), full surface-area test (`test_all_simulation.py`, ~46 checks), multi-step Human-in-the-Loop chat scenario test (`test_complex.py`). | [View Map](scripts/codemap.md) |

## Integration Points

| Component | Consumes | Provides |
|-----------|----------|----------|
| Master (FastAPI) | WebSocket connections from Workers, HTTP requests from operators, LLM API | REST API, WebSocket enrollment endpoint, admin endpoints |
| Worker (Go) | Master WebSocket enrollment + intents, Linux `/proc`, Docker socket, systemd | System metrics, log contents, container/service management |
| Database (SQLite) | Read/write from all Master modules | Persistent node state, audit chain, user accounts, metrics snapshots |
| LLM Provider | Chat prompts with node context | Streaming completions, structured action proposals |

## Architecture Constraints

- **No ORM** — pure SQL via aiosqlite. All DDL in `master/db/models.py`.
- **No SSH** — Workers initiate connections via WebSocket (`/ws/worker/join`).
- **No interactive shell** — Worker has a hardcoded action whitelist (8 actions).
- **No pytest** — custom test harness with `check()` + `results` pattern.
- **No pyproject.toml** — bare `requirements.txt` only. Forces `PYTHONPATH="."`.
- **DI-at-the-edge**: `core/` classes receive config via constructor, never read `settings` directly. Known violations in `api/` and `db/`.
- **Zero-dependency Go**: Worker binary is stdlib-only (RFC 6455 WebSocket implemented by hand).
- **App name `master/`** — unconventional (typical: `app/`, `api/`, `server/`).
