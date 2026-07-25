# Plan d'intégration des alertes Vigile

> **Document d'architecture** — Adaptation des alertes Netdata au système Vigile
> Date : 2026-07-13

---

## 1. Architecture du monitoring Vigile

Avant d'adapter les alertes, rappel des contraintes d'architecture :

### Flux des métriques

```
Worker (Go, stdlib only)
  └─ collectMetrics() → MetricsSnapshot (toutes les ~60s)
       ├─ CPU % / load avg / cores
       ├─ RAM total/used/%, swap
       ├─ Disque total/used/%, mounts[]
       ├─ Uptime, process count
       ├─ TopProcesses (top 10 CPU)
       └─ collected_at timestamp
  └─ WebSocket STATUS_REPORT → Master
       └─ Plugin metrics_plugin.py
            ├─ normalize → MetricsSnapshot (Pydantic)
            └─ persist → table metrics_snapshots
                 └─ Règles d'automation (trigger metric_threshold)
```

### Ce que Vigile NE collecte PAS (encore)

- Métriques réseau par interface (paquets, erreurs FIFO, drops)
- Métriques TCP/UDP (conntrack, SYN queue, orphans, memory)
- Métriques processus individuels (FD, mémoire détaillée)
- Erreurs matérielles (ECC, RAID mdstat)
- Métriques cgroup / conteneurs
- Entropie, NTP, OOM kills

### Canal de notification

- **Automation Rules** : système existant avec triggers `metric_threshold` et `node_state`
- **Webhooks** : `call_webhook` action (Discord, Slack, HTTP)
- **Actions** : `send_intent`, `log_message`
- **Cooldown** : anti-spam par règle (défaut 300s)

---

## 2. Cartographie : Alertes Netdata → Capacités Vigile

