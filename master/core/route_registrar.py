"""
Vigile — RouteRegistrar

Dynamic FastAPI route mounting and unmounting for plugins.

Mounts an APIRouter under ``/api/plugins/{plugin_id}/`` for each plugin's
declared routes. Unmounting rebuilds the application's route table by
filtering out the routes the registrar installed.

The registrar uses a FastAPI APIRouter per plugin so routes can be
individually mounted and unmounted without affecting other routes.
"""

from __future__ import annotations

import inspect
import json
import logging
from contextlib import AsyncExitStack
from typing import Any, Callable
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.dependencies.utils import get_dependant, solve_dependencies
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# T26 — réconciliation `?since=` sur les routes GET de plugin (S4)
#
# Le client SSE ne reçoit pas chaque événement (at-most-once) : il converge
# en revalidant avec la paire de revision capturée `<boot_id>:<counter>`.
# Si la revision courante du moteur est identique → `{"unchanged": true}`
# sans payload ; sinon réponse normale + paire `revision` (la forme de la
# donnée elle-même reste inchangée — « étendre, ne pas casser »). Seules les
# routes GET sont enveloppées : les POST de mutation (docker/systemd) ne sont
# pas concernés.
# ---------------------------------------------------------------------------


def _resolve_engine() -> Any:
    """Résout l'instance PluginEngine active (import paresseux : évite tout
    cycle module-level entre route_registrar et plugin_manager)."""
    from master.core.plugin_manager import plugin_engine
    return plugin_engine


def _since_matches(since: str) -> bool:
    """Compare `<boot_id>:<counter>` à la revision courante du moteur.

    Un ``since`` malformé ne matche jamais → repli sur la réponse complète
    (jamais de faux ``unchanged``).
    """
    engine = _resolve_engine()
    if engine is None or not hasattr(engine, "revision"):
        return False
    try:
        boot_id, counter = since.rsplit(":", 1)
        revision = engine.revision
        return revision.boot_id == boot_id and revision.counter == int(counter)
    except (ValueError, TypeError):
        return False


def _current_revision() -> dict[str, Any] | None:
    engine = _resolve_engine()
    if engine is None or not hasattr(engine, "revision"):
        return None
    revision = engine.revision
    return {"boot_id": revision.boot_id, "counter": revision.counter}


def _extend_with_revision(result: Any) -> Any:
    """Ajoute la paire ``revision`` à une réponse JSON (dict ou JSONResponse).

    Les réponses non-JSON (binaire — ex. plex /photo) sont laissées intactes.
    """
    revision = _current_revision()
    if revision is None:
        return result
    if isinstance(result, dict):
        return {**result, "revision": revision}
    if isinstance(result, JSONResponse):
        try:
            data = json.loads(result.body)
        except (ValueError, TypeError):
            return result
        if isinstance(data, dict):
            headers = {
                k: v
                for k, v in result.headers.items()
                if k.lower() not in ("content-length", "content-type")
            }
            return JSONResponse(
                {**data, "revision": revision},
                status_code=result.status_code,
                headers=headers,
            )
    return result


_DEPENDANT_CACHE: dict[Any, Any] = {}


def _get_cached_dependant(handler: Any) -> Any:
    """Mémoïse l'analyse de signature et modèles Pydantic de get_dependant (H7)."""
    dep = _DEPENDANT_CACHE.get(handler)
    if dep is None:
        dep = get_dependant(path="/plugins", call=handler)
        _DEPENDANT_CACHE[handler] = dep
    return dep


async def _invoke_handler(request: Request, handler: Any) -> tuple[Any, dict[str, Any]]:
    """Invoque le handler réel avec ses dépendances résolues (même mécanique
    que ``/batch`` — ``solve_dependencies``), sans le paramètre ``since``.

    Retourne ``(resultat, valeurs résolues)`` : les valeurs permettent au
    garde-fou d'URL d'accéder à la connexion DB (audit) sans dépendance
    directe sur le schéma de dépendances du handler.
    """
    scope = dict(request.scope)
    query = [(k, v) for k, v in request.query_params.multi_items() if k != "since"]
    scope["query_string"] = urlencode(query, doseq=True).encode("utf-8")
    sub_request = Request(scope)
    dependant = _get_cached_dependant(handler)

    # Réutilise l'AsyncExitStack de la requête FastAPI parent si présente (C3)
    req_astack = request.scope.get("fastapi_astack")
    stack = req_astack if req_astack is not None else AsyncExitStack()
    should_close = req_astack is None

    try:
        solved = await solve_dependencies(
            request=sub_request,
            dependant=dependant,
            body=None,
            background_tasks=None,
            response=None,
            dependency_overrides_provider=request.app,
            async_exit_stack=stack,
            embed_body_fields=False,
        )
        if solved.errors:
            raise HTTPException(status_code=400, detail=f"invalid parameters: {solved.errors}")
        result = handler(**solved.values)
        if inspect.isawaitable(result):
            result = await result
        return result, dict(solved.values)
    finally:
        if should_close:
            await stack.aclose()


async def _invoke_get_handler(request: Request, handler: Any) -> Any:
    result, _ = await _invoke_handler(request, handler)
    return result


