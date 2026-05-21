# master/db/

## Responsibility

Pure SQL database layer for the YouCloud API master server. Manages schema definitions as inline SQL strings, an aiosqlite connection singleton with WAL mode, an async transaction context manager, and an idempotent migration runner that creates all tables and seeds the default admin user on startup. No ORM, no query builder — all SQL is hand-written.

## Design

- **No ORM**: Every SQL query is a raw string. Schema lives in `models.py` as module-level string constants. No SQLAlchemy, no Alembic, no query builder.
- **Connection singleton**: A single `aiosqlite.Connection` instance (`_db`) initialized at FastAPI startup via `init_db()`, accessible via `get_db_conn()`. Not thread-safe by design (single-process async).
- **WAL mode**: `PRAGMA journal_mode=WAL` enables concurrent reads during writes. `PRAGMA synchronous=NORMAL` reduces fsync overhead. `PRAGMA foreign_keys=ON` enforces referential integrity.
- **Row factory**: `aiosqlite.Row` enables column-name access on query results (dict-like).
- **Transaction context manager**: `transaction()` wraps operations in explicit try/commit/rollback. Yields the connection directly (`async with transaction(db):`). Rolls back automatically on any exception, commits on success.
- **Idempotent migrations**: `run_migrations()` uses `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` — safe to call on every restart. No version tracking (no `schema_version` table).
- **DDL in dependency order**: `ALL_TABLES` ordered so foreign key dependencies exist before referencing tables: nodes → join_tokens → worker_tokens → users → audit_log → metrics_snapshots → action_proposals.
- **Default admin seeding**: If `users` table is empty, creates `admin/admin` account via passlib bcrypt and inserts a genesis audit entry (sequence=1) anchoring the SHA256 hash chain.
- **Audit chain genesis**: The first audit entry uses `GENESIS_HASH` (from `master.core.audit`) as its `previous_hash`, computed via `compute_entry_hash()` using SHA256 of concatenated fields.
- **No connection pooling**: Single connection, single process. SQLite is the bottleneck by design — no pooling needed.

## Flow

1. FastAPI lifespan calls `init_db()` → opens SQLite file from `settings.database_path`, configures WAL/foreign_keys/synchronous pragmas, sets row factory.
2. Lifespan calls `run_migrations(db)` → iterates `ALL_TABLES` (7 CREATE TABLE IF NOT EXISTS), then `CREATE_INDEXES` (11 CREATE INDEX IF NOT EXISTS).
3. If `users` table is empty, `_seed_default_admin()` inserts admin/admin user with bcrypt hash.
4. Genesis audit entry inserted at sequence=1, linking to `GENESIS_HASH` — anchors the SHA256 chain.
5. `db.commit()` finalizes schema creation and seeding.
6. After startup, domain logic calls `get_db_conn()` to obtain the connection, wraps multi-statement writes in `async with transaction(db):` for automatic commit/rollback.
7. On shutdown, lifespan calls `close_db()` → closes the aiosqlite connection, sets `_db = None`.

## Integration

- **Consumed by**: `master/api/auth.py`, `master/api/nodes.py`, `master/api/services.py`, `master/api/chat.py` (all REST endpoints call `get_db_conn()` for reads/writes); `master/ws/worker_handler.py` (WebSocket handler reads/writes node state); `master/core/` classes (`NodeManager`, `SecurityManager`, audit logging) via injected or imported `get_db_conn()`
- **Depends on**: `aiosqlite` (async SQLite driver), `passlib[CryptContext]` (bcrypt hashing in migrations), `master.config.settings` (for `database_path`), `master.core.audit` (for `GENESIS_HASH` and `compute_entry_hash` in genesis seeding)
