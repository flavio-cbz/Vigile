from __future__ import annotations

"""
Vigile — Alert Engine

Évalue en continu des seuils prédéfinis sur les métriques Worker et les
événements de la flotte, et persiste les alertes dans la table `alerts`.

Cycle de vie d'une alerte :
  - firing   → le seuil est dépassé
  - resolved → la métrique est repassée sous le seuil de récupération

Alertes intégrées :
  - Seuils métriques (disque, mémoire, CPU, swap, reboot)
  - État des nœuds (LOST, STALE, flapping)
  - Taux d'échec des intents
  - Sécurité (token reuse, audit chain)
"""

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from typing import Any

from master.core.lock import LoopBoundLock
from master.db.database import transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Définition des seuils intégrés
# ---------------------------------------------------------------------------

class AlertThreshold:
    """Définition d'un seuil d'alerte avec sa récupération."""

    def __init__(
        self,
        name: str,
        metric: str,
        warning_at: float | None = None,
        critical_at: float | None = None,
        resolve_at: float | None = None,
        operator: str = "gt",
        severity: str = "warning",
        message_template: str = "{metric} = {value:.1f} (seuil {operator} {threshold})",
    ) -> None:
        self.name = name
        self.metric = metric
        self.warning_at = warning_at
        self.critical_at = critical_at
        self.resolve_at = resolve_at
        self.operator = operator
        self.severity = severity
        self.message_template = message_template

    def check(self, value: float) -> tuple[str | None, float | None]:
        """
        Évalue la valeur.
        Retourne (severity, threshold) si le seuil est dépassé, (None, None) sinon.
        """
        if value is None:
            return None, None

        if self.critical_at is not None and self._cmp(value, self.critical_at):
            return "critical", self.critical_at
        if self.warning_at is not None and self._cmp(value, self.warning_at):
            return "warning", self.warning_at
        return None, None

    def is_resolved(self, value: float) -> bool:
        """Retourne True si la valeur est repassée sous le seuil de résolution."""
        if value is None or self.resolve_at is None:
            return False
        # On considère résolu si l'opérateur inverse n'est plus vrai
        if self.operator == "gt":
            return value <= self.resolve_at
        elif self.operator == "lt":
            return value >= self.resolve_at
        return False

    def _cmp(self, value: float, threshold: float) -> bool:
        if self.operator == "gt":
            return value > threshold
        elif self.operator == "lt":
            return value < threshold
        elif self.operator == "gte":
            return value >= threshold
        elif self.operator == "lte":
            return value <= threshold
        return False


