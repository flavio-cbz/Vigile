"""
Vigile — Insights Manager

Implements the 3-phase insights and profiling system:
  - Phase 1: structured LLM profiling and fallback heuristic rules
  - Phase 2: real-time rule-based insights (disk regression, CPU/RAM thresholds)
  - Phase 3: real-time diagnostic LLM analysis for anomalies
"""

import asyncio
import enum
import json
import logging
import re
import time
from typing import Any

import aiosqlite
from pydantic import BaseModel, Field

from master.core.llm_client import LLMClient
from master.core.node_manager import NodeManager
from master.core.structured_llm import StructuredLLM

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models for Node Profile
# ---------------------------------------------------------------------------


class HeavyProcessConfig(BaseModel):
    container_name: str | None = Field(default=None)
    service_name: str | None = Field(default=None)
    cpu_threshold_percent: float = Field(
        description="CPU percentage threshold above which this is considered active"
    )
    label: str = Field(description="Human-friendly label (e.g. 'Transcodage Plex')")


class ServiceCategory(str, enum.Enum):
    MEDIA = "media"
    DATABASE = "database"
    LLM = "llm"
    REVERSE_PROXY = "reverse_proxy"
    CI_CD = "ci_cd"
    SYSTEM = "system"
    MONITORING = "monitoring"
    OTHER = "other"


class ClassifiedService(BaseModel):
    name: str
    service_type: str
    category: ServiceCategory
    label: str
    cpu_threshold_percent: float


class NodeServiceClassification(BaseModel):
    services: list[ClassifiedService]
    context_label: str
    baseline_ram_percent: float


_CONTAINER_PATTERNS: list[tuple[str, ServiceCategory, str, float]] = [
    (r"plex|jellyfin|emby", ServiceCategory.MEDIA, "Transcodage Multimédia (Plex/Jellyfin)", 50.0),
    (r"postgres(ql)?|pg-\w+", ServiceCategory.DATABASE, "Requêtes Base de Données (PostgreSQL)", 40.0),
    (r"mysql|mariadb", ServiceCategory.DATABASE, "Requêtes Base de Données (MySQL)", 40.0),
    (r"litellm|ollama|vllm|openai|localai|text-generation-inference|tgi", ServiceCategory.LLM, "Passerelle API LLM (IA Générative)", 40.0),
    (r"nginx|traefik|haproxy|caddy", ServiceCategory.REVERSE_PROXY, "Trafic Web (Reverse Proxy)", 30.0),
    (r"(runner|gitlab|jenkins|drone|woodpecker)", ServiceCategory.CI_CD, "Compilation / Pipeline CI-CD", 60.0),
    (r"(prometheus|grafana|netdata|node-exporter|telegraf|influxdb|victoria-metrics)", ServiceCategory.MONITORING, "Monitoring / Métriques", 20.0),
]

_SERVICE_PATTERNS: list[tuple[str, ServiceCategory, str, float]] = [
    (r"plex", ServiceCategory.MEDIA, "Transcodage Plex Media Server", 50.0),
    (r"postgresql|mysql|mariadb", ServiceCategory.DATABASE, "Activité Base de Données", 45.0),
    (r"nginx|apache2?|httpd", ServiceCategory.REVERSE_PROXY, "Pic de Trafic Web", 35.0),
    (r"fail2ban", ServiceCategory.SYSTEM, "Analyse d'intrusions Fail2ban", 20.0),
]

_IMAGE_PATTERNS: list[tuple[str, ServiceCategory, str, float]] = [
    (r"litellm|ollama|vllm|openai|localai|tgi", ServiceCategory.LLM, "Passerelle API LLM (IA Générative)", 40.0),
    (r"^(nginx|traefik|haproxy|caddy)(:|$)", ServiceCategory.REVERSE_PROXY, "Trafic Web (Reverse Proxy)", 30.0),
    (r"postgres|mysql|mariadb|redis", ServiceCategory.DATABASE, "Service Base de Données", 40.0),
]


