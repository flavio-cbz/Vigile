"""
Vigile — S2 Closed Block Resolver (J3a-T15)

The resolver is the CLOSED dispatch point for declarative block data sources
(contract §8 S2, plan §5 S2). Security model:

- **Build-then-freeze**: the loader (T14) populates the registry via
  ``register()`` at load time, then calls ``freeze()``. Freeze replaces the
  live dict with a ``types.MappingProxyType`` — lookups happen ONLY against
  the frozen mapping (``FROZEN.get(key)``), never the mutable registry.
- **404 fail-closed**: an unknown key raises ``BlockNotFoundError`` (a
  ``KeyError`` subclass the API layer maps to HTTP 404). There is no default
  handler, no fall-through, no ``dict.get(None)``-style silent miss.
- **Lifecycle guards**: ``register()`` after freeze raises
  ``ResolverFrozenError``; ``resolve()`` (and ``FROZEN`` access) before
  freeze raises ``ResolverNotFrozenError``. Duplicate keys are rejected at
  registration (no silent shadowing). Both are fail-closed — a programming
  error must never degrade into a wrong-but-served response.
- **Handler contract**: ``handler(context, config) -> JSON-serializable
  result``. ``resolve()`` is async and awaits coroutine handlers (all plugin
  ``@route`` handlers in this repo are ``async def``), while remaining
  compatible with plain sync callables.

MEDIA/BINARY envelope (decision, see decisions.md):

The plex ``/photo`` image proxy is a binary response — a JSON-only contract
would break session posters. The resolver therefore defines a small typed
wrapper, ``BinaryResult(content: bytes, media_type: str)``, and passes it
through **untouched** (no base64, no JSON mangling). The API layer
distinguishes ``isinstance(result, BinaryResult)`` and serves raw bytes with
the declared ``media_type``; every other result is JSON-serialized. A typed
wrapper was chosen over a dict envelope (e.g. ``{"__binary__": ...}``)
because it is type-checkable, cannot collide with plugin payload keys, and
keeps the bytes out of any JSON round-trip.

Registry isolation: each plugin owns its own ``BlockResolver`` instance —
the loader creates one per plugin and registers namespaced keys
(``<plugin_id>.<handler>``, S1 format). A handler registered in plugin A's
resolver is unreachable from plugin B's resolver by construction.

This module is deliberately dependency-free: no plugin_engine imports, no
FastAPI, no settings — the loader wires it (T14), the API layer mounts it
(later task).
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping


class BlockNotFoundError(KeyError):
    """Unknown block/data-source key — maps to HTTP 404 (fail-closed).

    Raised by :meth:`BlockResolver.resolve` when the key is absent from the
    frozen mapping. Subclasses ``KeyError`` so generic mapping-miss handling
    also catches it; the API layer converts it to a 404 response.
    """


class ResolverFrozenError(RuntimeError):
    """Registration attempted after :meth:`BlockResolver.freeze`.

    The registry is immutable once frozen — a late ``register()`` is a
    loader wiring bug and must fail loudly, never silently drop the handler.
    """


class ResolverNotFrozenError(RuntimeError):
    """Lookup attempted before :meth:`BlockResolver.freeze`.

    Lookups are only valid against the frozen mapping. Resolving a
    half-built registry would serve a snapshot that later registrations
    could change — fail-closed instead.
    """


@dataclass(frozen=True)
class BinaryResult:
    """Typed envelope for MEDIA/BINARY handler responses.

    Handlers that proxy binary content (plex ``/photo`` image proxy) return
    this instead of a JSON-serializable value. The resolver passes it
    through untouched; the API layer serves ``content`` raw with
    ``media_type`` (e.g. ``image/jpeg``) instead of JSON-encoding it.
    """

    content: bytes
    media_type: str


# Handler contract: (context, config) -> JSON-serializable result | BinaryResult
Handler = Callable[[Any, Any], Any]


class BlockResolver:
    """Closed block/data-source resolver with build-then-freeze semantics.

    Usage (loader wiring, T14)::

        resolver = BlockResolver()
        resolver.register("plex.photo", photo_handler)
        resolver.register("plex.sessions", sessions_handler)
        resolver.freeze()
        result = await resolver.resolve("plex.photo", context, config)
    """

    def __init__(self) -> None:
        self._registry: dict[str, Handler] = {}
        self._frozen: MappingProxyType[str, Handler] | None = None

    @property
    def FROZEN(self) -> Mapping[str, Handler]:
        """The frozen handler mapping (``MappingProxyType``) — contract S2.

        Read-only view of the registry after :meth:`freeze`. Accessing it
        before freeze raises :class:`ResolverNotFrozenError` (fail-closed).
        """
        if self._frozen is None:
            raise ResolverNotFrozenError(
                "BlockResolver.FROZEN accessed before freeze() — "
                "lookups are only valid against the frozen mapping"
            )
        return self._frozen

    def register(self, key: str, handler: Handler) -> None:
        """Register one handler under a namespaced key (``plugin.handler``).

        Raises
        ------
        ResolverFrozenError
            If called after :meth:`freeze` — the registry is immutable.
        ValueError
            If ``key`` is already registered — no silent overwrite.
        TypeError
            If ``handler`` is not callable.
        """
        if self._frozen is not None:
            raise ResolverFrozenError(
                f"cannot register {key!r}: BlockResolver is frozen"
            )
        if not callable(handler):
            raise TypeError(f"handler for {key!r} must be callable, got {type(handler).__name__}")
        if key in self._registry:
            raise ValueError(f"duplicate block key {key!r} — refusing to shadow an existing handler")
        self._registry[key] = handler

    def freeze(self) -> None:
        """Freeze the registry into a read-only ``MappingProxyType``.

        Idempotent: a second call is a no-op. After this point,
        ``register()`` raises :class:`ResolverFrozenError` and lookups go
        through the frozen view only.
        """
        if self._frozen is None:
            self._frozen = MappingProxyType(dict(self._registry))

    async def resolve(self, key: str, context: Any, config: Any) -> Any:
        """Resolve ``key`` and invoke its handler with ``(context, config)``.

        Parameters
        ----------
        key:
            Namespaced block/data-source key (``<plugin_id>.<handler>``).
        context:
            Block context (params, injected ``node_id``, session roles…).
        config:
            Plugin/block configuration dict.

        Returns
        -------
        The handler result: a JSON-serializable value, or a
        :class:`BinaryResult` envelope for MEDIA/BINARY responses.

        Raises
        ------
        BlockNotFoundError
            Unknown key — 404 fail-closed, never a default handler.
        ResolverNotFrozenError
            Called before :meth:`freeze`.
        """
        handler = self.FROZEN.get(key)
        if handler is None:
            raise BlockNotFoundError(key)
        result = handler(context, config)
        if inspect.isawaitable(result):
            result = await result
        return result