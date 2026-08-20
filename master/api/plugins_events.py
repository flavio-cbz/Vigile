from __future__ import annotations

"""
Vigile — Flux SSE des invalidations de plugins (S4 / T26).

Canal ``plugins.invalidated`` : diffusé à chaque swap atomique du registre
(``plugin_engine._swap_registry``) — le plan (migration_master_plugins.md §S4,
D3) précise explicitement que ce canal est du NOUVEAU travail, jamais une
réutilisation de ``/api/stream`` (événements nœuds uniquement).

Modèle calqué sur ``nodes_events.py`` :
  - auth par ``?token=<jwt>`` — EventSource ne peut pas envoyer d'en-têtes
    Authorization, le même vérificateur d'access token que la REST API est
    réutilisé (``verify_access_token`` → 401 sur échec) ;
  - abonnement EventBus + replay du ring buffer au (re)connect ;
  - heartbeat 25 s + en-têtes anti-cache.

Filtrage de permission (plan §Mineur 1, non-optionnel) : un événement n'est
livré qu'aux utilisateurs dont ``(role >= min_role ∧ p ∈ permissions)`` pour
le plugin concerné — pas de fuite d'information sur l'état des plugins. Un
événement "unloaded" (manifest déjà retiré du registre) ne peut plus être
vérifié → fail-closed : seuls les admins le reçoivent.
"""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from master.api.deps import get_bus
from master.core import permissions as permissions_module
from master.core.event_bus import EventBus
from master.core.security_manager import (
    ExpiredTokenError,
    SecurityError,
    get_security_instance,
)

router = APIRouter(prefix="/api/plugins/events", tags=["plugins-events"])
logger = logging.getLogger(__name__)

_SSE_TOPIC = "plugins.invalidated"
# Intervalle de heartbeat SSE (commentaire `: keepalive`) quand aucun
# événement n'arrive. Constant de module pour permettre aux tests de la
# raccourcir (évite des attentes de 25 s).
_KEEPALIVE_SECONDS = 25.0


def _get_engine() -> Any:
    """Résout l'instance PluginEngine active (même seam que ``plugins.py``)."""
    from master.core.plugin_manager import plugin_engine
    return plugin_engine


def _can_receive_event(claims: dict[str, Any], plugin_id: str) -> bool:
    """Filtre S7 à la livraison : ``(role >= min_role ∧ p ∈ permissions)``.

    - admin : reçoit tout (le catalogue ne peut pas restreindre un admin) ;
    - plugin sans manifest V2 servi ou sans permissions déclarées : modèle
      plat (héritage V1) → autorisé (parité avec ``check_permission_intersection``) ;
    - plugin déchargé/inconnu (manifest absent) : vérification impossible →
      refusé (fail-closed, pas de fuite d'état) ;
    - sinon : autorisé si une permission déclarée du manifest intersecte le
      catalogue avec un ``min_role`` satisfait par le rôle.
    """
    role = str(claims.get("role", "viewer"))
    if role == "admin":
        return True
    engine = _get_engine()
    manifest = engine.get_served_manifest(plugin_id) if engine is not None else None
    if manifest is None:
        return False  # déchargé ou inconnu → fail-closed
    names = permissions_module.manifest_permission_names(
        getattr(manifest, "permissions", None)
    )
    if not names:
        return True  # modèle plat (plugin V1 hérité)
    user_level = permissions_module.role_level(role)
    for name in names:
        entry = permissions_module.PERMISSION_CATALOG.get(name)
        if entry is None:
            continue
        if entry.resource_contract == plugin_id and user_level >= permissions_module.role_level(
            entry.min_role
        ):
            return True
    return False


async def _sse_stream(
    bus: EventBus, request: Request, claims: dict[str, Any]
) -> AsyncGenerator[str, None]:
    queue = bus.subscribe(_SSE_TOPIC)
    try:
        # Replay du ring buffer au (re)connect : les clients frais synchronisent.
        for evt in bus.replay(_SSE_TOPIC):
            if await request.is_disconnected():
                return
            payload = evt["payload"]
            if _can_receive_event(claims, payload.get("plugin_id", "")):
                yield f"event: {_SSE_TOPIC}\ndata: {json.dumps(payload)}\n\n"

        while True:
            if await request.is_disconnected():
                break
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            payload = evt["payload"]
            if _can_receive_event(claims, payload.get("plugin_id", "")):
                yield f"event: {_SSE_TOPIC}\ndata: {json.dumps(payload)}\n\n"
    finally:
        bus.unsubscribe(_SSE_TOPIC, queue)


@router.get("/stream")
async def stream(
    request: Request,
    token: Optional[str] = Query(default=None),
    bus: EventBus = Depends(get_bus),
) -> StreamingResponse:
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing token query parameter (EventSource cannot send Authorization headers)",
        )
    try:
        claims = get_security_instance().verify_access_token(token)
    except ExpiredTokenError:
        raise HTTPException(status_code=401, detail="Token has expired") from None
    except SecurityError:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from None

    return StreamingResponse(
        _sse_stream(bus, request, claims),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
