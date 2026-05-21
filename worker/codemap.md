# worker/

## Responsibility

A zero-dependency Go binary that runs on target servers, establishes a WebSocket connection to the Master, authenticates via Ed25519 challenge/response, and executes a hardcoded whitelist of remote actions (system metrics, log reading, Docker container management, systemd service control). It is the on-premise agent that the Master uses to manage remote nodes.

## Design

- **Stdlib-only**: Zero external imports. Full RFC 6455 WebSocket handshake and frame I/O implemented by hand using `net.Conn`, `bufio`, `crypto/rand`, `crypto/sha1`, `encoding/base64`, and `encoding/binary`.
- **Single flat package**: All files in `package main`. No internal sub-packages, no shared libraries. The binary is built from a single directory.
- **Ed25519 identity**: Each worker generates or persists an Ed25519 keypair under `/etc/vigile/`. The public key is sent during enrollment; the private key signs the challenge from the Master.
- **JOIN_TOKEN auth**: A single-use HMAC token (consumed by the Master on first use) gates enrollment. After successful enrollment, the token cannot be reused, and disconnection means the worker must be re-provisioned.
- **Exponential backoff with jitter**: Before enrollment, reconnection backs off from 1s to 5min max. After enrollment, any disconnect is terminal (token consumed), so backoff is pre-enrollment only.
- **Hardcoded action whitelist**: 8 allowed actions (`GET_STATS`, `READ_LOGS`, `RESTART_CONTAINER`, `LIST_CONTAINERS`, `LIST_SERVICES`, `STATUS_SERVICE`, `RESTART_SERVICE`, `READ_LOGS_SERVICE`). Any unknown action is rejected before execution.
- **State machine**: Three states: `stateDisconnected` (0), `stateConnecting` (1), `stateOperational` (2). Transition guarded by mutex.
- **Heartbeat + status tickers**: 30s heartbeat, 90s read deadline (3x heartbeat), 60s STATUS_REPORT with full metrics snapshot.
- **No goroutine leaks**: All goroutines are tracked; the read goroutine exits on error/stop, and the main loop in `RunOperational` uses `select` on heartbeat/status/msg/stop channels.
- **Linux-only runtime**: Metrics (`/proc/stat`, `/proc/meminfo`, `/proc/loadavg`, `/proc/uptime`), Docker Unix socket (`/var/run/docker.sock`), systemd (`systemctl`, `journalctl`). macOS detection exists in discovery but no macOS metric collection.
- **Log path security**: File-based log reading restricted to `/var/log/` and `/var/log/journal/` prefixes.

## Flow

1. **Startup**: `main()` parses `--master` and `--token` flags (or reads from `/etc/vigile/`). Normalizes the URL scheme (http/https/ws/wss to http for WebSocket upgrade). Loads or generates Ed25519 keypair. Collects fingerprint (hostname, machine-id, arch, OS). Registers SIGINT/SIGTERM handlers.
2. **Connection loop**: `RunWithBackoff()` enters a loop. Before enrollment, it attempts `Connect()` with exponential backoff (1s doubling to 5min max, checked against `stopCh` between attempts).
3. **WebSocket dial**: `Connect()` calls `DialWebSocket(masterURL + "/ws/worker/join")`. This opens a raw TCP connection, sends the HTTP upgrade request (GET with `Upgrade: websocket`, `Sec-WebSocket-Key`), and parses the 101 response manually (avoiding `net/http.ReadResponse` quirks). Returns a `WSConn` wrapping the `net.Conn` with a shared `bufio.Reader`.
4. **Enrollment handshake**: `runEnrollment()` sends `ENROLLMENT_REQUEST` (join_token + public_key + fingerprint). Master replies with `ENROLLMENT_CHALLENGE` (base64-encoded random bytes). Worker decodes, signs with Ed25519, sends `ENROLLMENT_RESPONSE` (signature). Master replies with `ENROLLMENT_SUCCESS` (node_id + worker_token). State transitions to `stateOperational`.
5. **Operational loop**: `RunOperational()` spawns three concurrent paths via `select`:
   - **Heartbeat ticker** (30s): Sends `{"type": "HEARTBEAT", "ts": <unix-ms>}`.
   - **Status ticker** (60s): Calls `buildStatusReport()` (collects CPU/mem/disk/uptime/processes from `/proc`), sends as `STATUS_REPORT`.
   - **Read goroutine**: Dedicated goroutine reads WebSocket frames with a 90s read deadline. Incoming messages are JSON-unmarshalled and type-routed:
     - `HEARTBEAT_ACK`: No-op (acknowledgment).
     - `INTENT`: Passed to `dispatchIntent()`, which checks the action whitelist, routes to the appropriate handler (`handleGetStats`, `handleReadLogs`, `handleListContainers`, etc.), and sends back `INTENT_RESULT` with `{intent_id, success, output, error}`.
6. **Shutdown**: SIGINT/SIGTERM closes `stopCh`, which unblocks `RunOperational()` and `RunWithBackoff()`. Worker sends a close frame, closes TCP, and exits. After successful enrollment, any connection loss is also terminal (worker exits cleanly).
7. **Action handlers** each execute the corresponding OS-level operation and return `IntentResult`. `mustJSON()` panics on marshal failure (should never happen for known structs).

## Integration

- Consumed by: Master WebSocket endpoint (`/ws/worker/join`) in `master/ws/worker_handler.py`. The Master initiates enrollment, sends intents, and receives status reports via this worker.
- Depends on: Linux kernel (`/proc` filesystem), Docker Engine Unix socket (`/var/run/docker.sock`), systemd (`systemctl`, `journalctl`), `/etc/vigile/` for persisted keys and config. No external Go modules.