Légende :
- ✅ **Déjà possible** (métrique collectée + trigger automation disponible)
- 🟡 **Possible avec adaptation mineure** (métrique existante mais pas de trigger automation formalisé)
- 🔶 **Nécessite collecte Worker** (métrique non collectée par le Worker Go)
- 🔴 *(non utilisé — toutes les métriques sont collectables par le Worker)*
- ➕ **Nouvelle alerte Vigile** (spécifique à l'architecture Vigile)

### 2.1 Disque

| Alerte | Faisabilité | Notes |
|---|---|---|
| `disk_space_usage` | ✅ | `disk_percent` déjà collecté — trigger `metric_threshold` existant |
| `10min_disk_backlog` | 🔶 | `disk_used_rate`/`io_stats` pas encore collecté par le Worker |
| `10min_disk_utilization` | 🔶 | Idem — nécessite lecture de `/proc/diskstats` |
| `disk_inode_usage` | 🔶 | Lecture `/proc` des inodes nécessaire |
| `out_of_disk_space_time` | 🟡 | Calculable depuis `disk_total_bytes` + `disk_used_bytes` + historique |
| `disk_fill_rate` | 🟡 | Dérivé à partir de l'historique des snapshots (taux de remplissage) |
| `disk_inode_rate` | 🔶 | Nécessite collecte des inodes |

### 2.2 RAID

| Alerte | Faisabilité | Notes |
|---|---|---|
| `mdstat_disks` | 🔶 | Lecture `/proc/mdstat` nécessaire dans le Worker |
| `mdstat_mismatch_cnt` | 🔶 | Idem |

### 2.3 CPU / Load

| Alerte | Faisabilité | Notes |
|---|---|---|
| `load_average_1/5/15` | ✅ | `cpu_load_1m/5m/15m` déjà collectés |
| `10min_cpu_usage` | ✅ | `cpu_percent` déjà collecté |
| `10min_cpu_iowait` | 🔶 | `/proc/stat` parse déjà idle/iowait mais non exposé |
| `20min_steal_cpu` | 🔶 | Champs `/proc/stat` `steal` non extraits |
| `load_cpu_number` | 🟡 | `cpu_load_1m` / `cpu_cores` déjà disponibles — rapport calculable |
| `cgroup_10min_cpu_usage` | 🔶 | `/sys/fs/cgroup/cpu.stat` + `cpu.max` — usage CPU / quota cgroup |

### 2.4 Mémoire

| Alerte | Faisabilité | Notes |
|---|---|---|
| `ram_available` | ✅ | `mem_used_bytes` → mémoire libre = total - used |
| `ram_in_use` | ✅ | `mem_percent` déjà collecté |
| `used_swap` | ✅ | `swap_used_bytes` déjà collecté |
| `oom_kill` | 🔶 | Lecture `dmesg` ou `/proc/kmsg` — nécessite logique Worker |
| `ecc_memory_*` | 🔶 | `/sys/devices/system/edac/mc/mc*/ce_count` et `ue_count` — compteurs d'erreurs ECC, lecture fichier standard |
| `1hour_memory_hw_corrupted` | 🔶 | `/sys/devices/system/edac/mc/mc*/sd_ce_count` — compteur de pages corrompues |
| `cgroup_ram_in_use` | 🔶 | `/sys/fs/cgroup/memory.current` + `memory.max` |

### 2.5 Réseau

| Alerte | Faisabilité | Notes |
|---|---|---|
| `toutes alertes réseau` | 🔶 | Aucune métrique réseau collectée par le Worker actuellement (Phase 2) |
| `netfilter_conntrack_full` | 🔶 | `/proc/net/stat/nf_conntrack` — compteurs d'utilisation + `/proc/sys/net/netfilter/nf_conntrack_max` |
| `tcp_connections` | 🔶 | `/proc/net/tcp` |

### 2.6 Processus / Système

| Alerte | Faisabilité | Notes |
|---|---|---|
| `active_processes` | ✅ | `processes` déjà collecté |
| `system_file_descriptors_utilization` | 🔶 | `/proc/sys/fs/file-nr` |
| `lowest_entropy` | 🔶 | `/proc/sys/kernel/random/entropy_avail` |
| `system_clock_sync_state` | 🔶 | `syscall.Adjtimex()` dans Go stdlib — vérifie le flag `STA_UNSYNC` |
| `system_reboot_detection` | ✅ | `uptime_seconds` — une baisse détecte un reboot |
| `apps_group_fds_utilization` | 🔶 | `/proc/*/fd` |
| `semaphore_*` | 🔶 | `/proc/sysvipc/sem` |

---

## 3. Nouvelles alertes spécifiques Vigile

Ces alertes n'existent pas dans Netdata car elles sont propres à l'architecture Vigile (fleet management, WebSocket, intents, audit).

### 3.1 Connectivité Flotte (infrastructure Vigile)

| Alerte | Déclencheur | Gravité | Canal |
|---|---|---|---|
| `node_state_lost` | Nœud en état `LOST` (heartbeat manquant) | **Haute** | sysadmin + webhook |
| `node_state_stale` | Nœud en état `STALE` (perdu >24h) | **Haute** | sysadmin + webhook |
| `node_connection_flap` | Nœud qui alterne CONNECTED/LOST >3x/h | **Moyenne** | sysadmin |
| `node_enrollment_failure` | Échec handshake Ed25519 (>3 tentatives) | **Haute** | sysadmin + webhook |
| `node_revoked_detected` | Nœud révoqué qui tente de se reconnecter | **Critique** | sysadmin + webhook |
| `fleet_coverage_drop` | >30% des nœuds perdus simultanément | **Critique** | sysadmin + webhook |

### 3.2 Exécution des Intents

| Alerte | Déclencheur | Gravité | Canal |
|---|---|---|---|
| `intent_failed_rate` | Taux d'échec d'intents >20% sur 1h | **Haute** | sysadmin |
| `intent_timeout` | Intent non résolue après timeout (60s) | **Moyenne** | sysadmin |
| `intent_high_duration` | Durée d'exécution d'intent >30s (anomalie) | **Basse** | silent |
| `action_proposal_stale` | Proposition d'action non traitée >24h | **Basse** | sysadmin |
| `unsafe_action_attempt` | Action bloquée par la whitelist (tentative) | **Critique** | sysadmin + webhook |

### 3.3 Sécurité & Audit

| Alerte | Déclencheur | Gravité | Canal |
|---|---|---|---|
| `audit_chain_break` | Échec de vérification de la chaîne SHA256 | **Critique** | sysadmin + webhook |
| `token_reuse_detected` | JOIN_TOKEN déjà consommé réutilisé | **Critique** | sysadmin + webhook |
| `public_key_mismatch` | Mismatch de clé publique au reconnect (vol token suspecté) | **Critique** | sysadmin + webhook |
| `join_token_expired_attempt` | Tentative de connexion avec token expiré | **Basse** | silent |
| `worker_token_rotation_failed` | Échec de rotation worker_token | **Moyenne** | sysadmin |

### 3.4 Worker Health

| Alerte | Déclencheur | Gravité | Canal |
|---|---|---|---|
| `worker_version_outdated` | Worker version >2 versions derrière Master | **Basse** | sysadmin |
| `worker_self_update_failed` | Échec de UPDATE_WORKER | **Moyenne** | sysadmin |
| `worker_oom` | OOM kill détecté sur un Worker | **Haute** | sysadmin + webhook |

### 3.5 Master Health

| Alerte | Déclencheur | Gravité | Canal |
|---|---|---|---|
| `master_disk_full` | Espace disque Master <5% (perte de base SQLite) | **Critique** | sysadmin + webhook |
| `master_slow_queries` | Requêtes DB >500ms (goulot d'étranglement) | **Moyenne** | sysadmin |
| `master_ws_backlog` | >100 messages en attente dans le buffer WebSocket | **Haute** | sysadmin |

---

## 4. Parcours d'intégration — Phases

### Phase 1 : Immédiat (métriques existantes)

Alertes activables dès maintenant via le système d'automation existant :

```
┌──────────────────────────────────────────────────────────────┐
│ RÈGLE D'AUTOMATION — SEUIL DISQUE                           │
├──────────────────────────────────────────────────────────────┤
│ trigger_type: metric_threshold                               │
│ trigger_config: { metric: "disk_percent", operator: "gt",    │
│                   threshold: 90 }                            │
│ conditions: [ { type: "always" } ]                           │
│ actions: [ { type: "log_message",                            │
│              message: "Nœud {node_id}: disque >90%" },       │
│            { type: "call_webhook",                           │
│              url: "https://discord.com/...",                  │
│              body: '{"node":"{node_id}","alert":"disk_full"}'│
│            } ]                                               │
│ cooldown_seconds: 3600                                       │
└──────────────────────────────────────────────────────────────┘
```

**Alertes activables en Phase 1 :**

| Nom | Métrique | Seuil Warning | Seuil Critique | Cooldown |
|---|---|---|---|---|
| `disk_usage_high` | `disk_percent` | >85% | >95% | 1h |
| `disk_usage_critical` | `disk_percent` | — | >97% | 30min |
| `memory_usage_high` | `mem_percent` | >85% | >95% | 1h |
| `memory_swap_active` | `swap_used_bytes` | >0 (swap utilisé) | >50% du swap | 4h |
| `cpu_high_load` | `cpu_load_5m` / `cpu_cores` | >2.0× cores | >4.0× cores | 10min |
| `cpu_high_percent` | `cpu_percent` | >80% | >95% | 10min |
| `node_uptime_drop` | `uptime_seconds` | Baisse entre 2 snapshots (reboot) | — | immédiat |
| `process_count_high` | `processes` | > seuil configurable | — | 30min |

### Phase 2 : Collecte Worker étendue (à développer)

Ajouter dans `worker/stats.go` les métriques manquantes. Ces métriques DOIVENT rester en lecture seule depuis `/proc` (zero-dependency).

**Extensions proposées :**

#### a) Métriques disque avancées

```go
// Dans worker/stats.go — nouvelles fonctions
type DiskExtendedStats struct {
    IOUtilPercent float64 // taux d'utilisation I/O
    AvgQueueLen   float64 // longueur moyenne de file d'attente
    AvgWaitMs     float64 // temps d'attente moyen (ms)
    ReadsPerSec   float64 // lectures/s
    WritesPerSec  float64 // écritures/s
    InodePercent  float64 // utilisation inodes (%)
}
```

Lecture : `/proc/diskstats` pour I/O, `statfs()` pour inodes.

#### b) Métriques réseau basiques

```go
type NetStats struct {
    BytesRecv     uint64
    BytesSent     uint64
    PacketsRecv   uint64
    PacketsSent   uint64
    ErrsIn        uint64
    ErrsOut       uint64
    DropIn        uint64
    DropOut       uint64
}
```

Lecture : `/proc/net/dev`.

#### c) Métriques TCP

```go
type TCPStats struct {
    ActiveOpens   uint64
    PassiveOpens  uint64
    CurrEstab     uint64
    InSegs        uint64
    OutSegs       uint64
    RetransSegs   uint64
    RetransPct    float64
}
```

Lecture : `/proc/net/snmp`.

#### d) Top processus par mémoire

Complément au `top_processes` actuel (qui trie par CPU). Ajouter un tri par RSS :

```go
type TopProcessesByMem struct {
    TopByCPU []ProcessInfo // existant
    TopByMem []ProcessInfo // nouveau — tri par MemRSSKB
    TotalRSS uint64        // somme RSS de tous les processus
}
```

### Phase 3 : Alertes Vigile-natives (logique Master)

Ces alertes sont implémentées dans le Master Python, pas dans le Worker. Elles utilisent le hook system existant ou un nouveau `AlertEngine`.

#### 3a : Connectivité Flotte

```python
# master/core/alert_engine.py (nouveau module)
class FleetAlerts:
    async def check_node_state(self, node_id: str, state: NodeState):
        """Vérifie l'état des nœuds et déclenche des alertes."""
        if state == NodeState.LOST:
            await self.trigger("node_state_lost",
                node_id=node_id,
                severity="high",
                message=f"Nœud {node_id} perdu — heartbeat manquant"
            )

    async def check_connection_flap(self, node_id: str):
        """Détecte les fluctuations de connexion."""
        events = await self.db.execute(
            "SELECT COUNT(*) FROM audit_log "
            "WHERE node_id = ? AND action = 'NODE_RECONNECTED' "
            "AND created_at > ?",
            (node_id, time.time() - 3600)
        )
        if events >= 3:
            await self.trigger("node_connection_flap",
                node_id=node_id,
                severity="medium",
                message=f"Nœud {node_id} : {events} reconnexions en 1h"
            )
```

#### 3b : Échecs d'Intents

```python
class IntentAlerts:
    async def check_intent_failures(self):
        """Vérifie le taux d'échec des intents sur la dernière heure."""
        async with self.db.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as failed
            FROM action_proposals
            WHERE updated_at > ?
              AND status IN ('EXECUTED', 'FAILED')
        """, (time.time() - 3600,)) as cursor:
            row = await cursor.fetchone()
            if row and row["total"] > 0:
                rate = row["failed"] / row["total"]
                if rate > 0.20:
                    await self.trigger("intent_failed_rate",
                        severity="high",
                        extra={"failure_rate": rate,
                               "total": row["total"],
                               "failed": row["failed"]}
                    )
```

#### 3c : Audit Trail

```python
class AuditAlerts:
    async def verify_chain_integrity(self):
        """Vérifie l'intégrité de la chaîne d'audit périodiquement."""
        from master.core.audit import verify_chain
        valid = await verify_chain(self.db)
        if not valid:
            await self.trigger("audit_chain_break",
                severity="critical",
                message="Chaîne d'audit SHA256 corrompue !"
            )
```

---

## 5. Nouveaux triggers d'automation à ajouter

Le système d'automation actuel supporte `metric_threshold` et `node_state`. Pour les alertes Vigile-natives, il faut ajouter :

### 5.1 Trigger `node_intent_failure`

```python
# master/api/schemas/automations.py — à ajouter
class IntentFailureTrigger(BaseModel):
    """Déclenché quand un intent échoue sur un nœud."""
    action: str | None = None  # Filtrer par action spécifique (ex: "RESTART_SERVICE")
    min_failures: int = 1       # Nombre d'échecs consécutifs
    window_seconds: int = 300   # Fenêtre de détection
```

### 5.2 Trigger `node_health`

```python
class NodeHealthTrigger(BaseModel):
    """Déclenché sur un événement de santé nœud."""
    event: Literal["enrolled", "lost", "stale", "reconnected", "revoked"]
```

### 5.3 Trigger `audit_alert`

```python
class AuditAlertTrigger(BaseModel):
    """Déclenché sur un événement d'audit spécifique."""
    action: str  # ex: "TOKEN_THEFT_DETECTED"
```

---

## 6. Métriques Prometheus — Export

Le endpoint `/metrics` expose déjà des métriques Prometheus. Ajouter les alertes Vigile-natives comme métriques :

```
# HELP vigile_nodes_lost Number of nodes in LOST state
# TYPE vigile_nodes_lost gauge
vigile_nodes_lost{state="lost"} 0

# HELP vigile_intents_failed_total Total failed intents
# TYPE vigile_intents_failed_total counter
vigile_intents_failed_total{node="abc123",action="RESTART_SERVICE"} 2

# HELP vigile_audit_chain_valid Audit chain integrity (1=valid, 0=broken)
# TYPE vigile_audit_chain_valid gauge
vigile_audit_chain_valid 1
```

---

## 7. Résumé — Arbre de décision pour chaque alerte

```
Alerte dispo dans Netdata ?
├─ Oui → La métrique existe dans MetricsSnapshot ?
│   ├─ Oui ✅ → Activable via automation (Phase 1)
│   ├─ Non → Peut-on l'ajouter au Worker Go ?
│   │   ├─ Oui (lecture /proc) 🔶 → Phase 2
│   │   └─ Non → Peut-on l'ajouter au Worker Go ?
│   └─ Non → Alerte calculable depuis historique ? 🟡 → Phase 1.5
│
└─ Non → Alerte spécifique Vigile ?
    ├─ Oui ➕ → Nouveau module AlertEngine (Phase 3)
    └─ Non → Ignorer
```

---

## 8. Priorisation

| Priorité | Phase | Alertes | Effort |
|---|---|---|---|
| **P0** | Phase 1 | disk_usage, memory_usage, cpu_load, reboot_detection | Aucun (configuration) |
| **P0** | Phase 1 | node_state_lost, node_state_stale | Faible (trigger `node_state` existe) |
| **P0** | Phase 3 | audit_chain_break, token_reuse_detected | Moyen (module AlertEngine) |
| **P1** | Phase 2 | disk_inode, disk_io, network_basic | Moyen (Worker/Go) |
| **P1** | Phase 3 | intent_failed_rate, fleet_coverage_drop | Moyen |
| **P2** | Phase 3 | connection_flap, enrollment_failure | Faible |
| **P3** | Phase 2 | TCP stats, entropy, file_descriptors | Élevé (Worker/Go) |
| **P3** | Phase 2 | ECC memory, netfilter conntrack, cgroup | Moyen (Worker/Go) |

---

## 9. Schéma d'architecture cible

```text
┌─────────────────────────────────────────────────────────────┐
│                        WORKER (Go)                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ collectMetrics()                                     │   │
│  │  ├─ CPU / Load / Cores          ✅ existant          │   │
│  │  ├─ RAM / Swap                 ✅ existant           │   │
│  │  ├─ Disk / Mounts              ✅ existant           │   │
│  │  ├─ Uptime / Processes         ✅ existant           │   │
│  │  ├─ TopProcesses               ✅ existant           │   │
│  │  ├─ Disk I/O / Inodes          🔶 Phase 2           │   │
│  │  ├─ ECC memory (/sys/edac/mc)  🔶 Phase 2           │   │
│  │  ├─ Net stats (/proc/net/dev)  🔶 Phase 2           │   │
│  │  ├─ TCP basics (/proc/net/snmp)🔶 Phase 2           │   │
│  │  └─ Netfilter conntrack        🔶 Phase 2           │   │
│  └──────────────┬──────────────────────────────────────┘   │
│                 │ STATUS_REPORT (WebSocket)                │
└─────────────────┼───────────────────────────────────────────┘
                  │
┌─────────────────┼───────────────────────────────────────────┐
│          MASTER (FastAPI/Python)                            │
│  ┌──────────────┴──────────────────────────────────────┐   │
│  │ metrics_plugin.py                                    │   │
│  │  ├─ normalize (MetricsSnapshot Pydantic)             │   │
│  │  └─ persist (metrics_snapshots table)                │   │
│  └──────────────┬──────────────────────────────────────┘   │
│                 │                                          │
│  ┌──────────────┴──────────────────────────────────────┐   │
│  │ alert_engine.py (Phase 3)                           │   │
│  │  ├─ MetricThresholdEvaluator (existant, amélioré)   │   │
│  │  ├─ NodeStateWatcher          (Phase 1)             │   │
│  │  ├─ IntentFailureAnalyzer     (Phase 3)             │   │
│  │  ├─ FleetHealthMonitor        (Phase 3)             │   │
│  │  ├─ AuditIntegrityVerifier    (Phase 3)             │   │
│  │  └─ TokenSecurityMonitor      (Phase 3)             │   │
│  └──────────────┬──────────────────────────────────────┘   │
│                 │                                          │
│  ┌──────────────┴──────────────────────────────────────┐   │
│  │ Automation Rules                                     │   │
│  │  ├─ metric_threshold (existant)                      │   │
│  │  ├─ node_state (existant)                            │   │
│  │  ├─ node_intent_failure (➕ Phase 3)                 │   │
│  │  ├─ node_health (➕ Phase 3)                         │   │
│  │  └─ audit_alert (➕ Phase 3)                         │   │
│  └──────────────┬──────────────────────────────────────┘   │
│                 │                                          │
│  ┌──────────────┴──────────────────────────────────────┐   │
│  │ Canaux de notification                              │   │
│  │  ├─ Webhook Discord/Slack/HTTP (existant)            │   │
│  │  ├─ Log (existant)                                   │   │
│  │  ├─ Email (➕ à implémenter)                         │   │
│  │  └─ Notification push frontend (➕)                  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 10. Prochaines actions

1. **Créer les règles d'automation P0** dans la base ou via l'API
2. **Implémenter `alert_engine.py`** (module Master pour alertes Vigile-natives)
3. **Étendre `MetricsSnapshot`** avec les champs réseau et disque avancés
4. **Ajouter les nouveaux triggers** dans `schemas/automations.py`
5. **Mettre à jour le Worker Go** pour collecter les nouvelles métriques
6. **Ajouter les notifications email/push** comme canaux d'action