def _match_classification(
    name: str,
    patterns: list[tuple[str, ServiceCategory, str, float]],
) -> tuple[ServiceCategory, str, float] | None:
    name_lower = name.lower()
    for pattern, category, label, threshold in patterns:
        if re.search(pattern, name_lower):
            return category, label, threshold
    return None


def _guess_context(hostname: str, containers: list[dict[str, Any]]) -> str:
    host_lower = hostname.lower()
    if "web" in host_lower or "nginx" in host_lower:
        return "Serveur Web / Applicatif"
    elif "db" in host_lower or "sql" in host_lower or "postgres" in host_lower:
        return "Serveur de Base de Données"
    elif (
        "plex" in host_lower
        or "media" in host_lower
        or "nas" in host_lower
        or any("plex" in c.get("name", "").lower() for c in containers)
    ):
        return "Homelab Médias & Stockage"
    return "Serveur général"


class NodeProfile(BaseModel):
    node_id: str
    known_heavy_processes: list[HeavyProcessConfig] = Field(default_factory=list)
    baseline_ram_percent: float = Field(
        default=70.0, description="Expected baseline RAM utilization percentage"
    )
    context_label: str = Field(
        default="Serveur homelab", description="Overall context label of the node"
    )


# ---------------------------------------------------------------------------
# Pydantic schema for Phase 3 Diagnostic Analysis
# ---------------------------------------------------------------------------


class DiagnosticReport(BaseModel):
    """Structured diagnostic report generated by LLM on demand during anomaly."""

    headline: str = Field(description="Short human-friendly summary of the diagnostic")
    explanation: str = Field(description="Detailed explanation of what is causing the load")
    suggested_action: str = Field(description="Remediation action recommended for the user")


# ---------------------------------------------------------------------------
# Insights Manager
# ---------------------------------------------------------------------------


