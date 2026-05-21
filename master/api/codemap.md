# master/api/

## Responsibility

The REST API layer that exposes Vigile's core capabilities over HTTP. It translates HTTP requests into database queries, WebSocket INTENT messages to Workers, and LLM streaming responses. All external human interaction with the system (auth, node management, service/container control, and AI chat) flows through these FastAPI routers.

## Design

- **One router per domain** -- `auth.py`, `nodes.py`, `services.py`, `chat.py`. Each file creates an `APIRouter` with a prefix. Routers are registered in `master/main.py` via `app.include_router()`.
- **FastAPI dependency injection** via `deps.py`. All dependencies are injected as function parameters using `Depends()`. Type aliases `CurrentUser` and `DB` shorten signatures. No request-level middleware.
- **Role-based access control** via `require_role("admin")`, `require_role("operator", "admin")`. A dependency factory that receives allowed roles and returns a closure. Calls `SecurityManager.require_role()` at request time.
- **JWT Bearer auth** -- `get_current_user()` extracts and verifies the JWT from the `Authorization: Bearer` header. Returns the claims dict. All endpoints except `/kickstart.sh` and `/login` require authentication.
- **Lazy LLM initialization** -- `LLMClient` and `StructuredLLM` are module-level `None` singletons in `deps.py`, created on first call. This avoids importing LLM dependencies at application startup when the LLM feature is not in use.
- **INTENT-based remote execution** -- `NodeManager.send_intent()` sends action messages to Workers over WebSocket. Services, containers, and logs all use this pattern. 15-second timeout. Errors map to HTTP 503 (worker unreachable) or 504 (timeout).
- **SSE streaming for chat** -- `POST /api/chat` returns a `StreamingResponse` with `text/event-stream`. The inner generator yields `token`, `proposal`, `error`, and `done` events as SSE JSON lines.
- **Pydantic request/response models** at endpoint boundaries. No ORM -- raw SQL via `aiosqlite` with dict row factories.
- **Rate limiting** on `/login` via `rate_limiter.dependency(10)` (10 requests/minute). Applied as a route dependency.
- **Audit trail** -- every state-changing operation (`GENERATE_JOIN_TOKEN`, `REVOKE_NODE`, `PROPOSAL_APPROVED`, `PROPOSAL_REJECTED`) calls `log_action()` which appends a SHA256-chained entry to the audit log.

## Flow

1. **Request arrives** at uvicorn. FastAPI routes it to the matching router based on path prefix and HTTP method.
2. **Dependencies resolve**: FastAPI calls `Depends()` functions top-down. `get_db()` returns the shared `aiosqlite.Connection`. `get_current_user()` / `require_role()` verify the JWT from the `Authorization` header and return claims. `get_node_manager()` returns the singleton.
3. **Endpoint handler executes**: reads the Pydantic-validated request body, performs business logic:
   - **Reads**: queries SQLite directly (nodes list, stats, proposals).
   - **Writes**: uses `db.execute()` + `db.commit()` for mutations. All admin operations log to audit trail.
   - **Remote actions**: calls `nm.send_intent(node_id, payload, timeout)` which dispatches to the Worker's WebSocket connection.
4. **Response returned**: Pydantic model serialized to JSON (or `StreamingResponse` for chat, `PlainTextResponse` for kickstart script).
5. **Error handling**: HTTP exceptions at known points. INTENT errors map to 503 (RuntimeError = connection failed) or 504 (TimeoutError = no response in 15s). 404 for missing nodes/proposals. 409 for state conflicts (already revoked, not PENDING).

## Integration

- Consumed by: External HTTP clients (operators, automation, CLI tools, frontend in Sprint 4). The kickstart script at `/api/nodes/kickstart.sh` is consumed by Worker nodes during enrollment (curl pipe to sh).
- Depends on:
  - `master/core/security_manager.py` -- JWT creation/verification, password hashing, JOIN_TOKEN generation
  - `master/core/node_manager.py` -- Node state machine, WebSocket connection tracking, INTENT dispatch
  - `master/core/llm_client.py` -- OpenAI-compatible LLM streaming client
  - `master/core/structured_llm.py` -- Pydantic model extraction from LLM responses
  - `master/core/action_proposal.py` -- Proposal state machine (PENDING / APPROVED / EXECUTED / FAILED)
  - `master/core/rate_limiter.py` -- In-memory sliding window rate limiter
  - `master/core/audit.py` -- Append-only SHA256 audit chain
  - `master/db/database.py` -- `get_db_conn()` returning the lifespan-managed aiosqlite connection
  - `master/config.py` -- Settings singleton (violates RULES.md -- should be injected)
  - `master/plugins/systemd_plugin.py` -- `parse_service_list()`, `parse_service_status()`
  - `master/plugins/docker_plugin.py` -- `parse_container_list()`
