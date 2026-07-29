from __future__ import annotations

import pytest

from master.core.plugin_base import (
    PluginBase,
    PluginContext,
    _extract_table_identifiers,
    _tokenize_sql,
    hook,
    route,
    scheduled,
)


class TestDecorators:
    def test_route_sets_metadata(self):
        class T:
            pass

        t = T()

        @route("/test", method="POST", roles=["admin"])
        def handler():
            pass

        assert hasattr(handler, "__plugin_route__")
        meta = handler.__plugin_route__
        assert meta["path"] == "/test"
        assert meta["method"] == "POST"
        assert meta["roles"] == ["admin"]

    def test_hook_sets_verb(self):
        @hook("on_test")
        def handler():
            pass

        assert hasattr(handler, "__plugin_hook__")
        assert handler.__plugin_hook__ == "on_test"

    def test_scheduled_sets_interval(self):
        @scheduled(interval_secs=60)
        def handler():
            pass

        assert hasattr(handler, "__plugin_sched__")
        assert handler.__plugin_sched__["interval_secs"] == 60

    def test_route_default_roles(self):
        @route("/public")
        def handler():
            pass

        assert handler.__plugin_route__["roles"] == ["viewer"]
        assert handler.__plugin_route__["method"] == "GET"


class TestPluginBase:
    def test_subclass_auto_registers(self):
        class TestPlugin(PluginBase):
            plugin_id = "test_plugin"

            def __init__(self, ctx):
                super().__init__(ctx)

        assert "test_plugin" in PluginBase._decorated_registry

    def test_plugin_without_id_not_registered(self):
        before = len(PluginBase._decorated_registry)

        class NoIdPlugin(PluginBase):
            pass

        assert len(PluginBase._decorated_registry) == before

    def test_collect_routes(self):
        class RouterPlugin(PluginBase):
            plugin_id = "router"

            def __init__(self, ctx):
                super().__init__(ctx)

            @route("/foo")
            def foo(self):
                pass

            @route("/bar", method="POST")
            def bar(self):
                pass

        ctx = PluginContext(plugin_id="router", config={}, db=None)
        instance = RouterPlugin(ctx)
        assert len(instance.routes) >= 2
        paths = {r["path"] for r in instance.routes}
        assert "/foo" in paths
        assert "/bar" in paths

    def test_collect_hooks(self):
        class HookPlugin(PluginBase):
            plugin_id = "hooker"

            def __init__(self, ctx):
                super().__init__(ctx)

            @hook("on_event")
            def handle_event(self):
                pass

        ctx = PluginContext(plugin_id="hooker", config={}, db=None)
        instance = HookPlugin(ctx)
        verbs = {h["verb"] for h in instance.hooks}
        assert "on_event" in verbs

    def test_collect_scheduled(self):
        class SchedPlugin(PluginBase):
            plugin_id = "sched"

            def __init__(self, ctx):
                super().__init__(ctx)

            @scheduled(300)
            def periodic(self):
                pass

        ctx = PluginContext(plugin_id="sched", config={}, db=None)
        instance = SchedPlugin(ctx)
        assert len(instance.scheduled) == 1
        assert instance.scheduled[0]["interval_secs"] == 300
        assert instance.scheduled[0]["method_name"] == "periodic"


class TestPluginContext:
    def test_get_config(self):
        ctx = PluginContext(plugin_id="test", config={"key": "val"}, db=None)
        assert ctx.get_config("key") == "val"
        assert ctx.get_config("missing", "default") == "default"

    def test_db_query_no_db(self):
        ctx = PluginContext(plugin_id="test", config={}, db=None)
        import pytest

        with pytest.raises(RuntimeError):
            import asyncio

            asyncio.run(ctx.db_query("SELECT 1"))

    def test_create_proposal(self):
        ctx = PluginContext(plugin_id="test", config={}, db=None)
        proposal = ctx.create_proposal(
            action="RESTART_SERVICE",
            params={"node_id": "n1", "service": "ssh"},
            reasoning="SSH is down",
        )
        assert proposal["action"] == "RESTART_SERVICE"
        assert proposal["status"] == "PENDING"
        assert proposal["risk_level"] == "MEDIUM"
        assert "plugin:test" in proposal["created_by"]

    def test_emit_event_no_hook_bus(self):
        ctx = PluginContext(plugin_id="test", config={}, db=None)
        ctx.emit_event("test_event", data={"key": "val"})

    def test_validate_sql_blocks_cross_table(self):
        ctx = PluginContext(
            plugin_id="test",
            config={},
            db=None,
        )
        import pytest

        with pytest.raises(PermissionError):
            ctx._validate_select("SELECT * FROM users")

    def test_validate_select_allows_shared(self):
        ctx = PluginContext(
            plugin_id="test",
            config={},
            db=None,
        )
        ctx._validate_select("SELECT * FROM plugins")


class TestSqlTokenizer:
    def test_tokenize_basic(self):
        tokens = _tokenize_sql("SELECT * FROM users")
        assert "SELECT" in tokens
        assert "FROM" in tokens
        assert "users" in tokens

    def test_tokenize_with_comment(self):
        tokens = _tokenize_sql("SELECT 1 -- inline comment")
        assert "SELECT" in tokens
        assert "1" in tokens
        assert "inline" not in tokens

    def test_tokenize_with_block_comment(self):
        tokens = _tokenize_sql("SELECT /* block */ 1")
        assert "SELECT" in tokens
        assert "1" in tokens
        assert "block" not in tokens

    def test_tokenize_quoted_identifier(self):
        tokens = _tokenize_sql('SELECT "my col" FROM t')
        assert "my col" in tokens
        assert "t" in tokens

    def test_extract_tables_simple(self):
        tables = _extract_table_identifiers("SELECT * FROM users")
        assert "users" in tables

    def test_extract_tables_join(self):
        tables = _extract_table_identifiers(
            "SELECT * FROM users JOIN orders ON users.id = orders.user_id"
        )
        assert "users" in tables
        assert "orders" in tables

    def test_extract_tables_update(self):
        tables = _extract_table_identifiers("UPDATE users SET name = ?")
        assert "users" in tables

    def test_extract_tables_insert(self):
        tables = _extract_table_identifiers("INSERT INTO logs VALUES (1)")
        assert "logs" in tables

    def test_extract_tables_create(self):
        tables = _extract_table_identifiers("CREATE TABLE my_data (id INT)")
        assert "my_data" in tables

    def test_extract_tables_drop(self):
        tables = _extract_table_identifiers("DROP TABLE IF EXISTS old_data")
        assert "old_data" in tables
