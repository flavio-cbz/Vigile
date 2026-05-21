# master/ws/

## Responsibility

Single-file WebSocket handler (491 lines) that authenticates and manages remote Worker nodes through a two-phase protocol. Phase 1 (Enrollment) performs an Ed25519-based challenge/response handshake secured by a single-use HMAC-SHA256 JOIN_TOKEN with 30-minute TTL. Phase 2 (Operational) runs a long-lived bidirectional message loop handling heartbeats, intent dispatch with result forwarding, and status report collection. The handler enforces strict state machine transitions on the NodeManager (`PENDING/STALE/LOST/RECONNECTING -> ENROLLING -> CONNECTED`) and uses application-defined WebSocket close codes (4400-4500) to signal specific failure modes.

## Design

- **Two-phase protocol**: Enrollment is sequential, time-bounded (30s per step), and must complete before the operational loop starts. Any malformed message or timeout during enrollment closes the socket immediately with no retry.
- **State machine gating**: Every enrollment checks `_get_node_state()` against allowed inbound states (`PENDING`, `LOST`, `STALE`, `RECONNECTING`). `REVOKED` nodes are rejected. On disconnect, state regresses: `CONNECTED -> RECONNECTING`, `ENROLLING -> PENDING`.
- **Atomic token consumption**: The JOIN_TOKEN is consumed inside a `transaction()` block with `UPDATE ... WHERE consumed=0`. Zero rowcount means a race lost -- the connection is closed with `WS_CLOSE_TOKEN_CONSUMED`.
- **IP prefix restriction**: Tokens can carry an `ip_prefix` claim. If set, the remote address must start with that prefix. Trusted proxy headers (`X-Forwarded-For`) are supported via `settings.trusted_proxies`.
- **Heartbeat deadline**: The operational loop uses `asyncio.wait_for` with a timeout of `settings.heartbeat_interval * 3`. Missing any message for that long closes the connection.
- **Plugin-driven status normalization**: `STATUS_REPORT` messages pass through `plugin_manager.call_first("normalize_status_report")`, then hook into `plugin_manager.async_call("on_status_report", ...)` for storage.
- **No WebSocket library abstraction**: Uses FastAPI's `WebSocket` class directly (`receive_text()`, `send_text()`, `close()`). No external WebSocket library.
- **Close codes are informational only**: `_close()` wraps `websocket.close()` in a try/except. All exceptions during close are swallowed.

## Flow

1. **Route entry**: `worker_join_handler()` is called from `main.py` for `GET /ws/worker/join`. Accepts the WebSocket immediately.
2. **Enrollment Step 1**: Receive `ENROLLMENT_REQUEST` with `join_token`, `public_key` (Ed25519 base64), and `fingerprint` (hostname, machine_id, arch, os).
3. **Token validation**: `SecurityManager.decode_join_token()` validates HMAC integrity and TTL. Checked again against the DB for `consumed` flag and `expires_at`.
4. **State check**: Node must be in one of `{PENDING, LOST, STALE, RECONNECTING}`. `REVOKED` is rejected. Transitions to `ENROLLING`.
5. **Challenge/Response**: Master generates a random 32-byte challenge (base64) and sends `ENROLLMENT_CHALLENGE`. Worker must respond with `ENROLLMENT_RESPONSE` containing the Ed25519 signature over the challenge.
6. **Ed25519 verification**: `SecurityManager.verify_ed25519_signature()` checks the signature against the worker's public key. Failure closes with `WS_CLOSE_SIGNATURE_INVALID` (4410).
7. **Atomic DB commit**: Inside a transaction, the token is consumed (`UPDATE join_tokens SET consumed=1 WHERE consumed=0`), node metadata is updated, and a new `worker_token` is inserted.
8. **Connection registration**: Node transitions to `CONNECTED` via `node_manager.transition_state()` with `last_heartbeat` timestamp. The WebSocket object is registered via `node_manager.register_connection()`.
9. **Success response**: `ENROLLMENT_SUCCESS` sent with `worker_token`, `master_public_key`, `node_id`, and `heartbeat_interval`.
10. **Audit**: `log_action(NODE_ENROLLED)` records hostname, arch, os, machine_id, and remote IP.
11. **Operational loop**: Repeatedly receives JSON messages. On `HEARTBEAT`, touches heartbeat timestamp and replies `HEARTBEAT_ACK`. On `INTENT_RESULT`, forwards to `node_manager.resolve_intent()` and audits. On `STATUS_REPORT`, normalizes and hooks into plugins.
12. **Disconnect cleanup**: `finally` block calls `node_manager.unregister_connection()` and regresses state (`CONNECTED -> RECONNECTING`, `ENROLLING -> PENDING`).

## Integration

- Consumed by: `master/main.py` (routes `/ws/worker/join` to `worker_join_handler`), `master/core/node_manager.py` (`register_connection`, `unregister_connection`, `resolve_intent`, `touch_heartbeat`, `transition_state`), Go Worker binary (`worker/main.go` acts as the WebSocket client).
- Depends on: `master/core/security_manager.py` (token encode/decode, Ed25519 verify, challenge generation), `master/core/node_manager.py` (state transitions, connection registry, intent resolution), `master/core/audit.py` (`log_action`), `master/core/plugin_manager.py` (status report normalization + async hooks), `master/db/database.py` (`get_db_conn`, `transaction`), `master/config.py` (`settings.heartbeat_interval`, `settings.trusted_proxies`), `fastapi.WebSocket`, `aiosqlite`.