async def _since_aware_get(request: Request, handler: Any) -> Any:
    """Enveloppe d'une route GET : `?since=` → `{"unchanged": true}` quand la
    revision courante est identique, sinon réponse normale + `revision`."""
    since = request.query_params.get("since")
    if since is not None and _since_matches(since):
        return JSONResponse({"unchanged": True}, status_code=200)
    return _extend_with_revision(await _invoke_get_handler(request, handler))


def _make_since_wrapper(fn: Any) -> Callable[[Request], Any]:
    """Factory d'enveloppe GET — capture ``fn`` par VALEUR (scope d'appel).

    Un closure inline dans la boucle de ``mount()`` capturerait la variable de
    boucle ``fn`` par référence (late-binding) : au moment de l'appel, elle
    contiendrait le handler de la DERNIÈRE route itérée. Chaque appel de cette
    factory crée un scope propre → chaque route garde son handler.
    """

    async def _since_wrapped(request: Request) -> Any:
        return await _since_aware_get(request, fn)

    return _since_wrapped


# ---------------------------------------------------------------------------
# Garde-fou `external_auth_domains` (T27-BE-2)
#
# Un plugin déclarant des domaines d'auth externes (ex. plex.tv) voit ses
# routes POST enveloppées : toute URL d'authentification renvoyée au client
# doit pointer vers un domaine autorisé (https, domaine exact ou sous-domaine
# pointé). Une URL hors liste = incident de sécurité → 502 + entrée d'audit
# SECURITY_INCIDENT. Les GET ne sont pas enveloppés (URL LAN http://
# légitimes en config, ex. plex_server_url).
# ---------------------------------------------------------------------------

_AUTH_URL_KEY_HINTS = ("auth", "redirect", "callback")
_URL_KEY_HINTS = ("url", "uri", "link", "href")


def _is_auth_url_key(key: str) -> bool:
    """Clé de réponse portant une URL d'authentification externe.

    Matche uniquement les clés explicitement liées à l'auth (``auth_url``,
    ``redirect_uri``, ``callback_url``...) ou exactement ``url``/``uri`` —
    jamais ``plex_server_url`` (URL LAN http:// légitime en config).
    """
    k = key.lower()
    if k in ("url", "uri"):
        return True
    return any(h in k for h in _AUTH_URL_KEY_HINTS) and any(h in k for h in _URL_KEY_HINTS)


def _url_allowed(raw: str, allowed_domains: list[str]) -> bool:
    """https uniquement, domaine exact ou sous-domaine pointé.

    Le point requis (``.plex.tv``) exclut ``plex.tv.attacker.com``.
    """
    try:
        parsed = urlparse(raw)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False
    return any(
        hostname == d.lower() or hostname.endswith("." + d.lower())
        for d in allowed_domains
    )


