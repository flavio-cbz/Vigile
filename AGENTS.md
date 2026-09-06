# PROJECT KNOWLEDGE BASE

**Generated:** 2026-08-04T00:00:00+00:00
**Commit:** 2f0cb40
**Branch:** master
**Updated by /init-deep:** root updated, subdirectory files (re)created.

## OVERVIEW
Vigile is a zero-trust fleet management server and agent system. The Python/FastAPI Master node coordinates authenticated operator commands via an LLM agent with human-in-the-loop validation, communicating with autonomous, zero-dependency Go Workers over WebSocket.

## STRUCTURE
```text
master/                  # Control plane FastAPI server
├── api/                 # REST API layer (auth, nodes, services, chat)
├── core/                # Trusted domain logic (state, crypto, LLM, audit)
├── db/                  # Raw SQL SQLite database & Alembic migrations
├── plugins/             # OS systemd/Docker/metrics/disk_analysis telemetry plugins
├── ws/                  # Two-phase WebSocket enrollment & operational connection handler
├── static/              # Compiled React SPA files served directly by FastAPI
worker/                  # Zero-dependency autonomous Go agent binary (DISK_SCAN handler)
frontend/                # React Vite SPA for operator interaction & Copilot (d3-hierarchy treemap)
tests/                   # Pytest test suite (93% coverage)
scripts/                 # Dev launcher and Docker-based simulation tests
docs/                    # Planning, known limits, and session logs
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Core logic (state machine, crypto, audit, LLM, insights, plugin engine) | [master/core/](master/core/) | See [master/core/AGENTS.md](master/core/AGENTS.md) |
| REST API endpoints (auth, nodes, services, chat, admin, audit, demo) | [master/api/](master/api/) | See [master/api/AGENTS.md](master/api/AGENTS.md) |
| Go Worker binary | [worker/](worker/) | See [worker/AGENTS.md](worker/AGENTS.md) |
| Database (pure SQL, migrations, alembic) | [master/db/](master/db/) | Single small dir; see root CODE MAP for `run_migrations`. |
| Plugins (metrics, systemd, docker, disk_analysis, plex, clean_logs) | [master/plugins/](master/plugins/) | See [master/plugins/AGENTS.md](master/plugins/AGENTS.md) |
| WebSocket protocol handler | [master/ws/](master/ws/) | Single dir: `worker_handler.py` (`worker_join_handler`), see root CODE MAP. |
| Pytest test suite | [tests/](tests/) | See [tests/AGENTS.md](tests/AGENTS.md) |
| Simulation & dev launcher | [scripts/](scripts/) | Single dir; see root COMMANDS for invocation. |
| React SPA | [frontend/](frontend/) | See [frontend/AGENTS.md](frontend/AGENTS.md) |

## CODE MAP

| Symbol | Type | Location | Refs | Role |
|--------|------|----------|------|------|
| `SecurityManager` | Class | [security_manager.py](master/core/security_manager.py) | High | Cryptography, JOIN_TOKEN (HMAC), JWT, Ed25519 challenge/response verification |
| `NodeManager` | Class | [node_manager.py](master/core/node_manager.py) | High | Worker lifecycle state machine and active WebSocket registries |
| `PluginManager` | Class | [plugin_manager.py](master/core/plugin_manager.py) | Medium | Hook-based plugin loading and sync/async hook dispatching |
| `RateLimiter` | Class | [rate_limiter.py](master/core/rate_limiter.py) | Medium | Sliding window rate limiting per IP + endpoint with lifespan cleanups |
| `LLMClient` | Class | [llm_client.py](master/core/llm_client.py) | Medium | Native HTTP client for OpenAI-compatible chat completion & streams |
| `StructuredLLM` | Class | [structured_llm.py](master/core/structured_llm.py) | Medium | System prompts for JSON schema validation & LLM retry feedback loops |
| `ActionProposal` | Class | [action_proposal.py](master/core/action_proposal.py) | Medium | Operator-approved action model (PENDING to APPROVED to EXECUTED/FAILED) |
| `DiskScanResult` | Class | [disk_scan.py](master/schemas/disk_scan.py) | Medium | Pydantic v2 schema validating Worker DISK_SCAN output before cache write (fail-closed against malicious workers) |
| `handleDiskScan` | Function | [disk_scan.go](worker/disk_scan.go) | Medium | Go stdlib disk-scan intent handler — dynamic whitelist via `params.mounts`, allocated size via `stat.Blocks×stat.Blksize`, 45s timeout, 2 MB payload cap |
| `DiskAnalysisPlugin` | Class | [disk_analysis/__init__.py](master/plugins/disk_analysis/__init__.py) | Low | Backend+frontend plugin: scheduled DISK_SCAN intents + GrandPerspective-style treemap UI (Tier 2 shipped) |
| `worker_join_handler` | Function | [worker_handler.py](master/ws/worker_handler.py) | High | Entry point router `/ws/worker/join` for worker connections |
| `verify_chain` | Function | [audit.py](master/core/audit.py) | Medium | Full SHA256 chain verification walking the entire audit log table |
| `run_migrations` | Function | [migrations.py](master/db/migrations.py) | Medium | Idempotent table creation, indexes registration, and admin seeder |

## CONVENTIONS
- **No ORM**: Raw SQL text queries via `aiosqlite`.
- **No pyproject.toml**: Only bare `requirements.txt`. Execution relies on setting `PYTHONPATH="."`.
- **DI at edge**: Domain logic constructors in `master/core/` are lightweight and receive raw configuration/arguments, never reading env vars or settings directly.
- **WebSocket Handshake**: Ed25519 challenge-response sequence over raw WS frames implemented from scratch in both Python and Go (zero external WS libraries in Go worker).
- **Dynamic path allow-list (DISK_SCAN)**: The Worker keeps **no static whitelist** of scannable paths. The Master injects `params.mounts` (derived from the Worker's last `STATUS_REPORT.disks[].mount_point`) into each `DISK_SCAN` intent. The Worker validates the requested `path` against this runtime-provided list only, and fails closed if `mounts` is empty/absent. Eliminates the stale-allowlist attack surface (a dismounted `/media/Disque_1` leaves no open door).
- **Allocated on-disk size**: `DiskNode.size` reflects allocated blocks (`stat.Blocks × stat.Blksize` in Go), not the apparent file size. Matches GrandPerspective's "size on disk" semantics and is consistent with `du`.
- **Read-Only Queries (`WorkerQueryPort`)**: Read-only queries (`LIST_SERVICES`, `LIST_CONTAINERS`, `READ_LOGS`, `DISK_SCAN`, `LIST_LOG_FILES`) are routed through `WorkerQueryPort` rather than calling `NodeManager` directly, guaranteeing zero mutation side-effects and preventing direct `send_intent` calls.
- **Declarative Plugin Sandbox**: Built-in system plugins set `"trusted": true` in their `manifest.json`, allowing in-process execution without relying on hard-coded plugin ID strings.
- **Worker Generic Capability Executor**: The Go Worker is a lightweight, paranoid capability executor that ONLY exposes generic OS primitives (`RESTART_SERVICE`, `RESTART_CONTAINER`, `READ_LOGS`, `DISK_SCAN`, `PURGE_MANAGED_PATH`). Plugins live entirely on the Master side (Python/FastAPI) and map domain actions to generic primitives via the Master's Capabilities Registry.

## ANTI-PATTERNS (THIS PROJECT)
- **CORS Wildcard**: CORS origins allow wildcards mapped dynamically via echoing middleware, but must be configured securely in production.
- **Dependency Injection leakage**: Module-level import `from master.config import settings` in `master/api/deps.py` (lines 63, 213) violates DI rules.
- **Sync call of async hooks**: Running async plugin hooks via sync `call()` emits a warning and is ignored. Always use `async_call()`.
- **Database transaction locks**: Shared single aiosqlite Connection; multi-statement mutations must be wrapped in `transaction()` context to prevent sequence conflicts.
- **Dynamic execution**: `compile()` and `exec()` inside `master/api/admin.py:337` allow dynamic python running; access must remain strictly role-gated.
- **DELETE_* intent without fail-closed guardrails**: A future `DELETE_FILES` intent MUST follow the same fail-closed pattern as DISK_SCAN (dynamic `mounts` whitelist, symlink-resolve, Pydantic schema validation of worker output) plus double-confirm operator approval, trash-bin staging, and explicit audit chain entry. Never bypass `ActionProposal` (PENDING → APPROVED → EXECUTED) for any mutation.
- **Per-Plugin Go Binaries / Worker Code Pollution**: Never create per-plugin Go files (e.g. `worker/plex.go`, `worker/nextcloud.go`). The Go worker binary must remain stable, generic, and plugin-agnostic.

## UNIQUE STYLES
- **Hash Chain Audit Trail**: Cryptographically linked logs where each entry contains `SHA256(previous_hash + sequence + data)`.
- **Two-phase WebSocket Enrollment**: challenge-response protocol with `JOIN_TOKEN` verification before operational heartbeats start.
- **Zero-Dependency Go worker**: Raw network socket frame decoding for RFC 6455 WebSocket connectivity without standard library extensions.
- **Copilot Target Resolution**: Before executing `RESTART_CONTAINER`, the Master resolves LLM/operator targets against cached Docker containers, with live `LIST_CONTAINERS` fallback and conservative fuzzy matching. Ambiguous or unknown targets fail closed before Worker restart intent dispatch.
- **Squarified Treemap Vis (DISK_SCAN)**: Frontend uses `d3-hierarchy treemapSquarify()` (Bruls et al. 1999) over a custom SVG `<rect>` renderer — NOT recharts `<Treemap>` which uses the inferior slice-and-dice algorithm. Color gradient amber→red encodes size ratio. Directories drill-down into their subtree. Matches GrandPerspective's reference rendering.

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
- `data/`, `__pycache__`, `.venv/` are gitignored.
- Root `AGENTS.md` + `RULES.md` are tracked in git; subdirectory `AGENTS.md` files (e.g. `master/core/AGENTS.md`) are gitignored to preserve developer workspace preferences.
- SQLite WAL mode enables parallel reads but writes are serialized.
- Auto-generated secrets (`secrets.token_hex(32)`) occur dynamically if config values are blank in development.
- Copilot `RESTART_CONTAINER` proposals normalize `container_id`/`container`/`name`/`target` to canonical `{"container_id": ..., "target": ...}` before persistence when a single safe match exists, and revalidate at approval for legacy pending proposals.
- Disk Analysis plugin (`master/plugins/disk_analysis/`): Visualisation treemap (style GrandPerspective) — Worker `DISK_SCAN` intent (read-only, dynamic `mounts` whitelist fail-closed), Master endpoint `GET /api/nodes/{node_id}/disk-scan` with 5 min cache + Pydantic v2 schema validation + audit chain logging, Frontend `NodeDetailDiskTab` using `d3-hierarchy treemapSquarify` over SVG `<rect>` renderer with drill-down breadcrumb, path selector from `STATUS_REPORT.disks[].mount_point`, admin-gated rescan. Tier 2 (drill-down + Copilot integration + filters) shipped. Tier 3 (snapshots history, diff growth, `DELETE_FILES` intent) is a separate plan.
- DISK_SCAN security review (2026-07-19, self-review after Oracle timeout): **SHIP with notes**. PASS: symlink safety in walk (skip on `os.ModeSymlink`), dynamic whitelist fail-closed (empty `mounts` → reject), Pydantic schema validation rejects unknown fields (`extra="forbid"`) and caps `children` at 100. GAPs: (a) **Rate-limit on `force=true`** — no per-node in-flight lock or `RateLimiter` dep; admin can trigger concurrent 45s scans → worker WS exhaustion. Open a follow-up issue before Tier 3. (b) **Cache write + audit log are separate transactions** — a crash between them leaves cache-without-audit; consistent with existing codebase split-transaction pattern but not ideal. (c) **TOCTOU on `EvalSymlinks` vs `ReadDir`** — low severity, requires root on worker host (which is already a trusted actor). (d) **No Master-side size cap on `result["output"]` before `model_validate_json`** — minor defense-in-depth.
- **Frontend build**: `master/static/assets/` must be rebuilt after any CSS/TSX change (`npm run build` in `frontend/` then copy `dist/assets/*` to `master/static/assets/` and update `master/static/index.html`). Stale builds cause missing CSS classes and black screen in Copilot panel (fixed: added ErrorBoundary around CopilotPanel in RootLayout.tsx).
- **No ErrorBoundary in main.tsx**: any React render error crashes the entire SPA to a blank screen. CopilotPanel is now wrapped in ErrorBoundary; consider wrapping the whole app root eventually.
- **Interactive Recharts tooltip (MetricsTooltip, 2026-08-04)**: Recharts v3 renders the tooltip via portal INSIDE the `recharts-wrapper` div, and that same div carries all mouse handlers (`onMouseMove`/`onMouseEnter`/`onMouseLeave`). Consequence: moving the cursor off the hovered point toward the tooltip card recomputes the active index on every mousemove → the tooltip jumps point-to-point (DOM re-created at the new position) or closes entirely (index null → `active:false` → custom content returns null), making the "Détail" link / event card unclickable. **Fix**: `onMouseMove={(e) => e.stopPropagation()}` on the `MetricsTooltip` Card root — once the cursor enters the card, the chart never sees the mousemove, the index freezes, and the card becomes clickable. Do NOT remove the stopPropagation "as cleanup": it is load-bearing. Related recharts v3 facts: `active` prop forces sticky display, `defaultIndex` is the programmatic index control, `activeIndex` prop was removed in v3.
- **React error #185 (Maximum update depth exceeded) — fixed in CopilotPanel.tsx**: The diagnostic/proposal trigger `useEffect` previously depended on `activeSession` and `isStreaming`, which caused it to re-run whenever `sendMessage()`'s finally block called `fetchSessions()`. `fetchSessions` updated `activeSession` in Zustand, triggering the effect again, which called `sendMessage()` again → infinite loop → error #185. **Fix**: replaced the effect with a `useRef(false)` guard (`triggerProcessedRef`) that tracks whether the trigger has already been processed for the current panel open. The effect now runs once per `copilotContext` change and is immune to `activeSession`/`isStreaming` changes caused by message streaming. Dependencies simplified to `[copilotOpen, copilotContext, sendMessage, nodeId]`.
- **Disk growth estimation is level-shift aware (2026-08-03)**: `master/core/insights.py::_calculate_disk_insight` and `frontend/src/components/node-detail/diskUtils.ts::estimateDiskSaturation` treat IQR-outlier deltas as PERMANENT LEVEL SHIFTS (mass deletion / bulk import), not noise. The series is rebuilt backwards from the latest value ignoring those jumps, so a mass deletion no longer zeroes the growth estimate (previously the −50 GB step dominated the least-squares slope → `max(0, slope)` → 0 Go/jour "Disque stable"). Both implementations mirror each other; a spike (backup written then deleted) still nets out to a flat rebuilt series. Guard: fewer than 3 inlier deltas → "Tendance disque fluctuante" (backend) / growth 0 confidence low (frontend).
- **Destructive Fleet Actions Guardrails (Ticket C2, 2026-09-04)**:
  - Primitives étendues : `STOP_CONTAINER`, `START_CONTAINER`, `DELETE_CONTAINER`, `STOP_SERVICE`, `START_SERVICE`.
  - **Fail-closed & TOCTOU guardrails sur le Worker Go** :
    - `handleDeleteContainer` inspecte l'état du conteneur via `/containers/{id}/json` immédiatement avant suppression. Il refuse si le conteneur n'est pas dans un état terminal (`exited`, `dead`, `created`), si l'ID ne matche pas le préfixe de l'ID résolu, ou si le nom inspecté (après strip du slash initial `/`) ne correspond pas à `container_name`. Paramètres `v=false&force=false` strictement codés en dur (pas de suppression de volumes ni d'écrasement brutal).
    - `handleStopService` / `handleStartService` imposent la regex de nom de service `^[a-zA-Z0-9_.@-]{1,128}$` et sanitizent les arguments via `--` dans `exec.CommandContext("systemctl", action, "--", service)`.
    - `protectedServices` whitelist côté Worker (`ssh`, `sshd`, `docker`, `dockerd`, `containerd`, `networking`, `systemd-networkd`, `NetworkManager`, `systemd-resolved`, `systemd-journald`, `systemd-logind`, `dbus`, `vigile`, `vigile-worker`) et Master (`PROTECTED_SERVICES`). `canonicalServiceName` applique `ToLower()` AVANT `TrimSuffix(".service")`.
  - **Contrôle d'accès & Audit Hash Chain** :
    - `DELETE_CONTAINER`, `STOP_CONTAINER` et `STOP_SERVICE` sont **strictement réservés au rôle admin** (les opérateurs reçoivent HTTP 403). Tout rejet d'un opérateur ou tentative sur un service protégé est enregistré immédiatement dans la hash-chain SHA256 avec `AuditAction.SECURITY_INCIDENT`.
    - `START_CONTAINER` et `START_SERVICE` sont autorisés aux opérateurs.
    - `DELETE_CONTAINER` est **EXCLU** de `copilot_actions` dans le manifest du plugin Docker (jamais proposé automatiquement par le LLM). `STOP_CONTAINER` et `STOP_SERVICE` sont classés sévérité `HIGH`.
  - **Frontend UI & Modal Pattern** :
    - La confirmation de suppression destructrice utilise un `ConfirmDeleteModal` unique et centralisé monté au niveau de la page (`DockerContainers.tsx`), avec saisie exacte obligatoire du nom du conteneur (jamais 80 modals instanciés dans chaque `ActionButtonRow`).
    - Masquage proactif des actions de stop pour les services critiques et pour les utilisateurs non-admins.


## AUDIT FINDINGS (2026-06-04)
File-by-file audit (4 specialists + cross-critique + Oracle verification) found **79 issues** the 8 audit documents in `docs/` missed:
- **Cross-cutting**: 8 mega-issues (e.g., no TLS anywhere, no fix enforcement, no worker concurrency)
- **Backend**: 13 new issues (require_role bypasses must_change_password/is_active, migration stamping broken)
- **Worker**: 10 new issues (no TLS, no exec timeouts, frame parse panic)
- **Frontend**: 18 new issues (zero AbortSignal, stale closures, localStorage token bypass)
- **Infra**: 30 new issues (live API key in .env, zero Go/frontend tests, CI no pre-commit/securité)

Full report: `.sisyphus/reports/audit-missed-report.md`

## AUDIT FIXES (2026-08-04)
Corrections de l'audit `vigile_audit.md` appliquées et vérifiées (21 fichiers, suite complète **579 passed / 2 deselected**). Points notables entrés dans la mémoire projet :
- `hook_bus.py`: `except Exception` → `except BaseException` dans `call()`/`call_first()` (ne pas avaler KeyboardInterrupt/SystemExit) ; `unregister()` prunes `_metrics`.
- `circuit_breaker.py`: `reset()` est **async** (sous `_lock`) — tout appelant sync doit être migré.
- `plugin_engine.py`: classe `_Lifecycle` supprimée (zéro référence) ; `_scan_py_file` version sentinelle `0.0.0` ; validation zip-slip + `manifest.id` traversal.
- `structured_llm.py`: paramètre renommé `max_retries` → `max_attempts` (API publique — caller `chat_stream.py:712` + tests mis à jour) ; stripping `<think>` en boucle (imbriqués).
- `outbox.py`: claim `processed=2` anti-double-sweep + reset en échec ; `replay_unprocessed` reset les claims orphelins ; sémantique at-least-once documentée.
- `security_manager.py`: `ExpiredTokenError(SecurityError, ValueError)` (MRO double pour compat `except ValueError`) ; `load_or_generate_master_key` utilise `O_EXCL` + re-read sur course.
- `alert_engine.py`: `_alert_rate_limiter` clés composites `f"{node_id}:{alert_name}"` — purge par préfixe dans `cleanup_orphaned_alerts` (le `pop(nid)` nu ne matchait jamais) ; auto-résolution `node_reboot_detected`/`node_connection_flap` ; doublon `cpu_high_load` supprimé (== `cpu_load_per_core_high`).
- `investigation_manager.py`: DI via paramètre constructeur `insights` + `set_insights()` (plus d'import `master.api.deps`) ; statut `'skipped'` persisté.
- `insights.py`: `_generate_profile_with_own_connection` — le fallback pool doit attraper `RuntimeError` en plus de `TimeoutError` (queue module-level liée à un event loop antérieur en environnement de test).
- `worker_query_port.py`: 4 méthodes read-only déléguent à `query()` (chemin unique).
- Rejetés : `proposal_dispatcher` PD-2 (stub `send_intent()` volontaire), PD-3 (code mort), `proposal_autoexpire` AE-1 (faux positif).

Full report: `vigile_audit.md`

## FIELD VALIDATION 2026-06-17 (youcloud.ovh, prod stack)
Live test of the worker against the production deployment on youcloud.ovh:

**Stack state** (before test): master `youcloud-master-1` running 4 weeks, BDD persisted on `vigile_data` volume. Worker `youcloud-persistent` running with an **expired** JOIN_TOKEN (exp 2026-05-15 22:34 UTC) — crashlooping on `peer closed connection` because the master rejects the stale token. `connected_nodes: 0`.

**Fresh test worker** (`node_id: 13d2e23a-4eee-43dd-a00b-d43bd179c29c`, name `test-worker-1`):
- WebSocket upgrade against `http://master:8000/ws/worker/join` — **OK**
- Ed25519 challenge/response (44-byte challenge, 32-byte raw signature) — **OK**
- Node appears in `/api/nodes` as `state: CONNECTED, online: true` — **OK**
- Plugin intents dispatched successfully:
  - `LIST_SERVICES` → 39 services returned (mysql: failed, prometheus: failed, ssh: active/running, etc.)
  - `LIST_CONTAINERS` → 40 containers returned
  - `READ_LOGS` → syslog tail returned
  - `STATUS_SERVICE ssh.service` → `{"active": "active", "enabled": "enabled"}`
- All intents completed `success=true`.

**BUG DISCOVERED — Worker env var mismatch** (worker/main.go:23-28):
- The Go binary reads `MASTER_URL` and `JOIN_TOKEN` **only** via `--master` and `--token` CLI flags (or via `/etc/vigile/master_url` and `/etc/vigile/enrollment.token` files).
- The `docker-compose.yml` declares these as **environment variables** (`MASTER_URL=http://master:8000` on the `worker` service) but the binary **ignores them entirely**.
- `docker compose run --rm -e JOIN_TOKEN=... worker` from `setup_test.sh` only works if the container inherits `--master` and `--token` args from the service definition; it does NOT.
- The historical `youcloud-persistent` container has `--master http://master:8000 --token <...>` in `Config.Cmd` (set at creation time by Compose), which is why it worked.
- **Fix candidates** (none applied — needs design decision):
  1. Add `os.Getenv("MASTER_URL")` and `os.Getenv("JOIN_TOKEN")` fallbacks in `worker/main.go` after `flag.Parse()`
  2. Modify `setup_test.sh` to override `--entrypoint` with full arg list (what I used: `--entrypoint "/usr/local/bin/vigile-worker --master http://master:8000 --token $TOKEN"`)
  3. Modify `docker-compose.yml` `worker` service to set `command: ["--master", "http://master:8000"]`

**Worker `vigile-test-worker-1` and `vigile-debug-worker` containers were cleaned up manually**. The historical `youcloud-persistent` was preserved. Master was inadvertently stopped+removed by `docker compose down --remove-orphans` (cleanup mistake) and was immediately restored with `docker compose up -d master`. BDD is intact.

## WORKER BINARY DISTRIBUTION ISSUE — 2026-07-25

**Problem**: `https://vigile.youcloud.ovh/api/nodes/binary/linux/arm64/worker` returns 404 when running the kickstart script on an arm64 machine (e.g. `NetHunter-ServerV3`). The production `manifest.json` only listed `linux/amd64` — no `linux/arm64`.

**Root cause**: Production `docker-compose.yml` overrides `WORKER_BINARY_MANIFEST_URL` to `file:///var/cache/vigile/worker/manifest.json`, which requires pre-built binaries in `./data/worker-dist/` (gitignored). The production `data/worker-dist/` was only ever populated for `linux/amd64` via an older manual process that also used a flat path format (`worker-linux-amd64`) instead of the current structured format (`linux/amd64/worker`). The `data/worker-dist/` directory must be rebuilt with all target architectures whenever a new architecture is needed or the build script changes.

**Fix** (applied on production server vigile.youcloud.ovh):
```bash
cd ~/Docker-Compose/vigile
./scripts/build_worker.sh          # rebuilds all 4 targets including linux/arm64
docker compose down master         # full teardown required — restart/recreate does NOT refresh bind mounts
docker compose up -d master        # picks up new manifest + binaries from data/worker-dist/
```

> **Note**: `docker compose restart master` and `docker compose up -d master --force-recreate` do NOT reliably refresh bind-mounted volumes on the production server. Only `docker compose down` + `up` guarantees the container sees the new host files. See `docs/architecture/worker-deployment.md` for the full 404 troubleshooting procedure.

**Prevention**: The improved `_fetch_and_cache` error in `worker_binary.py` now lists available architectures in the 404 detail message, making it immediately clear which architectures are missing and prompting the operator to rebuild.

**Key files**:
- Build script: `scripts/build_worker.sh` (targets: linux/amd64, linux/arm64, darwin/arm64, freebsd/amd64)
- Deployment: `docker-compose.yml` volume `./data/worker-dist:/var/cache/vigile/worker`
- Manifest format: `data/worker-dist/manifest.json` with structured paths (`linux/arm64/worker`)
- Production manifest endpoint: `GET /api/nodes/binary/manifest.json`

## PAGE UNIFICATION (2026-08-16)
Unification visuelle des tops de page du SPA sur toutes les vues (identité tokenisée multi-thèmes, zéro couleur codée en dur) :
- **`PageHeader` est LE composant canonique d'en-tête** (`frontend/src/components/blocks/PageHeader.tsx`) : props `{title, subtitle?, icon?, actions?, badge?, back?: {label?, onClick}, className?}`. Style : boîte icône `w-10 h-10 rounded-xl bg-accent/10 border border-accent/20 text-accent`, titre `font-interface text-xl font-extrabold tracking-wider uppercase text-text-1` (span `truncate`), sous-titre `text-[10px] text-text-3 font-semibold uppercase tracking-wider mt-0.5`, `border-b border-border-strong/20 pb-5`, back pill (`self-start inline-flex ... rounded border bg-surface hover:bg-surface-2`). Ne plus créer d'en-têtes "main de" ailleurs.
- **Wrapper standard** : `mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 space-y-6 pb-12 animate-fade-in` (Proposals/Settings gardent `max-w-4xl`/`max-w-5xl` ; EventDetail/DockerContainerDetail `max-w-4xl`). `<main>` de RootLayout possède déjà `p-6` → les pages n'ajoutent plus de padding horizontal.
- **Bouton d'action pill canonique** : `inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg border border-border-strong/50 bg-surface-2 hover:bg-surface-hover/80 text-text-1 font-mono text-xs font-semibold uppercase tracking-wider transition-colors duration-150 disabled:opacity-50 cursor-pointer` (primaire : `bg-accent hover:bg-accent-hover text-bg`).
- **Pages concernées** : ServersPage, PluginsPage, ProposalsPage, SettingsPage, EventDetailPage (badge sévérité tokenisé `bg-severity-*/10`, back), DockerContainerDetail (back), SystemdServices/DockerContainers/MetricsHistory/PlexAdmin (icônes `w-5` héritant `text-accent`, `fill-accent` pour le logo Plex), PluginRouter (zinc → tokens). Dashboard/Login restent des designs distincts volontairement.
- **TopBar `getPageTitle()`** : le breadcrumb résout maintenant `/servers`, `/plugins`, `/plugins/*` (titres via `usePluginStore().pages` match `plugin_id` — keys `page_title.servers/plugins`, fallback plugins) — plus de « CONSOLE / CONSOLE » sur ces routes.
- **Bouton refresh Proposals** : pas de clé i18n `prop_page.refresh` → pill icon-only (RefreshCw) — ne pas ajouter de texte inline (pas d'inline strings, convention i18n).
- Build recopié : `frontend/dist/` → `master/static/` (index.html + assets/* + favicon/icons.svg), comme le fait `Dockerfile.master` (COPY sans purge des anciens bundles).

## TEST ENVIRONMENT COMPATIBILITY (2026-08-17)
- **vitest 4.x ↔ vite 8.x incompatibles** : `vite@^8.2.0` + `vitest@^4.1.10` cause `TypeError: Cannot destructure property 'startVitest'`. Vitest 4.x requires vite 5.x. Use `vite@^5.4.0` + `vitest@^4.1.10` for testing.
- **jsdom 30.x ↔ vitest 4.x incompatibles** : jsdom 30.x prevents the jsdom environment from loading (`setup 0ms`, `environment 0ms`, `document is not defined`). Use `jsdom@26.x` or lower.
- **@vitejs/plugin-react 6.x requires vite ^8.0.0** : incompatible with vite 5.x. Use `@vitejs/plugin-react@^4.5.0` when downgrading vite.
- **Missing peer dep** : `@testing-library/jest-dom@7.x` requires `@testing-library/dom` as peer dep but `--legacy-peer-deps` skips it. Install `@testing-library/dom@^9` manually.
- **Running vitest** : use `node node_modules/vitest/vitest.mjs run --environment=jsdom` (bypasses npx downloading a fresh incompatible vitest).

## LOG BROWSER + TAIL READING (2026-08-18)
Réponse aux plaintes logs : `Error: log file too large` sur journalctl (fichier 16,5 Mo), fichiers exclus, navigation complexe.
- **Worker `tailFile`** (`worker/logs.go`) : remplace la lecture complète (`os.ReadFile` + cap 10 Mo supprimé) par un tail en fenêtre glissante — chunks arrière de 64 Ko, `maxTailWindow = 4 Mo`, `maxTailLines = 2000`, marqueur `[truncated: tail window exceeded 4194304 bytes]` si la fenêtre est dépassée. Les gros fichiers (journal, logs conteneurs) sont lisibles sans erreur de taille.
- **Intent `LIST_LOG_FILES`** : listing JSON `{"files":[{"path","size","mtime"}],"truncated"}` (mtime en secondes Unix), profondeur ≤ 3, ≤ 500 entrées, ignore symlinks + `*.journal` (binaires — journalctl reste le lecteur). Enregistré dans `dispatcher.go` ALLOWED_ACTIONS. Walk multi-racines via `logListRoots = ["/var/log", "/var/lib/docker/containers"]` + `listLogFilesFromRoots` (racine absente ignorée, tri global mtime desc, troncature inter-racines).
- **Invariant de sécurité** : `logListRoots` DOIT rester synchronisé avec `allowedLogPrefixes` — toute racine listée doit être lisible, sinon l'UI liste des fichiers que le worker refuse de lire. Préfixes worker : `/var/log/`, `/var/log/journal/`, `/var/lib/docker/containers/` (bornes strictes : `path == prefix || strings.HasPrefix(path, prefix)`).
- **Master** : `GET /api/nodes/{node_id}/log-files` (operator+, read-only, sans audit entry) via `WorkerQueryPort.list_log_files` ; `ALLOWED_LOG_PREFIXES = ("/var/log/", "/var/lib/docker/containers/")` avec borne stricte `clean == base || startswith(base + "/")` → rejette `/var/log_backup`, `/var/lib/docker/containers_evil` ; 403 hors préfixe, 503/504 sur échec/timeout worker ; mode démo = listing synthétique. Appliqué à `nodes.py` (live) ET `nodes_management.py` (miroir dead-code — voir master/api/AGENTS.md).
- **Frontend** : `NodeDetailLogsTab` redessiné — contrôle segmenté **Services / Fichiers** ; mode Fichiers = liste groupée par dossier (tri mtime desc) + recherche par nom + taille/date par fichier + sélection → lecture via `path` ; bannière d'erreur `Banner` (`logsError` du hook) ; note de troncature affichée **uniquement** si `LogFilesResponse.truncated` (plombé depuis le worker). `useNodeDetailData` expose `logFiles`, `logFilesTruncated`, `loadingLogFiles`, `logsPath`/`setLogsPath`, `logsError`, `fetchLogFiles`.