class InsightsManager:
    """
    Manages node profiling, real-time insights generation, and anomaly diagnostics.
    Follows Dependency Injection: receives LLMClient inside constructor.
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm_client = llm_client
        self._sllm = StructuredLLM(llm_client) if llm_client else None

    # -----------------------------------------------------------------------
    # Phase 1: Profile Generation
    # -----------------------------------------------------------------------

    async def generate_profile(
        self,
        node_id: str,
        db: aiosqlite.Connection,
        nm: NodeManager,
        force: bool = False,
        locale: str = "fr",
    ) -> NodeProfile:
        logger.info("Generating profile for node %s (force=%s)...", node_id, force)

        node = await nm.get_node(db, node_id)
        if not node:
            raise ValueError(f"Node not found: {node_id}")

        hostname = node.get("hostname") or ""

        services: list[dict[str, Any]] = []
        containers: list[dict[str, Any]] = []

        cached_services = node.get("cached_services_json")
        if cached_services:
            try:
                services = json.loads(cached_services)
            except Exception:
                pass

        cached_containers = node.get("cached_containers_json")
        if cached_containers:
            try:
                containers = json.loads(cached_containers)
            except Exception:
                pass

        if node.get("online"):
            if not services:
                try:
                    from master.core.plugin_helpers import parse_service_list

                    result = await nm.send_intent(node_id, {"action": "LIST_SERVICES"}, timeout=8.0)
                    if result.get("success"):
                        parsed = parse_service_list(result.get("output", ""))
                        if parsed:
                            services = parsed
                except Exception as e:
                    logger.warning("Profile gen: failed live services query: %s", e)

            if not containers:
                try:
                    from master.core.plugin_helpers import parse_container_list

                    result = await nm.send_intent(
                        node_id, {"action": "LIST_CONTAINERS"}, timeout=8.0
                    )
                    if result.get("success"):
                        parsed = parse_container_list(result.get("output", ""))
                        if parsed:
                            containers = parsed
                except Exception as e:
                    logger.warning("Profile gen: failed live containers query: %s", e)

        classification = await self.classify_node_services(
            node_id, db, nm, locale=locale, services=services, containers=containers
        )

        context_label = classification.context_label
        baseline_ram_percent = classification.baseline_ram_percent

        known_heavy = [
            HeavyProcessConfig(
                container_name=s.name if s.service_type == "container" else None,
                service_name=s.name if s.service_type == "systemd" else None,
                cpu_threshold_percent=s.cpu_threshold_percent,
                label=s.label,
            )
            for s in classification.services
        ]

        profile = NodeProfile(
            node_id=node_id,
            known_heavy_processes=known_heavy,
            baseline_ram_percent=baseline_ram_percent,
            context_label=context_label,
        )

        logger.info("Profile ready for node %s", node_id)

        now = time.time()
        await db.execute(
            """
            UPDATE nodes SET
                insight_profile = ?,
                insight_profile_generated_at = ?,
                cached_services_json = ?,
                cached_containers_json = ?
            WHERE id = ?
            """,
            (
                profile.model_dump_json(),
                now,
                json.dumps(services) if services else node.get("cached_services_json"),
                json.dumps(containers) if containers else node.get("cached_containers_json"),
                node_id,
            ),
        )
        await db.commit()

        return profile

    def _classify_services_fallback(
        self,
        services: list[dict[str, Any]],
        containers: list[dict[str, Any]],
    ) -> list[HeavyProcessConfig]:
        known_heavy: list[HeavyProcessConfig] = []

        for c in containers:
            match = _match_classification(c.get("name", ""), _CONTAINER_PATTERNS)
            if not match:
                match = _match_classification(c.get("image", ""), _IMAGE_PATTERNS)
            if match:
                known_heavy.append(
                    HeavyProcessConfig(
                        container_name=c.get("name"),
                        cpu_threshold_percent=match[2],
                        label=match[1],
                    )
                )

        for s in services:
            match = _match_classification(s.get("name", ""), _SERVICE_PATTERNS)
            if match:
                known_heavy.append(
                    HeavyProcessConfig(
                        service_name=s.get("name"),
                        cpu_threshold_percent=match[2],
                        label=match[1],
                    )
                )

        return known_heavy

    async def classify_node_services(
        self,
        node_id: str,
        db: aiosqlite.Connection,
        nm: NodeManager,
        locale: str = "fr",
        services: list[dict[str, Any]] | None = None,
        containers: list[dict[str, Any]] | None = None,
    ) -> NodeServiceClassification:
        logger.info("Classifying services for node %s...", node_id)
        node = await nm.get_node(db, node_id)
        if not node:
            raise ValueError(f"Node not found: {node_id}")

        hostname = node.get("hostname") or ""

        if services is None:
            services = []
            cached = node.get("cached_services_json")
            if cached:
                try:
                    services = json.loads(cached)
                except Exception:
                    pass

        if containers is None:
            containers = []
            cached = node.get("cached_containers_json")
            if cached:
                try:
                    containers = json.loads(cached)
                except Exception:
                    pass

        if self._sllm and self._llm_client and self._llm_client.base_url:
            lang = (
                "Write the label and context_label in English."
                if locale == "en"
                else "Écris le label et le context_label en français."
            )
            try:
                messages = [
                    {
                        "role": "user",
                        "content": (
                            f"Classify every container and service running on server '{node.get('name')}'.\n\n"
                            f"Systemd services:\n{json.dumps(services[:30], indent=2)}\n\n"
                            f"Docker containers (with image):\n{json.dumps(containers[:30], indent=2)}\n\n"
                            f"For each entry, determine:\n"
                            f"- category: one of {[e.value for e in ServiceCategory]}\n"
                            f"- label: short human-friendly description in French\n"
                            f"- cpu_threshold_percent: CPU % above which this process is considered actively loaded "
                            f"(e.g. 50 for Plex transcoding, 30 for a reverse proxy, 40 for a database)\n"
                            f"- service_type: \"container\" or \"systemd\"\n\n"
                            f"Also suggest:\n"
                            f"- context_label: overall role of this server (e.g. \"Serveur Médias\", \"Base de Données\", \"Passerelle LLM\")\n"
                            f"- baseline_ram_percent: normal baseline RAM usage for this server\n\n"
                            f"{lang}"
                        ),
                    }
                ]
                result = await self._sllm.create(
                    response_model=NodeServiceClassification,
                    messages=messages,
                    max_retries=2,
                )
                logger.info("LLM classification successful for node %s", node_id)
                return result
            except Exception as ex:
                logger.warning("LLM classification failed for node %s: %s", node_id, ex)

        known_heavy = self._classify_services_fallback(services, containers)
        context = _guess_context(hostname, containers)
        classified = [
            ClassifiedService(
                name=h.container_name or h.service_name or "",
                service_type="container" if h.container_name else "systemd",
                category=ServiceCategory.OTHER,
                label=h.label,
                cpu_threshold_percent=h.cpu_threshold_percent,
            )
            for h in known_heavy
        ]
        return NodeServiceClassification(
            services=classified,
            context_label=context,
            baseline_ram_percent=65.0,
        )

    def generate_fallback_profile(
        self,
        node_id: str,
        hostname: str,
        services: list[dict[str, Any]],
        containers: list[dict[str, Any]],
    ) -> NodeProfile:
        known_heavy = self._classify_services_fallback(services, containers)
        context = _guess_context(hostname, containers)
        return NodeProfile(
            node_id=node_id,
            known_heavy_processes=known_heavy,
            baseline_ram_percent=65.0,
            context_label=context,
        )

    # -----------------------------------------------------------------------
    # Phase 2: Real-time Insights (Deterministic)
    # -----------------------------------------------------------------------

    async def get_insights(
        self,
        node_id: str,
        db: aiosqlite.Connection,
        nm: NodeManager,
        locale: str = "fr",
    ) -> dict[str, Any]:
        """
        Produce real-time insights for a node (Phase 2).
        Calculates disk slope on-the-fly and evaluates current CPU/RAM.
        """
        node = await nm.get_node(db, node_id)
        if not node:
            return {"node_id": node_id, "insights": [], "profile_confidence": "low"}

        # 1. Trigger profile generation automatically if missing and online
        profile_json = node.get("insight_profile")
        if not profile_json:
            if node.get("online"):
                # Spawn generation background task
                asyncio.create_task(self.generate_profile(node_id, db, nm, locale=locale))
                return {
                    "node_id": node_id,
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "insights": [
                        {
                            "type": "status",
                            "severity": "info",
                            "icon": "🔄",
                            "headline": "Analyse du profil en cours",
                            "detail": "Vigilbot identifie les services et configure les seuils de charge...",
                        }
                    ],
                    "profile_confidence": "low",
                }
            else:
                return {
                    "node_id": node_id,
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "insights": [
                        {
                            "type": "status",
                            "severity": "warning",
                            "icon": "⚠️",
                            "headline": "Profil manquant",
                            "detail": "Le serveur doit être connecté en ligne pour initialiser son profil d'insights.",
                        }
                    ],
                    "profile_confidence": "low",
                }

        profile = NodeProfile.model_validate_json(profile_json)

        # 2. Get latest metrics snapshot
        latest_snap = None
        async with db.execute(
            "SELECT * FROM metrics_snapshots WHERE node_id = ? ORDER BY collected_at DESC LIMIT 1",
            (node_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                latest_snap = dict(row)

        if not latest_snap:
            return {
                "node_id": node_id,
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "insights": [
                    {
                        "type": "status",
                        "severity": "warning",
                        "icon": "🔄",
                        "headline": "En attente de métriques",
                        "detail": "Aucun rapport de métriques n'a encore été stocké pour ce serveur.",
                    }
                ],
                "profile_confidence": "medium",
            }

        insights = []

        # --- A. DISK INSIGHT (On-the-fly Linear Regression) ---
        disk_insight = await self._calculate_disk_insight(node_id, db, latest_snap)
        if disk_insight:
            insights.append(disk_insight)

        # --- B. CPU INSIGHT ---
        cpu_insight = self._calculate_cpu_insight(latest_snap, profile, node)
        if cpu_insight:
            insights.append(cpu_insight)

        # --- C. RAM INSIGHT ---
        ram_insight = self._calculate_ram_insight(latest_snap, profile)
        if ram_insight:
            insights.append(ram_insight)

        return {
            "node_id": node_id,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "insights": insights,
            "profile_confidence": "high" if node.get("online") else "medium",
        }

    async def _calculate_disk_insight(
        self,
        node_id: str,
        db: aiosqlite.Connection,
        latest_snap: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Calculate linear regression slope of disk usage and return insight."""
        disk_total = latest_snap.get("disk_total_bytes", 0)
        disk_used = latest_snap.get("disk_used_bytes", 0)
        disk_percent = latest_snap.get("disk_percent", 0.0)

        if disk_total == 0:
            return None

        # Query metrics snapshots from the last 24 hours (86400 seconds)
        now = time.time()
        limit_time = now - 86400

        snapshots = []
        async with db.execute(
            """
            SELECT collected_at, disk_used_bytes
            FROM metrics_snapshots
            WHERE node_id = ? AND collected_at >= ?
            ORDER BY collected_at ASC
            LIMIT 150
            """,
            (node_id, limit_time),
        ) as cursor:
            async for r in cursor:
                snapshots.append(dict(r))

        free_bytes = disk_total - disk_used
        free_gb = free_bytes / (1024**3)
        used_percent = round(disk_percent, 1)

        # Calculate slope only with enough snapshots AND sufficient time span.
        # With fewer points (or a very short window), filesystem noise yields
        # absurd extrapolations (e.g. +39000 GB/day from a 60s delta).
        slope = 0.0  # GB per day
        min_snapshots = 5
        min_timespan_seconds = 1800  # 30 minutes
        timespan = (
            (snapshots[-1]["collected_at"] - snapshots[0]["collected_at"])
            if len(snapshots) >= 2
            else 0
        )
        if len(snapshots) >= min_snapshots and timespan >= min_timespan_seconds:
            t0 = snapshots[0]["collected_at"]
            # Convert collected_at to days relative to first snapshot to avoid floating overflow
            x = [(s["collected_at"] - t0) / 86400.0 for s in snapshots]
            y = [s["disk_used_bytes"] / (1024**3) for s in snapshots]

            n = len(snapshots)
            sum_x = sum(x)
            sum_y = sum(y)
            sum_xx = sum(xi * xi for xi in x)
            sum_xy = sum(xi * yi for xi, yi in zip(x, y))

            denominator = n * sum_xx - sum_x * sum_x
            if abs(denominator) > 1e-6:
                slope = (n * sum_xy - sum_x * sum_y) / denominator
                if slope < 0.0:
                    slope = 0.0  # Ignore shrinking disk for the "full in" prediction
            else:
                slope = 0.0

        if slope > 0.01:  # Growth rate of at least 10 MB per day
            days_left = free_gb / slope

            if days_left < 14:
                severity = "critical"
                icon = "🚨"
            elif days_left < 60:
                severity = "warning"
                icon = "⚠️"
            else:
                severity = "ok"
                icon = "✅"

            # Human friendly time estimation
            if days_left < 1:
                headline = "Disque plein dans moins d'un jour !"
            elif days_left < 7:
                headline = f"Disque plein dans ~{round(days_left)} jours"
            else:
                weeks = int(days_left / 7)
                days = int(days_left % 7)
                if weeks < 5:
                    day_str = f" et {days}j" if days > 0 else ""
                    headline = f"Disque plein dans {weeks} sem{day_str}"
                else:
                    months = int(days_left / 30)
                    headline = f"Disque plein dans ~{months} mois"

            detail = f"Taux de croissance de +{slope:.2f} Go / jour"
        else:
            severity = "ok"
            icon = "✅"
            headline = "Disque stable"
            detail = "Plus de 6 mois d'autonomie restants"

        return {
            "type": "disk",
            "severity": severity,
            "icon": icon,
            "headline": headline,
            "detail": detail,
            "raw": {
                "used_percent": used_percent,
                "free_gb": round(free_gb, 1),
                "growth_gb_per_day": round(slope, 3),
            },
        }

    def _calculate_cpu_insight(
        self,
        latest_snap: dict[str, Any],
        profile: NodeProfile,
        node: dict[str, Any],
    ) -> dict[str, Any]:
        """Match current CPU load against node profile rules and active processes."""
        cpu_percent = latest_snap.get("cpu_percent", 0.0)

        top_procs: list[dict[str, Any]] = []
        raw_top = latest_snap.get("top_processes_json")
        if isinstance(raw_top, str):
            try:
                top_procs = json.loads(raw_top)
            except Exception:
                pass
        elif isinstance(latest_snap.get("top_processes"), list):
            top_procs = latest_snap["top_processes"]

        active_containers = []
        cached_containers = node.get("cached_containers_json")
        if cached_containers:
            try:
                active_containers = [
                    c.get("name")
                    for c in json.loads(cached_containers)
                    if c.get("state") == "running" or "up" in c.get("status", "").lower()
                ]
            except Exception:
                pass

        active_services = []
        cached_services = node.get("cached_services_json")
        if cached_services:
            try:
                active_services = [
                    s.get("service")
                    for s in json.loads(cached_services)
                    if s.get("state") == "active"
                ]
            except Exception:
                pass

        culprit = None
        culprit_pct: float | None = None
        headline = "Serveur au repos"
        detail = "Activités d'arrière-plan normales"
        icon = "💤"

        for p in profile.known_heavy_processes:
            is_running = False
            if p.container_name and p.container_name in active_containers:
                is_running = True
            elif p.service_name and p.service_name in active_services:
                is_running = True

            if is_running and cpu_percent >= p.cpu_threshold_percent:
                if not culprit or p.cpu_threshold_percent > culprit.cpu_threshold_percent:
                    culprit = p

        if culprit and top_procs:
            culprit_name = (culprit.container_name or culprit.service_name or "").lower()
            for tp in top_procs:
                tp_name = tp.get("name", "").lower()
                if culprit_name in tp_name or tp_name in culprit_name:
                    culprit_pct = tp.get("cpu_percent")
                    break

        if cpu_percent > 75:
            if culprit:
                severity = "warning"
                icon = "🔥"
                headline = f"Activité intense · {culprit.label}"
                actual = f" ({culprit_pct:.0f}% CPU)" if culprit_pct else ""
                detail = f"Charge soutenue ({cpu_percent:.0f}%) imputée à {culprit.container_name or culprit.service_name}{actual}"
            elif top_procs and top_procs[0].get("cpu_percent", 0) > 10:
                severity = "warning"
                icon = "⚠️"
                top = top_procs[0]
                headline = f"Charge élevée anormale"
                detail = f"Processus {top['name']} actif ({top['cpu_percent']:.0f}%)"
            else:
                severity = "warning"
                icon = "⚠️"
                headline = "Charge élevée anormale"
                detail = "Aucun processus lourd connu n'est actif sur le système."
        elif cpu_percent > 40:
            if culprit:
                severity = "info"
                icon = "⚡"
                headline = f"Charge modérée · {culprit.label}"
                actual = f" ({culprit_pct:.0f}%)" if culprit_pct else ""
                detail = f"Processus {culprit.container_name or culprit.service_name} actif ({cpu_percent:.0f}%){actual}"
            elif top_procs and top_procs[0].get("cpu_percent", 0) > 5:
                severity = "info"
                icon = "🏃"
                top = top_procs[0]
                headline = f"Activité modérée"
                detail = f"Processus {top['name']} actif ({top['cpu_percent']:.0f}%)"
            else:
                severity = "info"
                icon = "🏃"
                headline = "Activité modérée"
                detail = f"Charge générale du serveur à {cpu_percent:.0f}%"
        else:
            severity = "ok"
            icon = "✅"
            headline = "CPU stable"
            detail = "Serveur calme et stable"

        return {
            "type": "cpu",
            "severity": severity,
            "icon": icon,
            "headline": headline,
            "detail": detail,
            "raw": {
                "cpu_percent": round(cpu_percent, 1),
                "culprit_container": culprit.container_name if culprit else None,
                "culprit_service": culprit.service_name if culprit else None,
                "top_processes": top_procs[:5] if top_procs else None,
            },
        }

    def _calculate_ram_insight(
        self, latest_snap: dict[str, Any], profile: NodeProfile
    ) -> dict[str, Any]:
        """Assess RAM and swap usage against profile baseline."""
        mem_percent = latest_snap.get("mem_percent", 0.0)
        mem_total = latest_snap.get("mem_total_bytes", 0)
        mem_used = latest_snap.get("mem_used_bytes", 0)
        swap_used = latest_snap.get("swap_used_bytes", 0)

        used_gb = mem_used / (1024**3)
        total_gb = mem_total / (1024**3)
        swap_mb = swap_used / (1024 * 1024)

        baseline = profile.baseline_ram_percent

        if mem_percent > 90:
            severity = "warning"
            icon = "⚠️"
            headline = "RAM presque saturée"
            detail = "Risque potentiel de ralentissement (OOM)"
        elif mem_percent > baseline:
            severity = "info"
            icon = "🐏"
            headline = "RAM active"
            detail = f"Utilisation supérieure à la ligne de base habituelle ({baseline:.0f}%)"
        else:
            severity = "ok"
            icon = "✅"
            headline = "Mémoire stable"
            detail = (
                "Aucune pression d'échange (swap)"
                if swap_mb < 50
                else f"Swap utilisé : {swap_mb:.0f} Mo"
            )

        return {
            "type": "ram",
            "severity": severity,
            "icon": icon,
            "headline": headline,
            "detail": detail,
            "raw": {
                "used_percent": round(mem_percent, 1),
                "used_gb": round(used_gb, 1),
                "total_gb": round(total_gb, 1),
                "swap_used_mb": round(swap_mb, 1),
            },
        }

    # -----------------------------------------------------------------------
    # Phase 3: Anomaly AI Analysis (On-Demand)
    # -----------------------------------------------------------------------

    async def analyze_anomaly(
        self,
        node_id: str,
        db: aiosqlite.Connection,
        nm: NodeManager,
        locale: str = "fr",
    ) -> DiagnosticReport:
        """Call LLM Client on demand to analyze processes and diagnose anomaly."""
        logger.info("Running AI diagnostic for anomaly on node %s...", node_id)
        if not self._sllm:
            return DiagnosticReport(
                headline="Diagnostic IA temporairement indisponible",
                explanation="Le service d'IA n'est pas configuré sur ce serveur Master.",
                suggested_action="Veuillez configurer la clé LLM dans l'environnement du Master.",
            )

        node = await nm.get_node(db, node_id)
        if not node:
            raise ValueError(f"Node not found: {node_id}")

        # Fetch active containers and services lists
        cached_services = node.get("cached_services_json") or "[]"
        cached_containers = node.get("cached_containers_json") or "[]"

        # Get latest metrics
        latest_snap = None
        async with db.execute(
            "SELECT * FROM metrics_snapshots WHERE node_id = ? ORDER BY collected_at DESC LIMIT 1",
            (node_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                latest_snap = dict(row)

        snap_str = json.dumps(latest_snap) if latest_snap else "Metrics unavailable"

        lang_instruction = (
            "You must write the explanation, headline, and suggested_action in English."
            if locale == "en"
            else "Tu dois obligatoirement rédiger l'explication (explanation), le titre (headline) et l'action suggérée (suggested_action) en français."
        )
        messages = [
            {
                "role": "user",
                "content": (
                    f"Analyze this server anomaly for node '{node.get('name')}':\n"
                    f"- Active Services: {cached_services}\n"
                    f"- Active Containers: {cached_containers}\n"
                    f"- Current Metrics: {snap_str}\n\n"
                    f"Diagnose what is causing the anomaly and suggest remediation actions. "
                    f"{lang_instruction}"
                ),
            }
        ]

        try:
            report = await self._sllm.create(
                response_model=DiagnosticReport,
                messages=messages,
                max_retries=2,
            )
            logger.info("✓ AI Diagnostic complete for node %s", node_id)
            return report
        except Exception as ex:
            logger.error("Failed to call LLM for diagnostic on node %s: %s", node_id, ex)
            return DiagnosticReport(
                headline="Diagnostic IA temporairement indisponible",
                explanation=f"Une erreur est survenue lors de l'appel au service de diagnostic : {ex}",
                suggested_action="Veuillez inspecter manuellement les services systemd et conteneurs Docker via l'interface du serveur.",
            )
