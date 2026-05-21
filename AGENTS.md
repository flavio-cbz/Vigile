# Vigile — Agent Guide

## Session start

Read `docs/SESSION.md` first — it has the current sprint status.
Read `RULES.md` second — **coding standards, DI rules, typing, tests**.
Read `docs/LIMITS.md` third — known bugs and architectural limits.

**IMPORTANT:** `RULES.md` contains strict non-negotiable quality rules (DI, typing, zero-dependency, tests). Apply every rule to every line.

## Commit & Push policy

**Never commit or push without explicit approval.**
At end of feature/sprint, present summary (files changed, tests passed) and wait for go-ahead.

## Project structure

```text
master/main.py           # FastAPI entrypoint (v0.2.0-sprint2 — Sprint 3 IA done but version not bumped)
master/config.py         # Settings via os.getenv + pydantic.BaseModel (not pydantic-settings)
master/core/             # SecurityManager, NodeManager, PluginManager, audit, rate_limiter, LLM, proposals
master/api/              # auth.py, nodes.py, services.py, chat.py (REST), deps.py (FastAPI DI)
master/ws/               # worker_handler.py (WebSocket enrollment + operational, 491 lines)
master/db/               # database.py, models.py (pure SQL), migrations.py
master/plugins/          # metrics_plugin.py, systemd_plugin.py, docker_plugin.py
tests/                   # Pytest test suite (91 tests)
  conftest.py            # Global fixtures
  test_core/             # Unit tests for core logic
  test_api/              # Unit tests for API endpoints & test_integration.py
  test_plugins/          # Unit tests for plugin system
  test_ws/               # Unit tests for WebSocket handlers
scripts/                 # setup_test.sh, test_all_simulation.py (~46 checks), test_complex.py
docs/                    # PLAN.md, SESSION.md, LIMITS.md
worker/                  # Go binary (stdlib-only, zero imports, flat package)
  main.go               # Entrypoint, CLI flags (--master, --token, --key-dir), signal handling
  wsclient.go            # WebSocket RFC 6455 pure stdlib (295 lines)
  connection.go          # Reconnect exponential backoff, heartbeat 30s, STATUS_REPORT 60s
  enrollment.go          # Ed25519 keypair generation, challenge/response handshake
  dispatcher.go          # Hardcoded action whitelist + dispatch
  discovery.go           # Hostname, machine-id, OS, arch detection
  stats.go               # CPU/RAM/disk/uptime from /proc
  logs.go                # journalctl + file-based log reading
  containers.go          # Docker API via Unix socket
  services.go            # systemd service management
  Dockerfile             # Multi-stage (golang:1.23-alpine → alpine), 300 lines incl. inline test fixtures
master/templates/        # Jinja2 templates (base, dashboard, node, proposals, audit, plugins)
master/static/           # Custom CSS & JS (chat.js EventSource SSE)
```

## Sprint status

| Sprint | Content | Status |
| -------- | --------- | -------- |
| 1 | Core sec, enrollment, DB, Worker Go basics | ✅ Done |
| 2 | Plugins OS (metrics, systemd, docker), APIs, simulation stack | ✅ Done |
| 3 | LLMClient, StructuredLLM, ActionProposal, Chat API (+ SSE stream) | ✅ Done |
| 4 | Frontend (Jinja2 + HTMX + Tailwind) | ✅ Done |
| 5 | Plugin ecosystem (Home Assistant-like) | 🔜 Next |
| 6+ | Prod hardening, autonomy | 📅 Planned |

See `docs/SESSION.md` for detailed status.

## Key architecture facts

