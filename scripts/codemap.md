# scripts/

## Responsibility

Test infrastructure and simulation suites for the Vigile platform. Contains a Docker Compose orchestration script that brings up the full stack (Master + N Workers) and two Python test suites that exercise all REST endpoints, WebSocket-driven worker operations, and the Human-in-the-Loop chat proposal flow against a running simulation environment.

## Design

- **setup_test.sh** (133 lines) — Bash orchestration for Docker Compose test environments. Builds images, starts Master with health-check polling (30 retries at 2s intervals), authenticates as admin via `/api/auth/login`, generates join tokens per worker via `/api/nodes/generate-join`, then launches worker containers with injected `JOIN_TOKEN` env vars. Supports `--workers N` (default 1) and `--clean` (stops all containers and volumes). Prerequisites: `docker`, `docker compose`, `jq`.

- **test_all_simulation.py** (195 lines) — Full surface-area test against the simulation worker (port 8002). Uses `urllib.request` exclusively (no external deps). Custom `check()` harness tracks pass/fail counters (~46 checks). Tests 8 areas: METRICS (CPU, MEM, DISK, uptime range validations), SERVICES (list length, by-state breakdown with running/exited/dead/failed counts, specific service name presence), SERVICE STATUS (per-service active state verification for 6 named services), CONTAINERS (list presence, id+name fields), LOGS (syslog OOM detection, SSH failed/accepted attempts, nginx 404/403 responses, MySQL OOM crash), RESTART (mysql.service restart + state recovery), ERROR HANDLING (404 for nonexistent node, graceful 422 for invalid params), AUTH (401 for invalid token, 200 for chat proposals). Runs at module scope.

- **test_complex.py** (165 lines) — Multi-step Human-in-the-Loop chat scenario test. Tests the SSE streaming `/api/chat` endpoint with proposal lifecycle: send natural-language message, parse SSE event stream for `proposal` type events, extract `proposal_id`, then approve via `POST /api/chat/proposals/{id}/approve`. Contains 3 tests: (1) nginx status check + restart proposal, (2) SSH log analysis with failed-attempt detection + remediation proposal, (3) full server health check (CPU, MEM, DISK, services, syslog). Falls back to polling `GET /api/chat/proposals` if no immediate proposal detected. Runs via `main()` guard.

## Flow

1. Run `setup_test.sh` (with optional `--workers N`) to bring up Master and N Worker containers
2. Wait for health check + enrollment handshake to complete (workers transition to `CONNECTED` state)
3. Run `test_all_simulation.py` against port 8002 to validate all endpoint categories pass
4. Run `test_complex.py` against port 8002 to validate the LLM chat + proposal approval flow
5. Tear down with `setup_test.sh --clean` to remove containers and volumes

## Integration

- Consumed by: Developers running integration or end-to-end tests; CI pipeline (if added); manual QA
- Depends on: Docker + Docker Compose + jq (setup_test.sh); Python 3 stdlib (urllib.request, json, time); running simulation worker on port 8002; pre-built `master` and `worker` Docker images; default admin credentials (admin/admin); Master API healthy on localhost:8000