def _resolve_audit_user(request: Request) -> str:
    """Meilleur effort : identité depuis le Bearer token, sinon acteur système."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            from master.core.security_manager import verify_access_token

            claims = verify_access_token(auth[7:].strip())
            return str(claims.get("sub", "route_registrar"))
        except Exception:
            pass
    return "route_registrar"


async def _log_auth_url_violation(
    request: Request, key: str, value: str, allowed_domains: list[str], plugin_id: str, db: Any
) -> None:
    if db is None:
        logger.warning(
            "URL d'auth externe refusée (%s=%s) hors domaines %s — audit impossible (pas de db)",
            key,
            value,
            allowed_domains,
        )
        return
    try:
        from master.core.audit import AuditAction, log_action

        await log_action(
            db,
            user_id=_resolve_audit_user(request),
            action=AuditAction.SECURITY_INCIDENT,
            details={
                "plugin_id": plugin_id,
                "path": request.url.path,
                "key": key,
                "url": value,
                "allowed_domains": allowed_domains,
            },
        )
        if not db.in_transaction:
            await db.commit()
    except Exception:
        logger.exception("Échec de l'audit SECURITY_INCIDENT")


async def _check_auth_url_result(
    request: Request, result: Any, allowed_domains: list[str], plugin_id: str, db: Any
) -> None:
    """Vérifie les URL d'auth externes de la réponse ; rejette (502 + audit
    SECURITY_INCIDENT) toute URL hors des domaines déclarés."""
    data: Any = None
    if isinstance(result, dict):
        data = result
    elif isinstance(result, JSONResponse):
        try:
            data = json.loads(result.body)
        except (ValueError, TypeError):
            return
    if not isinstance(data, dict):
        return
    for key, value in data.items():
        if not _is_auth_url_key(key) or not isinstance(value, str):
            continue
        if _url_allowed(value, allowed_domains):
            continue
        await _log_auth_url_violation(request, key, value, allowed_domains, plugin_id, db)
        raise HTTPException(
            status_code=502,
            detail=(
                f"URL d'authentification externe refusée pour '{key}' : "
                f"'{value}' hors des domaines autorisés {allowed_domains}."
            ),
        )


def _make_auth_url_guard_wrapper(
    fn: Any, domains: list[str], plugin_id: str
) -> Callable[[Request], Any]:
    """Factory d'enveloppe POST — capture ``fn``/``domains`` par VALEUR
    (même règle que ``_make_since_wrapper`` : pas de closure inline)."""

    async def _guarded(request: Request) -> Any:
        result, solved = await _invoke_handler(request, fn)
        await _check_auth_url_result(request, result, domains, plugin_id, solved.get("db"))
        return result

    return _guarded


class RouteRegistrar:
    """Manages dynamic FastAPI route mounting for plugins."""

    def __init__(self, app: FastAPI | None = None) -> None:
        self._app = app
        # plugin_id -> list of (path, method) tuples for unmounting
        self._mounted_routes: dict[str, list[tuple[str, str]]] = {}

    def set_app(self, app: FastAPI) -> None:
        """Set or update the FastAPI application reference."""
        self._app = app

    def mount(
        self,
        plugin_id: str,
        routes_spec: list[dict[str, Any]],
        instance: Any,
        external_auth_domains: list[str] | None = None,
    ) -> None:
        """Mount routes for a plugin on the FastAPI app.

        Each spec dict must have ``path``, ``method``, ``handler``
        (method name on instance), and optional ``roles``.

        ``external_auth_domains`` (T27-BE-2) : domaines d'authentification
        externes déclarés par le plugin — les routes POST sont alors
        enveloppées d'un garde-fou rejetant (502 + audit SECURITY_INCIDENT)
        toute URL d'auth renvoyée hors de ces domaines. ``None`` → aucun
        changement de comportement.
        """
        if self._app is None:
            logger.warning(
                "RouteRegistrar: no FastAPI app set — cannot mount routes for '%s'",
                plugin_id,
            )
            return

        if plugin_id in self._mounted_routes:
            logger.warning(
                "RouteRegistrar: '%s' already has mounted routes — unmount first",
                plugin_id,
            )
            return

        router = APIRouter(prefix=f"/api/plugins/{plugin_id}", tags=[f"plugin:{plugin_id}"])

        mounted: list[tuple[str, str]] = []
        for spec in routes_spec:
            path = spec["path"]
            method = spec["method"].upper()
            handler_name = spec["handler"]
            fn = getattr(instance, handler_name, None)
            if fn is None:
                logger.error(
                    "RouteRegistrar: '%s' has no handler '%s'",
                    plugin_id,
                    handler_name,
                )
                continue

            if method == "GET":
                # T26 : les GET de plugin acceptent `?since=<boot_id>:<counter>`
                # (S4) — réponse `{unchanged: true}` si la revision est identique,
                # sinon réponse normale enrichie de la paire `revision`.
                # NB: factory (pas functools.partial ni closure inline) —
                # FastAPI résout les annotations via `__globals__` (absent sur
                # les partials → PydanticUndefinedAnnotation) et la factory
                # capture `fn` par valeur (le closure inline late-binderait).
                router.get(path)(_make_since_wrapper(fn))
            elif method == "POST":
                if external_auth_domains:
                    router.post(path)(_make_auth_url_guard_wrapper(fn, external_auth_domains, plugin_id))
                else:
                    router.post(path)(fn)
            elif method == "PUT":
                router.put(path)(fn)
            elif method == "DELETE":
                router.delete(path)(fn)
            elif method == "PATCH":
                router.patch(path)(fn)
            else:
                logger.warning(
                    "RouteRegistrar: unsupported method '%s' for %s route '%s'",
                    method,
                    plugin_id,
                    path,
                )
                continue

            mounted.append((f"/api/plugins/{plugin_id}{path}", method))

        self._app.include_router(router)
        self._mounted_routes[plugin_id] = mounted

        # Ensure dynamic plugin routes are evaluated BEFORE static files catch-all mounted at "/" (M1)
        from starlette.routing import Mount
        regular_routes = []
        static_routes = []
        for r in self._app.router.routes:
            if getattr(r, "name", "") == "static" or (isinstance(r, Mount) and getattr(r, "path", "") == "/"):
                static_routes.append(r)
            else:
                regular_routes.append(r)
        self._app.router.routes = regular_routes + static_routes

        logger.info(
            "RouteRegistrar: mounted %d routes for plugin '%s'",
            len(mounted),
            plugin_id,
        )

    def unmount(self, plugin_id: str) -> None:
        """Unmount all routes for a plugin.

        This rebuilds the route table, filtering out the routes that were
        mounted for this plugin.
        """
        if self._app is None:
            return

        mounted = self._mounted_routes.pop(plugin_id, [])
        if not mounted:
            return

        mounted_paths = {path for path, _ in mounted}

        new_routes = []
        removed = 0
        for route in self._app.router.routes:
            if hasattr(route, "path") and route.path in mounted_paths:
                removed += 1
                continue
            new_routes.append(route)

        self._app.router.routes = new_routes
        logger.info(
            "RouteRegistrar: unmounted %d routes for plugin '%s' (removed %d)",
            len(mounted),
            plugin_id,
            removed,
        )

    def get_mounted(self, plugin_id: str) -> list[str]:
        """Return the list of paths mounted for a plugin."""
        return [path for path, _ in self._mounted_routes.get(plugin_id, [])]
