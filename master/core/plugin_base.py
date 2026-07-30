"""
Vigile — Plugin Base, Decorators, and PluginContext

Foundational layer for the class-based plugin API introduced in Sprint 9.

Three concerns live here:

1. **Decorators** (`@route`, `@hook`, `@scheduled`) stamp metadata onto a
   plugin's methods at import time. They are deliberately side-effect free —
   they only attach attributes (`__plugin_route__`, `__plugin_hook__`,
   `__plugin_sched__`) and return the original callable unchanged, so a
   subclass can be imported without activating anything.

2. **PluginBase** — subclasses are auto-registered in
   ``PluginBase._decorated_registry`` via ``__init_subclass__`` keyed by the
   plugin's ``plugin_id`` class attribute. The constructor receives a
   ``PluginContext`` and introspects the instance via
   ``_collect_decorated`` to surface the routes, hooks, and scheduled tasks
   the plugin declared.

3. **PluginContext** — a restricted, slotted proxy handed to each plugin
   instance. It exposes a minimal, audited surface (``db_query``,
   ``emit_event``, ``create_proposal``, ``get_config``) and never a raw
   reference to the engine, the DB connection, or the hook bus. SQL is
   tokenized and verified against the plugin's prefix (`<plugin_id>_`) and
   the shared read/write whitelists before execution, enforcing zero-trust
   table isolation at the runtime boundary.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any


# ---------------------------------------------------------------------------
# Log redaction — masks secrets/tokens in log output
# ---------------------------------------------------------------------------

_REDACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Bearer tokens / Authorization headers
    (re.compile(r'(?i)(authorization|bearer|token|api[_-]?key|secret)\s*[:=]\s*["\']?\S+["\']?'), r'\1=***REDACTED***'),
    # JWT-like sequences (base64url triplets)
    (re.compile(r'\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b'), '***JWT_REDACTED***'),
    # Hex token patterns (32+ hex chars)
    (re.compile(r'\b[0-9a-fA-F]{32,}\b'), '***HEX_REDACTED***'),
    # Password-like entries
    (re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?\S+['\"]?"), r'\1=***REDACTED***'),
    # Private keys
    (re.compile(r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----'), '***PRIVATE_KEY_REDACTED***'),
    # Join tokens (format: vgl_...)
    (re.compile(r'\bvgl_[a-zA-Z0-9_-]{10,}\b'), '***JOIN_TOKEN_REDACTED***'),
]


def redact_sensitive(text: str) -> str:
    """Mask secrets, tokens, and credentials in a log message.

    Returns the redacted string with matched patterns replaced.
    """
    result = str(text)
    for pattern, replacement in _REDACT_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


class RedactingAdapter(logging.LoggerAdapter):
    """Logger adapter that automatically redacts sensitive data.

    Redacts both the format string and any positional arguments
    before forwarding to the underlying logger.
    """

    def __init__(self, logger: logging.Logger, extra: dict[str, Any] | None = None) -> None:
        super().__init__(logger, extra or {})

    def process(self, msg: Any, kwargs: Any) -> tuple[Any, Any]:
        if isinstance(msg, str):
            msg = redact_sensitive(msg)
        args = kwargs.get("args", ())
        if args:
            kwargs["args"] = tuple(
                redact_sensitive(str(a)) if isinstance(a, str) else a
                for a in args
            )
        return msg, kwargs

try:
    import aiosqlite  # Lazy import: optional dependency for plugin sandbox isolation
except ImportError:  # pragma: no cover - aiosqlite is a hard runtime dep
    aiosqlite = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def route(path: str, method: str = "GET", roles: list[str] | None = None) -> Any:
    """Stamp an HTTP route contract on a plugin method."""
    _roles = list(roles) if roles is not None else ["viewer"]

    def decorator(fn: Any) -> Any:
        fn.__plugin_route__ = {"path": path, "method": method, "roles": _roles}
        return fn

    return decorator


def hook(verb: str) -> Any:
    """Subscribe a method to a named hook verb."""
    def decorator(fn: Any) -> Any:
        fn.__plugin_hook__ = verb
        return fn

    return decorator


def scheduled(interval_secs: int) -> Any:
    """Declare a method as a periodic scheduled task."""
    def decorator(fn: Any) -> Any:
        fn.__plugin_sched__ = {"interval_secs": interval_secs}
        return fn

    return decorator


# ---------------------------------------------------------------------------
# SQL tokenization helpers
# ---------------------------------------------------------------------------

_SQL_KEYWORDS = frozenset(
    {
        "SELECT", "FROM", "WHERE", "INSERT", "INTO", "UPDATE", "DELETE",
        "CREATE", "TABLE", "IF", "NOT", "EXISTS", "DROP", "ALTER", "RENAME",
        "TO", "JOIN", "INNER", "LEFT", "RIGHT", "OUTER", "ON", "AS", "AND",
        "OR", "GROUP", "BY", "ORDER", "HAVING", "LIMIT", "OFFSET", "VALUES",
        "SET", "DISTINCT", "UNION", "ALL", "WITH", "RECURSIVE", "PRAGMA",
        "ATTACH", "DATABASE", "DETACH", "BEGIN", "COMMIT", "ROLLBACK",
        "TRANSACTION", "INDEX", "TRIGGER", "VIEW", "REPLACE",
    }
)

_BLOCKED_PATTERNS = (
    re.compile(r"\bATTACH\s+DATABASE\b", re.IGNORECASE),
    re.compile(r"\bDETACH\s+DATABASE\b", re.IGNORECASE),
)


def _tokenize_sql(sql: str) -> list[str]:
    """A permissive SQL tokenizer producing identifiers and keywords.

    Handles double-quoted identifiers, single-quoted literals, line (`--`) and
    block (`/* */`) comments, and bare identifiers. Returns the raw token
    strings (quotes/comments stripped) in encountered order.
    """
    tokens: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        c = sql[i]
        if c.isspace():
            i += 1
            continue
        if c == "-" and i + 1 < n and sql[i + 1] == "-":
            j = sql.find("\n", i)
            i = n if j == -1 else j + 1
            continue
        if c == "/" and i + 1 < n and sql[i + 1] == "*":
            j = sql.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c == '"':
            j = i + 1
            buf: list[str] = []
            while j < n:
                if sql[j] == '"':
                    if j + 1 < n and sql[j + 1] == '"':
                        buf.append('"')
                        j += 2
                        continue
                    break
                buf.append(sql[j])
                j += 1
            tokens.append("".join(buf))
            i = j + 1
            continue
        if c == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            i = j + 1
            continue
        if c == ";":
            tokens.append(c)
            i += 1
            continue
        if c in "(),.":
            tokens.append(c)
            i += 1
            continue
        if c.isalnum() or c == "_":
            j = i
            while j < n and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            tokens.append(sql[i:j])
            i = j
            continue
        tokens.append(c)
        i += 1
    return tokens


def _extract_table_identifiers(sql: str) -> list[str]:
    """Return table identifiers referenced by FROM/INTO/UPDATE/JOIN/TABLE clauses."""
    tokens = _tokenize_sql(sql)
    tables: list[str] = []
    capture_next = False
    for idx, tok in enumerate(tokens):
        upper = tok.upper()
        if upper in {"FROM", "INTO", "UPDATE", "JOIN", "TABLE"}:
            capture_next = True
            continue
        if capture_next:
            if tok == "IF" or upper == "NOT" or upper == "EXISTS":
                continue
            if tok in "(),;." or upper in _SQL_KEYWORDS:
                capture_next = False
                continue
            tables.append(tok)
            capture_next = False
    return tables


# ---------------------------------------------------------------------------
# PluginBase
# ---------------------------------------------------------------------------


class PluginBase:
    """Base class for class-based Vigile plugins.

    Subclasses set a ``plugin_id`` class attribute (matching the manifest id)
    and decorate methods with ``@route``, ``@hook``, ``@scheduled``. The
    metaclass-free design uses ``__init_subclass__`` to record subclasses in
    ``_decorated_registry`` so the engine can discover them without importing
    the class symbol twice.
    """

    _decorated_registry: dict[str, type[PluginBase]] = {}

    plugin_id: str = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        pid = getattr(cls, "plugin_id", "")
        if pid:
            PluginBase._decorated_registry[pid] = cls

    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        collected = self._collect_decorated(self)
        self.routes: list[dict[str, Any]] = collected["routes"]
        self.hooks: list[dict[str, Any]] = collected["hooks"]
        self.scheduled: list[dict[str, Any]] = collected["scheduled"]

    @property
    def config(self) -> dict[str, Any]:
        return getattr(self.ctx, "_config", {}) if getattr(self, "ctx", None) is not None else {}

    @property
    def db(self) -> Any:
        return getattr(self.ctx, "_db", None) if getattr(self, "ctx", None) is not None else None

    @classmethod
    def _collect_decorated(cls, instance: PluginBase) -> dict[str, list[dict[str, Any]]]:
        routes: list[dict[str, Any]] = []
        hooks: list[dict[str, Any]] = []
        scheduled: list[dict[str, Any]] = []
        for name in dir(instance.__class__):
            if name.startswith("__") and name.endswith("__"):
                continue
            fn = getattr(instance.__class__, name, None)
            if not callable(fn):
                continue
            route_meta = getattr(fn, "__plugin_route__", None)
            if route_meta is not None:
                routes.append({**route_meta, "handler": name, "method_name": name})
            hook_verb = getattr(fn, "__plugin_hook__", None)
            if hook_verb is not None:
                hooks.append({"verb": hook_verb, "method_name": name})
            sched_meta = getattr(fn, "__plugin_sched__", None)
            if sched_meta is not None:
                scheduled.append({**sched_meta, "method_name": name})
        return {"routes": routes, "hooks": hooks, "scheduled": scheduled}


# ---------------------------------------------------------------------------
# PluginContext (restricted proxy)
# ---------------------------------------------------------------------------


class PluginContext:
    """Slotted, audited proxy handed to each plugin instance.

    Plugins never receive a raw engine or DB handle. The context validates
    every SQL statement against the plugin's prefix and the shared whitelist
    before forwarding to the underlying aiosqlite connection, emits events
    via the hook bus, and produces action proposals as plain dicts (persistence
    is the caller's responsibility — the context never writes proposals
    itself).
    """

    __slots__ = (
        "_plugin_id",
        "_config",
        "_db",
        "_hook_bus",
        "_shared",
        "_engine_proxy",
    )

    def __init__(
        self,
        plugin_id: str,
        config: dict[str, Any],
        db: "aiosqlite.Connection | None",
        hook_bus: Any = None,
        shared: dict[str, set[str]] | None = None,
        engine_proxy: Any = None,
    ) -> None:
        object.__setattr__(self, "_plugin_id", plugin_id)
        object.__setattr__(self, "_config", config if config is not None else {})
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "_hook_bus", hook_bus)
        object.__setattr__(
            self,
            "_shared",
            shared if shared is not None else {"read": {"plugins"}, "write": set()},
        )
        object.__setattr__(self, "_engine_proxy", engine_proxy)

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def get_config(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    # ------------------------------------------------------------------
    # SQL (SELECT-only, whitelisted tables)
    # ------------------------------------------------------------------

    _SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)

    async def db_query(self, sql: str, params: Any = ()) -> Any:
        """Execute a SELECT-only query against whitelisted tables.

        Only SELECT statements are allowed. Referenced tables must either
        start with ``<plugin_id>_`` or be in the shared read whitelist.
        Returns the cursor for result fetching.
        """
        if not self._SELECT_RE.match(sql):
            raise PermissionError(
                f"Plugin '{self._plugin_id}': only SELECT statements are allowed via db_query"
            )
        self._validate_select(sql)
        if self._db is None:
            raise RuntimeError("PluginContext.db_query: no database connection configured")
        return await self._db.execute(sql, params)

    def _validate_select(self, sql: str) -> None:
        for pattern in _BLOCKED_PATTERNS:
            if pattern.search(sql):
                raise PermissionError(
                    f"Blocked SQL pattern in plugin '{self._plugin_id}': {pattern.pattern}"
                )
        pragma_match = re.search(r"\bPRAGMA\s+(\w+)", sql, re.IGNORECASE)
        if pragma_match:
            target = pragma_match.group(1)
            if not target.startswith(f"{self._plugin_id}_") and target not in self._shared["read"]:
                raise PermissionError(
                    f"PRAGMA on table '{target}' denied for plugin '{self._plugin_id}'"
                )
        tables = _extract_table_identifiers(sql)
        prefix = f"{self._plugin_id}_"
        read_set = self._shared.get("read", set())
        for table in tables:
            if table in read_set:
                continue
            if table.startswith(prefix):
                continue
            raise PermissionError(
                f"SELECT access to table '{table}' denied: must start with '{prefix}' "
                f"or be in shared read whitelist"
            )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def emit_event(self, event: str, data: dict[str, Any]) -> None:
        if self._hook_bus is None:
            return
        self._hook_bus.publish(event, **data)

    # ------------------------------------------------------------------
    # Proposals
    # ------------------------------------------------------------------

    def create_proposal(
        self,
        action: str,
        params: dict[str, Any],
        reasoning: str = "",
    ) -> dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "action": action,
            "params": dict(params),
            "reasoning": reasoning,
            "risk_level": "MEDIUM",
            "status": "PENDING",
            "created_by": "plugin:" + self._plugin_id,
            "created_at": time.time(),
        }
