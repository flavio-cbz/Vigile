"""
Vigile — DBAuto

Declarative table management for plugins.

Each plugin declares its table schema in the manifest's ``database`` field.
DBAuto translates those declarations into ``CREATE TABLE IF NOT EXISTS``
statements, prefixing table names with ``<plugin_id>_`` to enforce
zero-trust table isolation.

Operations:
  - create_tables(plugin_id, schema)
  - verify_tables(plugin_id, schema)
  - drop_tables(plugin_id, schema)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


_COLUMN_TYPE_MAP = {
    "TEXT": "TEXT",
    "INTEGER": "INTEGER",
    "REAL": "REAL",
    "BLOB": "BLOB",
    "NUMERIC": "NUMERIC",
    "BOOLEAN": "INTEGER",
    "FLOAT": "REAL",
    "INT": "INTEGER",
    "VARCHAR": "TEXT",
    "TIMESTAMP": "TEXT",
}


class DBAuto:
    """Declarative table management with prefix-based isolation."""

    def __init__(self, db: Any = None) -> None:
        self._db = db

    def set_db(self, db: Any) -> None:
        self._db = db

    def _table_name(self, plugin_id: str, table_name: str) -> str:
        return f"{plugin_id}_{table_name}"

    def _build_create_sql(
        self, plugin_id: str, table_name: str, columns: list[dict]
    ) -> str:
        full_name = self._table_name(plugin_id, table_name)
        col_defs: list[str] = []
        pk_cols: list[str] = []

        for col in columns:
            col_name = col.get("name", "")
            raw_type = col.get("type", "TEXT").upper()
            sql_type = _COLUMN_TYPE_MAP.get(raw_type, "TEXT")
            col_def = f"    {col_name} {sql_type}"

            if col.get("not_null"):
                col_def += " NOT NULL"

            if col.get("default") is not None:
                default = col["default"]
                if isinstance(default, str) and default.upper() in (
                    "CURRENT_TIMESTAMP", "CURRENT_DATE", "CURRENT_TIME"
                ):
                    col_def += f" DEFAULT {default}"
                elif isinstance(default, str):
                    col_def += f" DEFAULT '{default}'"
                elif isinstance(default, bool):
                    col_def += f" DEFAULT {'1' if default else '0'}"
                else:
                    col_def += f" DEFAULT {default}"

            col_defs.append(col_def)

            if col.get("pk"):
                pk_cols.append(col_name)

        if pk_cols:
            col_defs.append(f"    PRIMARY KEY ({', '.join(pk_cols)})")

        sql = (
            f"CREATE TABLE IF NOT EXISTS {full_name} (\n"
            + ",\n".join(col_defs)
            + "\n)"
        )
        return sql

    async def create_tables(
        self, plugin_id: str, schema: dict[str, list[dict]]
    ) -> dict[str, bool]:
        """Create all tables declared in *schema*.

        Returns a dict mapping table name to success boolean.
        """
        if self._db is None:
            raise RuntimeError("DBAuto: no database connection available")

        results: dict[str, bool] = {}
        for table_name, columns in schema.items():
            sql = self._build_create_sql(plugin_id, table_name, columns)
            try:
                await self._db.execute(sql)
                results[table_name] = True
                logger.info(
                    "DBAuto: created table '%s' for plugin '%s'",
                    self._table_name(plugin_id, table_name),
                    plugin_id,
                )
            except Exception as exc:
                logger.error(
                    "DBAuto: failed to create table '%s' for plugin '%s': %s",
                    self._table_name(plugin_id, table_name),
                    plugin_id,
                    exc,
                )
                results[table_name] = False
        return results

    def _build_drop_sql(self, plugin_id: str, table_name: str) -> str:
        full_name = self._table_name(plugin_id, table_name)
        return f"DROP TABLE IF EXISTS {full_name}"

    async def drop_tables(
        self, plugin_id: str, schema: dict[str, list[dict]]
    ) -> dict[str, bool]:
        """Drop all tables declared in *schema*.

        Returns a dict mapping table name to success boolean.
        """
        if self._db is None:
            raise RuntimeError("DBAuto: no database connection available")

        results: dict[str, bool] = {}
        for table_name in schema:
            sql = self._build_drop_sql(plugin_id, table_name)
            try:
                await self._db.execute(sql)
                results[table_name] = True
                logger.info(
                    "DBAuto: dropped table '%s' for plugin '%s'",
                    self._table_name(plugin_id, table_name),
                    plugin_id,
                )
            except Exception as exc:
                logger.error(
                    "DBAuto: failed to drop table '%s' for plugin '%s': %s",
                    self._table_name(plugin_id, table_name),
                    plugin_id,
                    exc,
                )
                results[table_name] = False
        return results

    async def verify_tables(
        self, plugin_id: str, schema: dict[str, list[dict]]
    ) -> dict[str, bool]:
        """Verify that all tables in *schema* exist and have the correct columns.

        Uses ``PRAGMA table_info`` for structure verification.

        Returns a dict mapping table name to a boolean: True if the table
        exists with all expected columns, False otherwise.
        """
        if self._db is None:
            raise RuntimeError("DBAuto: no database connection available")

        results: dict[str, bool] = {}
        for table_name, columns in schema.items():
            full_name = self._table_name(plugin_id, table_name)
            try:
                cursor = await self._db.execute(
                    f"PRAGMA table_info({full_name})"
                )
                rows = await cursor.fetchall()
                actual_cols = {row["name"] for row in rows}
                expected_cols = {col.get("name", "") for col in columns}
                exists = expected_cols.issubset(actual_cols)
                results[table_name] = exists
                if not exists:
                    missing = expected_cols - actual_cols
                    logger.warning(
                        "DBAuto: table '%s' missing columns: %s",
                        full_name,
                        missing,
                    )
            except Exception as exc:
                logger.error(
                    "DBAuto: verify failed for table '%s': %s",
                    full_name,
                    exc,
                )
                results[table_name] = False
        return results
