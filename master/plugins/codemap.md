# master/plugins/

## Responsibility

Master-side plugin modules that declare Worker-supported actions and validate their responses. The metrics plugin additionally normalizes and persists periodic STATUS_REPORT messages from Workers into the `metrics_snapshots` SQL table. Each plugin maps to a Worker concern (system metrics, systemd services, Docker containers) and auto-registers via `PluginManager.load_plugins_from_dir()` at startup with zero config changes.

## Design

- **One file, one concern**: `metrics_plugin.py` (272 lines), `systemd_plugin.py` (80 lines), `docker_plugin.py` (64 lines). No monolithic plugin file.
- **Hook-based dispatch**: `PluginManager` uses a dict `{hook_name: [(plugin_name, callable)]}`. Three hook points exist: `get_supported_actions` (sync, declares action names), `normalize_status_report` (sync, validates raw report into a Pydantic model dict), `on_status_report` (async, persists to DB).
- **Pydantic response validation**: `MetricsSnapshot`, `ServiceInfo`, `ServiceStatus`, and `ContainerSummary` models define the schema for Worker responses. Validation happens on the Master side after receiving raw JSON from the Worker via WebSocket.
- **Minimal Master-side logic**: systemd and docker plugins only declare action names and provide `parse_*` helper functions for response validation. They register only the `get_supported_actions` hook. Actual execution happens in the Worker Go binary.
- **Graceful degradation**: `_on_status_report` accepts `db=None` and skips persistence with a debug log. `PluginManager.call_first()` returns `None` when no hook is registered, never crashes.
- **Nested report support**: `_normalize_status_report` accepts both flat `{cpu_percent: ...}` and nested `{metrics: {...}}` formats, extracting via `raw_report.get("metrics", raw_report)`.
- **No filesystem I/O at import time**: `register()` only registers hooks, no startup logic. I/O-bound initialization (DB writes) happens in async hook handlers.
- **Dynamic scanning**: `PluginManager.load_plugins_from_dir()` uses `importlib.util.spec_from_file_location` to load any `*.py` file not prefixed with `_` that exports a `register(pm)` function.

## Flow

1. **Startup**: `main.py` calls `plugin_manager.load_plugins_from_dir(settings.plugins_dir)`, which scans `master/plugins/`, imports each module, and calls its `register(pm)` function.
2. **Action declaration**: Each plugin's `register()` calls `pm.register("get_supported_actions", handler, plugin_name="...")`. At runtime, `worker_handler.py` can call `pm.call_first("get_supported_actions")` to discover all Worker-supported actions and compare against the hardcoded whitelist in `worker/dispatcher.go`.
3. **STATUS_REPORT ingestion**: Worker sends `{"type": "STATUS_REPORT", "metrics": {...}}` over WebSocket. `worker_handler.py` calls `pm.call_first("normalize_status_report", raw_report=msg)` to validate and transform the raw dict into a `MetricsSnapshot`-validated dict.
4. **Metrics persistence**: If normalization succeeds, `worker_handler.py` calls `await pm.async_call("on_status_report", node_id=node_id, snapshot=snapshot, db=db)`. The metrics plugin's `_on_status_report` inserts a row into the `metrics_snapshots` table via raw SQL INSERT.
5. **Action dispatch**: For operational actions (LIST_SERVICES, RESTART_CONTAINER, etc.), the Worker receives the action name via WebSocket, dispatches to the appropriate handler in `dispatcher.go`, and returns JSON results. The Master-side plugins are not involved in execution, only action declaration and optional response validation via `parse_*` helpers.
6. **Async dispatch**: `PluginManager.async_call()` runs all registered hook implementations concurrently via `asyncio.gather()`. Sync functions run in the event loop's thread pool executor. Async coroutines run as created tasks. Exceptions are logged and collected, never propagated.

## Integration

- **Consumed by**:
  - `master/ws/worker_handler.py` -- calls `normalize_status_report` and `on_status_report` hooks during STATUS_REPORT processing in `_run_operational()`
  - `master/main.py` -- calls `load_plugins_from_dir()` during application lifespan startup
  - `master/core/plugin_manager.py` -- `PluginManager` is the host that invokes all hooks
  - `worker/dispatcher.go` -- hardcoded action whitelist (`GET_STATS`, `LIST_SERVICES`, `STATUS_SERVICE`, `RESTART_SERVICE`, `LIST_CONTAINERS`, `RESTART_CONTAINER`) mirrors the plugin-declared actions
  - `tests/unit/test_plugins.py` -- 495 lines, 93 `check()` calls testing all plugins in isolation

- **Depends on**:
  - `pydantic.BaseModel` + `Field` -- used by all three plugins for response schemas (`MetricsSnapshot`, `ServiceInfo`, `ServiceStatus`, `ContainerSummary`)
  - `master/core/plugin_manager.py` (`PluginManager`) -- provides the `register()` API and `call()`/`async_call()` dispatch
  - `master/config.py` -- `settings.plugins_dir` provides the filesystem path for plugin scanning
  - Standard library: `logging`, `time`, `uuid`, `json`, `typing`, `asyncio`, `importlib.util`, `inspect`, `os`
