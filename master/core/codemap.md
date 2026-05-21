# master/core/

## Responsibility

Heart of the Vigile system. Owns all trusted business logic: cryptographic identity (Ed25519 keypairs, JWT, HMAC tokens), Worker node lifecycle state machine (PENDING through REVOKED), append-only SHA256 audit trail, in-memory sliding-window rate limiting, plugin hook dispatch, and LLM integration for chat + structured action proposals. Every class follows strict DI rules (configuration injected via constructor, never reads `settings` or `os.getenv`).

## Design

- **Strict DI at construction**: `SecurityManager`, `LLMClient`, `StructuredLLM`, `NodeManager`, `RateLimiter` all receive config via constructor params. No module-level `from master.config import settings` in any core file.
- **Singleton at module edge**: `PluginManager`, `NodeManager`, `RateLimiter` export module-level instances. `SecurityManager` uses `init_security()` / `get_security_instance()` with a guard against double init.
- **State machines enforced in code**: Node state transitions validated against `VALID_TRANSITIONS` set (13 allowed pairs across 7 states). `ActionProposal` status guarded by `_VALID_STATUS_TRANSITIONS` dict (PENDING is the only entry point).
- **Future-based async intent dispatch**: `NodeManager.send_intent()` creates an `asyncio.Future`, sends an `INTENT` message type over WebSocket, and awaits the Future. The WebSocket operational loop calls `resolve_intent()` to deliver the Worker's response.
- **Background heartbeat monitor**: `NodeManager._heartbeat_monitor()` is an `asyncio.Task` that periodically checks heartbeat age and transitions nodes to LOST/STALE. Thresholds injected at `start()` time.
- **Append-only hash chain audit**: SHA256 of `(previous_hash | sequence | timestamp | action | user_id | node_id | details_json)`. `verify_chain()` walks the full table recomputing every hash. An `asyncio.Lock` serializes writes to prevent sequence collision.
- **Sliding window per (IP, route)**: `RateLimiter` keys on `f"{client_ip}:{request.url.path}"` with per-bucket timestamp lists. Global middleware and per-endpoint dependency both reference the same singleton.
- **Plugin hook dispatch**: Inspired by Pluggy (pytest). `PluginManager` stores `{hook_name: [(plugin_name, callable)]}`. Sync dispatch (`call()`) skips async callables with a warning. Async dispatch (`async_call()`) runs sync hooks via `run_in_executor` and coroutines via `create_task`, gathered concurrently.
- **Ed25519 challenge/response**: Static methods `generate_challenge()` and `verify_ed25519_signature()` for Worker enrollment handshake. Master private key persisted to disk via `load_or_generate_master_key()`.
- **Four token types in SecurityManager**: JOIN_TOKEN (HMAC-SHA256, single-use, 30-min TTL), WORKER_TOKEN (JWT HS256 with rotation lifecycle), user access token (JWT short-lived), user refresh token (JWT long-lived).
- **Structured LLM pattern**: `StructuredLLM.create()` generates a JSON schema from a Pydantic model, injects it as a system prompt, calls `LLMClient.complete()`, validates with `model_validate_json()`, and retries up to `max_retries` showing validation errors to the LLM.
- **Thread/task safety via asyncio.Lock**: `NodeManager._lock` protects `_connections`, `_pending_intents`, `_intent_nodes`. `RateLimiter._lock` protects `_buckets`. `_audit_lock` in audit.py serializes chain appends.

## Flow

1. **Worker enrollment**: Admin calls `NodeManager.create_node()` (INSERT PENDING) -> `SecurityManager.generate_join_token()` (HMAC-signed) -> Worker connects via WebSocket -> token decoded via `decode_join_token()` -> state transitions to ENROLLING -> Ed25519 challenge/response (`generate_challenge()` + `verify_ed25519_signature()`) -> state to CONNECTED -> `generate_worker_token()` issued.
2. **Heartbeat monitoring**: Every 30s, `_heartbeat_monitor()` iterates active connections. If `heartbeat_age > lost_threshold` (300s) -> `unregister_connection()` + transition to LOST. If LOST nodes exceed stale_threshold (86400s) -> transition to STALE. Reconnecting Workers transition LOST/STALE back to CONNECTED.
3. **Intent execution**: Operator approves an `ActionProposal` (state -> APPROVED) -> `NodeManager.send_intent()` creates a Future -> WebSocket sends `INTENT` message -> Worker executes and responds -> operational loop calls `resolve_intent()` setting the Future result -> `ActionProposal.complete()` transitions to EXECUTED or FAILED.
4. **Audit logging**: Every DB mutation calls `log_action()` -> acquires `_audit_lock` -> fetches current chain head -> computes `compute_entry_hash()` over previous_hash + sequence + fields -> INSERTs new entry with monotonic sequence number.
5. **Rate limiting**: Incoming HTTP request -> `RateLimiter.middleware()` or `.dependency()` extracts `client_ip + path` -> `is_allowed()` filters stale timestamps -> checks `len(timestamps) >= max_requests` -> returns 429 or allows through.
6. **LLM chat + proposals**: `LLMClient.complete()` sends POST to `/v1/chat/completions` -> response parsed -> if structured, `StructuredLLM.create()` validates against a Pydantic schema with retries -> result used to create `ActionProposal` in PENDING state for operator review.
7. **Plugin hook dispatch**: On events (node connect, intent received, metrics collected), `plugin_manager.async_call("hook_name", **data)` gathers all registered handler results concurrently. Sync handlers run in thread pool, async handlers as coroutines.

## Integration

- **Consumed by**:
  - `master/api/auth.py` — `SecurityManager` for login (password verify, JWT create/verify), RBAC dependencies (`require_role()`)
  - `master/api/nodes.py` — `NodeManager` for list, get, create, revoke; `SecurityManager` for join token generation
  - `master/api/services.py` — `NodeManager.send_intent()` to dispatch service actions to Workers
  - `master/api/chat.py` — `LLMClient` + `StructuredLLM` + `ActionProposal` for chat and AI action proposals
  - `master/ws/worker_handler.py` — `NodeManager` for connection register/unregister/touch_heartbeat, state transitions, intent resolution; `SecurityManager` for token verification
  - `master/db/migrations.py` — `compute_entry_hash()` from audit.py for genesis entry creation
  - `master/main.py` — lifespan calls `NodeManager.start/stop`, `init_security()`, `load_or_generate_master_key()`
  - `master/api/deps.py` — `RateLimiter.dependency()` for per-endpoint rate limiting
  - `master/plugins/` — `PluginManager.register()` called by each plugin's `register()` function

- **Depends on**:
  - `aiosqlite` — async SQLite for all DB operations (NodeManager, audit, SecurityManager token revocation)
  - `cryptography` (hazmat) — Ed25519 key generation, serialization, signature verification
  - `jose` (python-jose) — JWT encode/decode (HS256) for worker tokens and user tokens
  - `passlib` — bcrypt password hashing via `CryptContext`
  - `httpx` — async HTTP for LLM API calls (both `complete()` and SSE `stream()`)
  - `pydantic` — BaseModel for `ActionProposal`, JSON schema generation in `StructuredLLM`
  - `fastapi` — WebSocket, HTTPException, Request, Depends, middleware integration
  - `master/db/database.py` — `get_db_conn()` used by `NodeManager._check_heartbeats()`
  - Python stdlib: `hashlib`, `hmac`, `secrets`, `base64`, `json`, `uuid`, `time`, `asyncio`, `inspect`, `importlib`, `os`