- **No ORM** — pure SQL via aiosqlite. All DDL in `master/db/models.py`.
- **No SSH** — Workers initiate connections via WebSocket (`/ws/worker/join`).
- **No interactive shell** — Worker has a hardcoded action whitelist.
- **State machine**: `PENDING → ENROLLING → CONNECTED → LOST/REVOKED → STALE`. Transitions validated.
- **Audit trail**: append-only SHA256 hash chain. Every DB mutation must call `log_action()`.
- **Ed25519 handshake**: challenge/response over WebSocket for Worker enrollment.
- **JOIN_TOKEN**: HMAC-SHA256, single-use, 30-min TTL. Atomic consumption via `UPDATE ... WHERE consumed=0`.
- **Rate limiter**: in-memory sliding window (60 req/min per route, 10 req/min on `/login`). `cleanup_expired()` exists but is **never called**.
- **Zero-dependency rule**: see `RULES.md` §12.
- **DI rule**: `core/` classes never read `settings`/`os.getenv` — config injected via constructor (RULES.md §1).
- **Settings via os.getenv + pydantic.BaseModel**: not `pydantic-settings`. Auto-generates secrets if env vars empty (`model_post_init` → `secrets.token_hex(32)`), dev only.
- **Config auto-secret generation**: if `SERVER_SECRET_KEY` or `JWT_SECRET_KEY` empty, generated at import time with `secrets.token_hex(32)`. Safe for dev, **never for prod**.

## Commands

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

| Suite / Folder | Description / Tests |
| ------ | -------- |
| `tests/test_core/` | Tests unitaires pour SecurityManager, NodeManager, PluginManager, Audit, LLM. |
| `tests/test_api/` | Tests unitaires pour Chat, Logs, Services et le test d'intégration. |
| `tests/test_plugins/` | Tests unitaires pour les hooks, snap de métriques, enregistrement de plugins. |
| `tests/test_ws/` | Tests unitaires pour l'enrôlement et les opérations WebSocket. |
| **Unit total** | **90 tests unitaires réussis** |
| **Integration** | **1 test d'intégration complet réussi** |

**Note:** Les tests ont été entièrement migrés de l'ancien harnais fait maison (`check()`) vers le framework `pytest`. Les assertions sont maintenant standards (`assert`).

## Gotchas

- `data/` and `__pycache__/` are gitignored — `data/` contains the DB and the master Ed25519 private key. Never commit.
- Secrets auto-generated if env vars empty — fine for dev, **never for prod**. Always set `SERVER_SECRET_KEY` and `JWT_SECRET_KEY` in production.
- `generate_join_token()` returns `(token_string, payload_dict)`, not just a string.
- `NodeManager` methods `get_connection`, `touch_heartbeat`, `is_connected` are `async` — always `await`.
- `transaction()` context manager exists in `database.py` — use it for multi-statement DB operations.
- Plugin hooks have sync (`call()`) and async (`async_call()`) dispatch. Async hooks called via `call()` emit a `warning` log and are silently ignored.
- `PYTHONIOENCODING=utf-8` required on Windows (emoji in test names crash cp1252).
- `.venv` may have broken symlinks when moving between OS — system Python with `PYTHONPATH="."` works as fallback.
- New plugins go in `master/plugins/` and auto-register via hooks — no config change needed.
- `master/api/deps.py` imports `from master.config import settings` at module level — violates RULES.md §1 (should use lazy injection).
- `master/config.py` uses `pydantic.BaseModel` + `os.getenv` directly, **not** `pydantic-settings`. The `model_post_init` hook auto-generates dev secrets.
- CORS wildcard (`CORS_ORIGINS=*`) with `allow_credentials=True` is invalid per spec — see `docs/LIMITS.md`.
- `master/templates/components/` is empty/dead directory — ignore.
- `frontend/` exists but is **empty** — placeholder for Sprint 4.
- `docker-compose.yml` has a hardcoded LLM API key — security risk.
- **No CI/CD**: no `.github/`, no `.editorconfig`, no `.pre-commit-config.yaml`, no Makefile, no pyproject.toml.

## Reference files

| File | Purpose |
| ------ | --------- |
| `RULES.md` | Coding standards, DI, typing, tests, security, zero-dependency |
| `docs/PLAN.md` | Full architecture plan, protocol specs, future sprints |
| `docs/SESSION.md` | Current sprint status |
| `docs/LIMITS.md` | Known bugs, races, scalability limits |
| `.env.example` | All configurable env vars with defaults |
| `master/core/AGENTS.md` | Core domain logic guide |
| `master/api/AGENTS.md` | REST API layer guide |
| `worker/AGENTS.md` | Go Worker binary guide |

## WHERE TO LOOK (Task → Location)

