"""
Vigile — Nodes API: insights, profiling, and anomaly analysis endpoints
"""

from __future__ import annotations

import logging
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated  # type: ignore[attr-defined]


from fastapi import Depends, HTTPException, Path, status

from master.api.demo_data import get_demo_node, is_demo
from master.api.deps import DB, Insights, get_locale, get_node_manager, require_role
from master.api.nodes_router import router
from master.core.insights import DiagnosticReport, HeavyProcessConfig, NodeProfile
from master.core.node_manager import NodeManager

import time

logger = logging.getLogger(__name__)


@router.get(
    "/{node_id}/insights",
    summary="Get real-time insights for a node (Operator+)",
)
async def get_node_insights(
    node_id: Annotated[str, Path(description="Node UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    im: Insights,
    nm: NodeManager = Depends(get_node_manager),
    locale: str = Depends(get_locale),
) -> dict:
    """Fetch real-time natural language insights for CPU, memory, and disk usage."""
    if is_demo(claims):
        insights = []
        if node_id in ("demo-node-01", "demo-node-99"):
            insights = [
                {
                    "type": "disk",
                    "severity": "warning",
                    "icon": "⚠️",
                    "headline": (
                        "Disk full in 1 week and 3 days"
                        if locale == "en"
                        else "Disque plein dans 1 semaine et 3j"
                    ),
                    "detail": (
                        "+2.4 GB / day growth rate"
                        if locale == "en"
                        else "Taux de croissance de +2.4 Go / jour"
                    ),
                    "raw": {"used_percent": 80.0, "free_gb": 24.0, "growth_gb_per_day": 2.4},
                },
                {
                    "type": "cpu",
                    "severity": "warning",
                    "icon": "🔥",
                    "headline": (
                        "Higher than normal load · Plex Transcoding"
                        if locale == "en"
                        else "Charge supérieure à la normale · Transcodage Plex"
                    ),
                    "detail": (
                        "Sustained load (60%) attributed to Plex container"
                        if locale == "en"
                        else "Charge soutenue (60%) imputée au conteneur Plex"
                    ),
                    "raw": {
                        "cpu_percent": 60.0,
                        "culprit_container": "plex",
                        "culprit_service": None,
                    },
                },
                {
                    "type": "ram",
                    "severity": "ok",
                    "icon": "✅",
                    "headline": "Stable memory" if locale == "en" else "Mémoire stable",
                    "detail": (
                        "No swap pressure" if locale == "en" else "Aucune pression d'échange (swap)"
                    ),
                    "raw": {
                        "used_percent": 65.0,
                        "used_gb": 10.4,
                        "total_gb": 16.0,
                        "swap_used_mb": 0.0,
                    },
                },
            ]
        elif node_id == "demo-node-02":
            insights = [
                {
                    "type": "disk",
                    "severity": "ok",
                    "icon": "✅",
                    "headline": "Stable disk" if locale == "en" else "Disque stable",
                    "detail": (
                        "More than 6 months of space remaining"
                        if locale == "en"
                        else "Plus de 6 mois d'autonomie restants"
                    ),
                    "raw": {"used_percent": 42.0},
                },
                {
                    "type": "cpu",
                    "severity": "ok",
                    "icon": "✅",
                    "headline": "Stable CPU" if locale == "en" else "CPU stable",
                    "detail": "Low usage" if locale == "en" else "Faible utilisation",
                    "raw": {"cpu_percent": 18.7},
                },
                {
                    "type": "ram",
                    "severity": "ok",
                    "icon": "✅",
                    "headline": "Stable memory" if locale == "en" else "Mémoire stable",
                    "detail": (
                        "No swap pressure" if locale == "en" else "Aucune pression d'échange (swap)"
                    ),
                    "raw": {"used_percent": 57.8},
                },
            ]
        else:
            insights = [
                {
                    "type": "disk",
                    "severity": "ok",
                    "icon": "✅",
                    "headline": "Stable disk" if locale == "en" else "Disque stable",
                    "detail": (
                        "More than 6 months of space remaining"
                        if locale == "en"
                        else "Plus de 6 mois d'autonomie restants"
                    ),
                    "raw": {"used_percent": 25.0},
                },
                {
                    "type": "cpu",
                    "severity": "ok",
                    "icon": "✅",
                    "headline": "Stable CPU" if locale == "en" else "CPU stable",
                    "detail": "Low usage" if locale == "en" else "Faible utilisation",
                    "raw": {"cpu_percent": 12.0},
                },
                {
                    "type": "ram",
                    "severity": "ok",
                    "icon": "✅",
                    "headline": "Stable memory" if locale == "en" else "Mémoire stable",
                    "detail": (
                        "No swap pressure" if locale == "en" else "Aucune pression d'échange (swap)"
                    ),
                    "raw": {"used_percent": 30.0},
                },
            ]
        return {
            "node_id": node_id,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "insights": insights,
            "data_window_hours": 72.0,
            "observation_ready": True,
            "profile_confidence": "high",
            "next_profile_refresh_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 12 * 3600)
            ),
            "profile_generated_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 12 * 3600)
            ),
        }

    # Verify node exists
    node = await nm.get_node(db, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    return await im.get_insights(node_id, db, nm, locale=locale)


@router.post(
    "/{node_id}/profile/regenerate",
    response_model=NodeProfile,
    summary="Regenerate node profile manually (Operator+)",
)
async def regenerate_node_profile(
    node_id: Annotated[str, Path(description="Node UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    im: Insights,
    nm: NodeManager = Depends(get_node_manager),
    locale: str = Depends(get_locale),
) -> NodeProfile:
    """Manually trigger LLM/heuristic profile regeneration for a node."""
    if is_demo(claims):
        return NodeProfile(
            node_id=node_id,
            known_heavy_processes=[
                HeavyProcessConfig(
                    container_name="plex",
                    cpu_threshold_percent=50.0,
                    label="Plex Transcoding" if locale == "en" else "Transcodage Plex",
                )
            ],
            baseline_ram_percent=70.0,
            context_label="Homelab Server" if locale == "en" else "Serveur homelab",
        )

    # Verify node exists
    node = await nm.get_node(db, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    try:
        profile = await im.generate_profile(node_id, db, nm, force=True, locale=locale)
        im.invalidate_cache(node_id)
        return profile
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate profile: {e}",
        )


@router.post(
    "/{node_id}/insights/analyze",
    response_model=DiagnosticReport,
    summary="Analyze anomaly using LLM diagnostic (Operator+)",
)
async def analyze_node_anomaly(
    node_id: Annotated[str, Path(description="Node UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    im: Insights,
    nm: NodeManager = Depends(get_node_manager),
    locale: str = Depends(get_locale),
) -> DiagnosticReport:
    """Analyze current metrics and services with LLM to produce an anomaly diagnostic report."""
    if is_demo(claims):
        return DiagnosticReport(
            headline=(
                "Plex transcoding task detected"
                if locale == "en"
                else "Tâche de transcodage Plex détectée"
            ),
            explanation=(
                "The Plex container is currently transcoding a 4K H.265 video stream to 1080p H.264 for client 'iPad-de-Flavio'. This operation intensively uses the CPU (60%)."
                if locale == "en"
                else "Le conteneur Plex effectue actuellement le transcodage d'un flux vidéo 4K H.265 vers 1080p H.264 pour le client 'iPad-de-Flavio'. Cette opération sollicite intensément le processeur (60%)."
            ),
            suggested_action=(
                "No action required. If this impacts other services, you can limit Plex CPU or enable hardware acceleration (GPU transcoding)."
                if locale == "en"
                else "Aucune action requise. Si cela impacte d'autres services, vous pouvez limiter le CPU de Plex ou activer l'accélération matérielle (transcodage GPU)."
            ),
            correlated_cause=[],
        )

    # Verify node exists
    node = await nm.get_node(db, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    try:
        report = await im.analyze_anomaly(node_id, db, nm, locale=locale)
        return report
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Anomaly analysis failed: {e}",
        )