# Seuils intégrés — appliqués à chaque STATUS_REPORT
BUILTIN_THRESHOLDS: list[AlertThreshold] = [
    # Disque
    AlertThreshold("disk_usage_high", "disk_percent",
                    warning_at=85.0, critical_at=95.0, resolve_at=80.0,
                    message_template="Espace disque {value:.1f}% utilisé (seuil > {threshold}%)"),
    # Mémoire
    AlertThreshold("memory_usage_high", "mem_percent",
                    warning_at=85.0, critical_at=95.0, resolve_at=80.0,
                    message_template="RAM {value:.1f}% utilisée (seuil > {threshold}%)"),
    # Swap actif
    AlertThreshold("memory_swap_active", "swap_used_bytes",
                    warning_at=1.0, critical_at=None, resolve_at=0.0,
                    message_template="Swap utilisé ({value} octets)"),
    # CPU pourcentage
    AlertThreshold("cpu_high_percent", "cpu_percent",
                    warning_at=80.0, critical_at=95.0, resolve_at=60.0,
                    message_template="CPU {value:.1f}% (seuil > {threshold}%)"),
    # Charge CPU normalisée (load_5m / nb_coeurs) — alias de cpu_load_per_core_high
    AlertThreshold("cpu_high_load", "cpu_load_per_core",
                    warning_at=2.0, critical_at=4.0, resolve_at=1.5,
                    message_template="Charge CPU {value:.1f} par coeur (seuil > {threshold})"),
    # Température CPU / système
    AlertThreshold("temperature_high", "temp_celsius",
                    warning_at=75.0, critical_at=85.0, resolve_at=70.0,
                    message_template="Température {value:.1f}°C (seuil > {threshold}°C)"),
    # PSI CPU (pression d'ordonnancement)
    AlertThreshold("psi_cpu_pressure", "psi_cpu_avg10",
                    warning_at=50.0, critical_at=80.0, resolve_at=30.0,
                    message_template="Pression CPU PSI avg10={value:.1f} (seuil > {threshold})"),
    # PSI I/O
    AlertThreshold("psi_io_pressure", "psi_io_avg10",
                    warning_at=50.0, critical_at=80.0, resolve_at=30.0,
                    message_template="Pression I/O PSI avg10={value:.1f} (seuil > {threshold})"),
    # PSI Mémoire
    AlertThreshold("psi_mem_pressure", "psi_mem_avg10",
                    warning_at=50.0, critical_at=80.0, resolve_at=30.0,
                    message_template="Pression mémoire PSI avg10={value:.1f} (seuil > {threshold})"),
    # Entropie faible
    AlertThreshold("entropy_low", "entropy_avail",
                    warning_at=None, critical_at=100.0, resolve_at=200.0,
                    operator="lt",
                    message_template="Entropie disponible: {value} bits (seuil < {threshold})"),
    # --- Synthétiques (calculés par _compute_synthetic_metrics) ---

    # Charge CPU par coeur
    AlertThreshold("cpu_load_per_core_high", "cpu_load_per_core",
                    warning_at=2.0, critical_at=4.0, resolve_at=1.5,
                    message_template="Charge CPU {value:.1f} par coeur (seuil > {threshold})"),
    # Nombre de processus
    AlertThreshold("process_count_high", "processes",
                    warning_at=500, critical_at=1000, resolve_at=400,
                    message_template="{value:.0f} processus (seuil > {threshold})"),
    # Pourcentage Swap
    AlertThreshold("swap_usage_percent_high", "swap_percent",
                    warning_at=50.0, critical_at=80.0, resolve_at=40.0,
                    message_template="Swap {value:.1f}% utilisé (seuil > {threshold}%)"),
    # Descripteurs de fichiers
    AlertThreshold("file_handle_usage_high", "file_handle_percent",
                    warning_at=80.0, critical_at=95.0, resolve_at=70.0,
                    message_template="Descripteurs fichiers {value:.1f}% (seuil > {threshold}%)"),
    # Taux de pertes réseau (deltas entre snapshots)
    AlertThreshold("network_drops_high", "net_drops_rate",
                    warning_at=5.0, critical_at=20.0, resolve_at=3.0,
                    message_template="Pertes réseau {value:.1f}/s (seuil > {threshold}/s)"),
    # Débit I/O disque (deltas entre snapshots)
    AlertThreshold("disk_io_high", "disk_io_mbps",
                    warning_at=50.0, critical_at=200.0, resolve_at=30.0,
                    message_template="I/O disque {value:.1f} Mo/s (seuil > {threshold} Mo/s)"),
]


# ---------------------------------------------------------------------------
# AlertEngine
# ---------------------------------------------------------------------------