| Task | Directory | Notes |
| ------ | ----------- | ------- |
| Core logic (state machine, crypto, audit, LLM) | `master/core/` | See `master/core/AGENTS.md` |
| REST API endpoints (auth, nodes, services, chat) | `master/api/` | See `master/api/AGENTS.md` |
| Go Worker binary | `worker/` | See `worker/AGENTS.md` |
| Database (pure SQL, migrations) | `master/db/` | All DDL in `models.py` |
| Plugins (metrics, systemd, docker) | `master/plugins/` | Auto-register via hooks |
| WebSocket protocol handler | `master/ws/` | Two-phase enrollment + operational |
| Unit tests | `tests/unit/` | Custom harness, no pytest |
| Integration tests | `tests/integration/` | Requires running server on :8000 |
| Simulation tests | `scripts/` | test_all_simulation.py, test_complex.py |

## CONVENTIONS (Deviations from Standard Python/FastAPI)

- **No pyproject.toml** — bare `requirements.txt` only. Forces `PYTHONPATH="."` everywhere.
- **Pytest** — framework utilisé avec fixtures dans `tests/conftest.py` et assertions standards.
- **No ORM** — pure SQL via `aiosqlite`, all DDL in `master/db/models.py` as strings.
- **No Makefile** — all commands documented in AGENTS.md.
- **No linting/formatting config** — no ruff, mypy, black, isort configs.
- **Settings via `os.getenv`** — not `pydantic-settings`, no `.env` auto-loading.
- **DI at edge** — `core/` classes never read `settings` directly; config injected via constructor.
- **Singleton DI pattern** — module-level singletons for lightweight constructors, factory functions for parameterized ones.
- **App name `master/`** — unconventional (typical: `app/`, `api/`, `server/`).
- **Config class uses pydantic.BaseModel directly** with `model_post_init` for auto-secret generation (not `pydantic-settings`).

## ANTI-PATTERNS (THIS PROJECT)

- **`from master.config import settings` in `api/` or `core/`** — Résolu et corrigé (les dépendances sont injectées proprement).
- **Async hooks called via sync `call()`** — use `async_call()` instead (async hooks silently ignored with warning)
- **~~Rate limiter memory leak~~** — Corrigé (nettoyage automatique via tâche d'arrière-plan asynchrone).
- **Hardcoded LLM API key** in `docker-compose.yml` (security risk)
- **CORS wildcard + credentials incompatibility** — `allow_credentials=True` with `CORS_ORIGINS=*` breaks browsers
- **~~No pagination~~** — Corrigé (pagination implémentée pour `list_nodes` et `verify_chain`).
- **`_pending_intents` non nettoyé après timeout** — stale entries in dict
- **~~Plugin double-registration~~** — Corrigé (protection contre la double-inscription des plugins).

## UNIQUE STYLES

- **Audit trail**: append-only SHA256 hash chain. Every DB mutation calls `log_action()`.
- **Ed25519 handshake**: challenge/response over WebSocket for Worker enrollment.
- **Zero-dependency Go**: Worker binary is stdlib-only (RFC 6455 WebSocket implemented by hand).
- **Custom LLM client**: native OpenAI-compatible `complete()` + `stream()` — no `openai` library.
- **Action proposals**: Pydantic state machine (PENDING→APPROVED→EXECUTED|FAILED) with human-in-the-loop.
- **Test harness**: custom `check()` + `results` pattern, no pytest — each file runnable standalone.

## NOTES

- `data/` (DB + Ed25519 key) is gitignored. Never commit.
- `generate_join_token()` returns `(token_string, payload_dict)`, not just a string.
- `PYTHONIOENCODING=utf-8` required on Windows (emoji in test names).
- `.venv` may break across OS — `PYTHONPATH="."` with system Python works as fallback.
- `master/templates/components/` is empty/dead directory — ignore.
- `frontend/` is empty — placeholders for Sprint 4 React app.
- No `.editorconfig`, `.pre-commit-config.yaml`, `.github/`, or CI workflow files exist.
- `scripts/test_complex.py` exists but contains no test assertions — may be a draft or scratch file.

## Repository Map

A full codemap is available at `codemap.md` in the project root.

Before working on any task, read `codemap.md` to understand:
- Project architecture and entry points
- Directory responsibilities and design patterns
- Data flow and integration points between modules

For deep work on a specific folder, also read that folder's `codemap.md`.
