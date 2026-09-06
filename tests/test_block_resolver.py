"""
Tests for the S2 closed block resolver (J3a-T15).

The resolver is CLOSED by design (contract §8 S2):

- The handler registry is built at load time then FROZEN (``MappingProxyType``).
- Lookups happen ONLY against the frozen mapping — an unknown key raises
  ``BlockNotFoundError`` (HTTP 404 semantics), never falls through, never
  hits a default handler.
- Handlers are ``(context, config) -> JSON-serializable result``.
- MEDIA/BINARY responses (plex ``/photo`` image proxy) flow through the
  ``BinaryResult`` typed envelope — a JSON-only contract would break session
  posters, so the resolver passes the envelope through untouched.
- Each plugin owns its own resolver instance → registry isolation: a handler
  registered in plugin A's resolver is unreachable from plugin B's resolver.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from master.core.block_resolver import (
    BinaryResult,
    BlockNotFoundError,
    BlockResolver,
    ResolverFrozenError,
    ResolverNotFrozenError,
)


def _echo(context, config):
    """Sync handler echoing its (context, config) — the contract signature."""
    return {"context": context, "config": config}


async def _async_echo(context, config):
    """Async handler — plugin ``@route`` handlers are coroutines in this repo."""
    return {"async": True, "context": context, "config": config}


def _photo(context, config):
    """Plex-style binary proxy handler (MEDIA/BINARY requirement)."""
    return BinaryResult(
        content=b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
        media_type="image/png",
    )


def _make_frozen(*pairs) -> BlockResolver:
    resolver = BlockResolver()
    for key, handler in pairs:
        resolver.register(key, handler)
    resolver.freeze()
    return resolver


# ---------------------------------------------------------------------------
# Closed lookup (fail-closed 404)
# ---------------------------------------------------------------------------


class TestClosedLookup:
    async def test_unknown_key_raises_404_fail_closed(self):
        resolver = _make_frozen(("plex.photo", _photo))
        with pytest.raises(BlockNotFoundError):
            await resolver.resolve("plex.sessions", {}, {})

    async def test_unknown_key_never_falls_through(self):
        # A resolver with OTHER registered keys must still 404 on a miss —
        # no default handler, no dict.get(None) fallback, no 200-with-null.
        resolver = _make_frozen(
            ("plex.photo", _photo),
            ("plex.sessions", _echo),
        )
        with pytest.raises(BlockNotFoundError):
            await resolver.resolve("docker.containers", {}, {})

    async def test_missing_key_is_distinguishable_from_registered(self):
        # Fail-closed: the caller must be able to tell "handler returned
        # None" apart from "key unknown" — only the exception path exists.
        resolver = _make_frozen(("plex.photo", _photo))
        with pytest.raises(BlockNotFoundError):
            await resolver.resolve("nope", {}, {})

    async def test_lookup_before_freeze_is_fail_closed(self):
        # Lookups only against the frozen mapping — resolving a registered
        # key before freeze() is a programming error, never a silent serve.
        resolver = BlockResolver()
        resolver.register("plex.photo", _photo)
        with pytest.raises(ResolverNotFrozenError):
            await resolver.resolve("plex.photo", {}, {})


# ---------------------------------------------------------------------------
# Frozen mapping (MappingProxyType semantics)
# ---------------------------------------------------------------------------


class TestFrozenMapping:
    def test_FROZEN_is_a_mappingproxy_after_freeze(self):
        resolver = _make_frozen(("plex.photo", _photo))
        assert isinstance(resolver.FROZEN, MappingProxyType)

    def test_FROZEN_get_returns_registered_handler(self):
        resolver = _make_frozen(("plex.photo", _photo))
        assert resolver.FROZEN.get("plex.photo") is _photo

    def test_FROZEN_get_unknown_returns_none(self):
        # Plain mapping semantics on the frozen view — resolve() is the only
        # gate that converts a miss into BlockNotFoundError.
        resolver = _make_frozen(("plex.photo", _photo))
        assert resolver.FROZEN.get("plex.missing") is None

    def test_FROZEN_access_before_freeze_fails_closed(self):
        resolver = BlockResolver()
        resolver.register("plex.photo", _photo)
        with pytest.raises(ResolverNotFrozenError):
            resolver.FROZEN

    def test_freeze_is_idempotent(self):
        resolver = BlockResolver()
        resolver.register("plex.photo", _photo)
        resolver.freeze()
        resolver.freeze()  # second freeze must be a no-op, not an error
        assert resolver.FROZEN.get("plex.photo") is _photo

    def test_frozen_view_is_readonly(self):
        resolver = _make_frozen(("plex.photo", _photo))
        with pytest.raises(TypeError):
            resolver.FROZEN["plex.sessions"] = _echo


# ---------------------------------------------------------------------------
# Registration & freeze lifecycle
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_then_freeze_then_resolve(self):
        resolver = BlockResolver()
        resolver.register("plex.photo", _photo)
        resolver.freeze()
        assert resolver.FROZEN.get("plex.photo") is _photo

    def test_freeze_blocks_later_registration(self):
        resolver = BlockResolver()
        resolver.register("plex.photo", _photo)
        resolver.freeze()
        with pytest.raises(ResolverFrozenError):
            resolver.register("plex.sessions", _echo)

    def test_duplicate_registration_is_rejected(self):
        # Fail-closed: no silent overwrite / shadowing of an existing key.
        resolver = BlockResolver()
        resolver.register("plex.photo", _photo)
        with pytest.raises(ValueError):
            resolver.register("plex.photo", _echo)

    def test_non_callable_handler_is_rejected(self):
        resolver = BlockResolver()
        with pytest.raises(TypeError):
            resolver.register("plex.photo", "not-a-callable")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Handler invocation contract
# ---------------------------------------------------------------------------


class TestHandlerInvocation:
    async def test_sync_handler_receives_context_and_config(self):
        resolver = _make_frozen(("plex.sessions", _echo))
        result = await resolver.resolve(
            "plex.sessions", {"node_id": "n-1"}, {"limit": 10}
        )
        assert result == {"context": {"node_id": "n-1"}, "config": {"limit": 10}}

    async def test_async_handler_is_awaited(self):
        resolver = _make_frozen(("metrics.history", _async_echo))
        result = await resolver.resolve(
            "metrics.history", {"node_id": "n-2"}, {"period": "1h"}
        )
        assert result == {
            "async": True,
            "context": {"node_id": "n-2"},
            "config": {"period": "1h"},
        }

    async def test_handler_returning_none_is_a_valid_result(self):
        # None is JSON-serializable and a legitimate handler result — the
        # fail-closed 404 is reserved for unknown KEYS, not handler output.
        resolver = _make_frozen(("plex.empty", lambda c, cfg: None))
        assert await resolver.resolve("plex.empty", {}, {}) is None


# ---------------------------------------------------------------------------
# MEDIA/BINARY envelope (plex /photo image proxy)
# ---------------------------------------------------------------------------


class TestBinaryEnvelope:
    async def test_binary_result_flows_through_envelope(self):
        resolver = _make_frozen(("plex.photo", _photo))
        result = await resolver.resolve("plex.photo", {}, {})
        assert isinstance(result, BinaryResult)
        assert result.content == b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        assert result.media_type == "image/png"

    async def test_binary_envelope_is_passed_untouched(self):
        # The resolver must NOT JSON-encode or base64-mangle the envelope —
        # the API layer decides how to serialize (raw bytes for image/jpeg).
        payload = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        resolver = _make_frozen(("plex.photo", lambda c, cfg: BinaryResult(content=payload, media_type="image/jpeg")))
        result = await resolver.resolve("plex.photo", {}, {})
        assert result.content == payload
        assert result.media_type == "image/jpeg"

    async def test_binary_and_json_results_coexist(self):
        resolver = _make_frozen(
            ("plex.photo", _photo),
            ("plex.sessions", _echo),
        )
        binary = await resolver.resolve("plex.photo", {}, {})
        json_result = await resolver.resolve("plex.sessions", {}, {})
        assert isinstance(binary, BinaryResult)
        assert not isinstance(json_result, BinaryResult)
        assert isinstance(json_result, dict)


# ---------------------------------------------------------------------------
# Registry isolation between plugins
# ---------------------------------------------------------------------------


class TestRegistryIsolation:
    async def test_plugins_do_not_share_handlers(self):
        plex = _make_frozen(("plex.photo", _photo))
        docker = _make_frozen(("docker.containers", _echo))
        with pytest.raises(BlockNotFoundError):
            await docker.resolve("plex.photo", {}, {})
        with pytest.raises(BlockNotFoundError):
            await plex.resolve("docker.containers", {}, {})

    async def test_same_key_in_different_plugins_is_distinct(self):
        # Isolation even when keys collide by handler name — each plugin
        # resolves against its OWN registry, never a global namespace.
        plex = _make_frozen(("plex.history", _photo))
        metrics = _make_frozen(("metrics.history", _echo))
        plex_result = await plex.resolve("plex.history", {}, {})
        metrics_result = await metrics.resolve("metrics.history", {}, {})
        assert isinstance(plex_result, BinaryResult)
        assert not isinstance(metrics_result, BinaryResult)