class AlertEngine:
    """
    Moteur d'alertes intégré.

    S'abonne à :
      - on_status_report (plugin hook) → évalue les seuils métriques
      - state_change_callback (node_manager) → détecte LOST/STALE/CONNECTED

    Fonctionnement :
      - Maintient un état en mémoire {node_id: {alert_name: AlertState}}
      - Persiste dans la table `alerts` les transitions firing / resolved
      - Nettoie périodiquement les resolved_at > 7 jours
    """

    def __init__(self) -> None:
        self._db: Any = None
        # Callback when an alert fires — set by InvestigationManager at startup
        self.on_alert_fired_callback: Any = None
        # {node_id: {alert_name: {"severity": ..., "status": ..., "created_at": ...}}}
        self._active_alerts: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        # Dernière métrique connue par nœud (pour les dérivées)
        self._last_snapshot: dict[str, dict[str, Any]] = {}
        # Compteur d'échecs d'intents par nœud (rolling window)
        self._intent_failures: dict[str, list[tuple[float, bool]]] = defaultdict(list)
        # Compteur de reconnexions pour le flapping
        self._reconnect_counts: dict[str, list[float]] = defaultdict(list)
        # Verrou pour les accès concurrents
        self._lock = LoopBoundLock()
        # Background task supervision
        self._background_tasks: set[asyncio.Task] = set()
        # Rate limiting for alert firing (sliding window per node_id:alert_name)
        self._alert_rate_limiter: dict[str, list[float]] = defaultdict(list)
        self._alert_rate_limit_window: float = 60.0
        self._alert_rate_limit_max: int = 10

    async def initialize(self, db: Any) -> None:
        """Charge les alertes non résolues depuis la base au démarrage."""
        self._db = db
        try:
            async with db.execute(
                "SELECT id, node_id, alert_name, severity, details_json, created_at "
                "FROM alerts WHERE status = 'firing'"
            ) as cursor:
                rows = await cursor.fetchall()
            count = 0
            for row in rows:
                try:
                    details = json.loads(row["details_json"]) if row["details_json"] else {}
                    self._active_alerts[row["node_id"]][row["alert_name"]] = {
                        "id": row["id"],
                        "severity": row["severity"],
                        "status": "firing",
                        "details": details,
                        "created_at": row["created_at"],
                    }
                    count += 1
                except Exception:
                    continue
            logger.info("AlertEngine initialized. %d active alert(s) restored.", count)
        except Exception as exc:
            logger.error("AlertEngine.initialize: %s", exc)

    # -------------------------------------------------------------------
    # Évaluation des métriques — hook on_status_report
    # -------------------------------------------------------------------

    async def evaluate_metrics(
        self,
        node_id: str,
        snapshot: Any,
        db: Any,
    ) -> None:
        """
        Évalue tous les seuils intégrés sur un snapshot de métriques.
        Appelé via le hook plugin_manager 'on_status_report'.
        snapshot est un dict (issue de MetricsSnapshot.model_dump()).

        Ordre : reboot → thresholds → stockage snapshot.
        _detect_reboot doit lire l'ANCIEN snapshot avant que _evaluate_builtin_thresholds
        ne mette à jour _last_snapshot avec le nouveau.
        """
        if not isinstance(snapshot, dict):
            return

        async with self._lock:
            await self._detect_reboot(node_id, snapshot, db)
            await self._evaluate_builtin_thresholds(node_id, snapshot, db)

    async def _evaluate_builtin_thresholds(
        self, node_id: str, snapshot: dict, db: Any
    ) -> None:
        """Évalue les seuils intégrés pour un snapshot donné."""
        previous = self._last_snapshot.get(node_id, {})
        self._last_snapshot[node_id] = snapshot

        self._compute_synthetic_metrics(snapshot, previous, node_id)

        for threshold in BUILTIN_THRESHOLDS:
            value = snapshot.get(threshold.metric)
            if value is None or not isinstance(value, (int, float)):
                continue

            alert_name = threshold.name
            current = self._active_alerts[node_id].get(alert_name)

            # Vérifier si le seuil est dépassé
            severity, thresh = threshold.check(value)
            if severity is not None and thresh is not None:
                # Vérifier si l'alerte existe déjà avec une sévérité >=
                if current and current["status"] == "firing":
                    if self._severity_rank(current["severity"]) >= self._severity_rank(severity):
                        continue  # déjà alerté à ce niveau ou plus haut
                    # Sinon, on monte en gravité (warning → critical)
                    await self._resolve_alert(node_id, alert_name, db)
                # Créer / mettre à jour l'alerte
                msg = threshold.message_template.format(
                    metric=threshold.metric,
                    value=value,
                    threshold=thresh,
                    operator=threshold.operator,
                )
                await self._fire_alert(
                    node_id, alert_name, severity, msg,
                    metric_value=float(value),
                    threshold=float(thresh),
                    db=db,
                )
            elif current and current["status"] == "firing":
                # Vérifier si l'alerte est résolue
                if threshold.is_resolved(value):
                    await self._resolve_alert(node_id, alert_name, db)

    async def _detect_reboot(self, node_id: str, snapshot: dict, db: Any) -> None:
        """Détecte un redémarrage du nœud (baisse de uptime_seconds)."""
        uptime = snapshot.get("uptime_seconds")
        if uptime is None or not isinstance(uptime, (int, float)):
            return

        previous = self._last_snapshot.get(node_id, {})
        prev_uptime = previous.get("uptime_seconds") if isinstance(previous, dict) else None

        if prev_uptime is not None and uptime < prev_uptime - 5.0:
            # Uptime a baissé → reboot
            if "node_reboot_detected" not in self._active_alerts[node_id]:
                await self._fire_alert(
                    node_id, "node_reboot_detected", "warning",
                    f"Nœud redémarré (uptime: {prev_uptime:.0f}s → {uptime:.0f}s)",
                    metric_value=uptime,
                    db=db,
                )

    # -------------------------------------------------------------------
    # -------------------------------------------------------------------
    # Synthèse de métriques dérivées (swap%, file handles%, load/core, rates)
    # -------------------------------------------------------------------

    @staticmethod
    def _compute_synthetic_metrics(
        snapshot: dict,
        previous: dict,
        node_id: str,
    ) -> None:
        """
        Calcule et injecte les métriques synthétiques dans le snapshot :
          - cpu_load_per_core  : cpu_load_5m / cpu_cores
          - swap_percent       : swap_used_bytes / swap_total_bytes * 100
          - file_handle_percent: file_handles_used / file_handles_max * 100
          - net_drops_rate     : delta(net_drops_in + net_drops_out) / dt
          - disk_io_mbps       : delta(disk_read_bytes + disk_write_bytes) / dt / 1M
        """
        # -- CPU Load par coeur --
        load_5m = snapshot.get("cpu_load_5m")
        cores = snapshot.get("cpu_cores")
        if load_5m is not None and cores and cores > 0:
            snapshot["cpu_load_per_core"] = load_5m / cores

        # -- Pourcentage Swap --
        swap_used = snapshot.get("swap_used_bytes")
        swap_total = snapshot.get("swap_total_bytes")
        if swap_used is not None and swap_total and swap_total > 0:
            snapshot["swap_percent"] = swap_used / swap_total * 100.0

        # -- Pourcentage descripteurs fichiers --
        fh_used = snapshot.get("file_handles_used")
        fh_max = snapshot.get("file_handles_max")
        if fh_used is not None and fh_max and fh_max > 0:
            snapshot["file_handle_percent"] = fh_used / fh_max * 100.0

        # -- Taux de pertes réseau (delta) --
        if previous:
            dt = max(1.0, snapshot.get("collected_at", 0.0) - previous.get("collected_at", 0.0))
            cur_drops = snapshot.get("net_drops_in", 0) + snapshot.get("net_drops_out", 0)
            prev_drops = previous.get("net_drops_in", 0) + previous.get("net_drops_out", 0)
            drop_delta = cur_drops - prev_drops
            if drop_delta > 0:
                snapshot["net_drops_rate"] = drop_delta / dt

            # -- Débit I/O disque (delta, en Mo/s) --
            cur_io = snapshot.get("disk_read_bytes", 0) + snapshot.get("disk_write_bytes", 0)
            prev_io = previous.get("disk_read_bytes", 0) + previous.get("disk_write_bytes", 0)
            io_delta = cur_io - prev_io
            if io_delta > 0:
                snapshot["disk_io_mbps"] = io_delta / dt / (1024 * 1024)

    # Évaluation des états — state_change_callback
    # -------------------------------------------------------------------

    async def evaluate_node_state(
        self,
        node_id: str,
        new_state: Any,
        db: Any,
    ) -> None:
        """
        Évalue les alertes liées à l'état du nœud.
        Appelé via node_manager.register_state_change_callback().
        """
        state_value = new_state.value if hasattr(new_state, "value") else str(new_state)

        async with self._lock:
            if state_value == "LOST":
                if "node_state_lost" not in self._active_alerts[node_id]:
                    await self._fire_alert(
                        node_id, "node_state_lost", "critical",
                        f"Nœud {node_id} perdu — heartbeat manquant",
                        db=db,
                    )
            elif state_value == "STALE":
                if "node_state_stale" not in self._active_alerts[node_id]:
                    await self._fire_alert(
                        node_id, "node_state_stale", "critical",
                        f"Nœud {node_id} perdu depuis >24h (STALE)",
                        db=db,
                    )
            elif state_value == "CONNECTED":
                # Résoudre les alertes de perte de connexion
                for alert_name in ("node_state_lost", "node_state_stale"):
                    if alert_name in self._active_alerts[node_id]:
                        await self._resolve_alert(node_id, alert_name, db)

                # Détection de flapping
                now = time.time()
                self._reconnect_counts[node_id].append(now)
                # Garder les 60 dernières minutes
                cutoff = now - 3600
                self._reconnect_counts[node_id] = [
                    t for t in self._reconnect_counts[node_id] if t > cutoff
                ]
                if len(self._reconnect_counts[node_id]) >= 5:
                    if "node_connection_flap" not in self._active_alerts[node_id]:
                        await self._fire_alert(
                            node_id, "node_connection_flap", "warning",
                            f"Nœud {node_id} : {len(self._reconnect_counts[node_id])} "
                            f"reconnexions dans l'heure",
                            db=db,
                        )

    # -------------------------------------------------------------------
    # Suivi des échecs d'intents
    # -------------------------------------------------------------------

    async def track_intent_result(
        self, node_id: str, success: bool, db: Any
    ) -> None:
        """
        Suit le taux d'échec des intents par nœud.
        Appelé depuis worker_handler.py sur réception d'INTENT_RESULT.
        """
        now = time.time()
        cutoff = now - 3600

        async with self._lock:
            self._intent_failures[node_id].append((now, success))
            # Nettoyage de la fenêtre glissante
            self._intent_failures[node_id] = [
                (t, s) for t, s in self._intent_failures[node_id] if t > cutoff
            ]

            total = len(self._intent_failures[node_id])
            if total == 0:
                return
            failed = sum(1 for _, s in self._intent_failures[node_id] if not s)
            rate = failed / total

            if rate > 0.20 and total >= 5:
                if "intent_failed_rate" not in self._active_alerts[node_id]:
                    await self._fire_alert(
                        node_id, "intent_failed_rate", "warning",
                        f"Taux d'échec intents: {rate:.0%} ({failed}/{total}) sur 1h",
                        metric_value=float(rate),
                        threshold=0.2,
                        details={"failed": failed, "total": total, "rate": rate},
                        db=db,
                    )
            else:
                if "intent_failed_rate" in self._active_alerts[node_id]:
                    await self._resolve_alert(node_id, "intent_failed_rate", db)

    # -------------------------------------------------------------------
    # Persistance des alertes
    # -------------------------------------------------------------------

    async def _fire_alert(
        self,
        node_id: str,
        alert_name: str,
        severity: str,
        message: str,
        db: Any = None,
        metric_value: float | None = None,
        threshold: float | None = None,
        details: dict | None = None,
    ) -> str | None:
        """Crée une alerte firing en base et en mémoire."""
        db = db or self._db
        if db is None:
            logger.warning("AlertEngine: no DB — cannot fire alert '%s'", alert_name)
            return None

        # Rate limiting: prevent alert storms
        if self._is_rate_limited(node_id, alert_name):
            logger.debug(
                "AlertEngine: rate-limited alert '%s' for node %s", alert_name, node_id
            )
            return None

        alert_id = str(uuid.uuid4())
        now = time.time()
        details_json = json.dumps(details or {})

        try:
            async with transaction(db) as tx_db:
                await tx_db.execute(
                    """INSERT INTO alerts
                       (id, node_id, alert_name, severity, status, message,
                        metric_value, threshold, details_json,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, 'firing', ?, ?, ?, ?, ?, ?)""",
                    (
                        alert_id, node_id, alert_name, severity, message,
                        metric_value, threshold, details_json,
                        now, now,
                    ),
                )
        except Exception as exc:
            logger.error("AlertEngine: failed to persist alert '%s': %s", alert_name, exc)
            return None

        self._active_alerts[node_id][alert_name] = {
            "id": alert_id,
            "severity": severity,
            "status": "firing",
            "details": details or {},
            "created_at": now,
        }
        logger.info(
            "🔔 ALERT %s [%s] %s — %s",
            alert_name.upper(), severity.upper(), node_id[:12], message,
        )

        # Notify investigation manager (supervised task)
        if self.on_alert_fired_callback is not None:
            self._spawn_task(
                self.on_alert_fired_callback(
                    node_id=node_id,
                    alert_name=alert_name,
                    severity=severity,
                    message=message,
                    alert_id=alert_id,
                    db=db,
                    details=details,
                ),
                name=f"investigation:{alert_name}:{alert_id[:12]}",
            )

        return alert_id

    async def _resolve_alert(
        self,
        node_id: str,
        alert_name: str,
        db: Any = None,
    ) -> None:
        """Marque une alerte comme resolved."""
        db = db or self._db
        if db is None:
            return

        current = self._active_alerts[node_id].get(alert_name)
        if not current:
            return

        now = time.time()
        try:
            async with transaction(db) as tx_db:
                await tx_db.execute(
                    "UPDATE alerts SET status = 'resolved', resolved_at = ?, updated_at = ? "
                    "WHERE id = ? AND status = 'firing'",
                    (now, now, current["id"]),
                )
        except Exception as exc:
            logger.error("AlertEngine: failed to resolve alert '%s': %s", alert_name, exc)
            return

        del self._active_alerts[node_id][alert_name]

        duration = now - current.get("created_at", now)
        logger.info(
            "✅ RESOLVED %s [%s] %s — was firing for %.0fs",
            alert_name.upper(), current["severity"].upper(), node_id[:12], duration,
        )

    # -------------------------------------------------------------------
    # Rate limiting
    # -------------------------------------------------------------------

    def _is_rate_limited(self, node_id: str, alert_name: str) -> bool:
        """Check if alert firing is rate-limited for this node+alert combo."""
        key = f"{node_id}:{alert_name}"
        now = time.time()
        timestamps = self._alert_rate_limiter[key]
        self._alert_rate_limiter[key] = [
            t for t in timestamps if now - t < self._alert_rate_limit_window
        ]
        if len(self._alert_rate_limiter[key]) >= self._alert_rate_limit_max:
            return True
        self._alert_rate_limiter[key].append(now)
        return False

    # -------------------------------------------------------------------
    # Task supervision
    # -------------------------------------------------------------------

    def _spawn_task(self, coro: Any, name: str) -> asyncio.Task:
        """Spawn a supervised background task tracked for graceful shutdown."""
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def ensure_tasks_complete(self, timeout: float = 30.0) -> None:
        """Wait for all background tasks to complete (graceful shutdown)."""
        if not self._background_tasks:
            return
        done, pending = await asyncio.wait(
            self._background_tasks, timeout=timeout
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.wait(pending, timeout=5.0)
        self._background_tasks.clear()
        logger.info("AlertEngine: %d background task(s) completed.", len(done))

    # -------------------------------------------------------------------
    # Orphan cleanup
    # -------------------------------------------------------------------

    async def cleanup_orphaned_alerts(self, db: Any = None) -> int:
        """Remove alerts and in-memory state for nodes that no longer exist."""
        db = db or self._db
        if db is None:
            return 0
        try:
            async with transaction(db) as tx_db:
                cursor = await tx_db.execute(
                    "DELETE FROM alerts WHERE node_id NOT IN (SELECT id FROM nodes)"
                )
                deleted = cursor.rowcount or 0
        except Exception as exc:
            logger.error("AlertEngine: orphan cleanup failed: %s", exc)
            return 0

        # Clean in-memory state
        async with self._lock:
            valid_node_ids: set[str] = set()
            try:
                async with db.execute("SELECT id FROM nodes") as cursor:
                    valid_node_ids = {row["id"] for row in await cursor.fetchall()}
            except Exception:
                pass
            orphaned = [
                nid for nid in list(self._active_alerts.keys())
                if nid not in valid_node_ids
            ]
            for nid in orphaned:
                del self._active_alerts[nid]
            # Also clean rate limiter and intent failures
            for nid in orphaned:
                self._alert_rate_limiter.pop(nid, None)
                self._intent_failures.pop(nid, None)
                self._reconnect_counts.pop(nid, None)
                self._last_snapshot.pop(nid, None)

        if deleted:
            logger.info("AlertEngine: purged %d orphaned alert(s).", deleted)
        return deleted

    # -------------------------------------------------------------------
    # Nettoyage périodique
    # -------------------------------------------------------------------

    async def cleanup_old_alerts(self, db: Any = None) -> int:
        """Supprime les alertes résolues depuis plus de 7 jours."""
        db = db or self._db
        if db is None:
            return 0
        cutoff = time.time() - 7 * 86400
        try:
            async with transaction(db) as tx_db:
                cursor = await tx_db.execute(
                    "DELETE FROM alerts WHERE status = 'resolved' AND resolved_at < ?",
                    (cutoff,),
                )
                deleted = cursor.rowcount or 0
            if deleted:
                logger.info("AlertEngine: purged %d old resolved alert(s).", deleted)
            return deleted
        except Exception as exc:
            logger.error("AlertEngine: cleanup failed: %s", exc)
            return 0

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    def get_active_alerts(self, node_id: str | None = None) -> list[dict]:
        """Retourne les alertes actives, éventuellement filtrées par nœud."""
        result = []
        for nid, alerts in self._active_alerts.items():
            if node_id and nid != node_id:
                continue
            for alert_name, state in alerts.items():
                result.append({
                    "node_id": nid,
                    "alert_name": alert_name,
                    "severity": state["severity"],
                    "status": state["status"],
                    "created_at": state.get("created_at"),
                    "details": state.get("details", {}),
                })
        return result

    def get_active_alert_count(self) -> dict[str, int]:
        """Retourne le nombre d'alertes actives par sévérité."""
        counts: dict[str, int] = {"critical": 0, "warning": 0, "info": 0}
        for alerts in self._active_alerts.values():
            for state in alerts.values():
                sev = state.get("severity", "info")
                counts[sev] = counts.get(sev, 0) + 1
        return counts

    @staticmethod
    def _severity_rank(severity: str) -> int:
        return {"info": 0, "warning": 1, "critical": 2}.get(severity, 0)


# Module singleton
alert_engine = AlertEngine()
