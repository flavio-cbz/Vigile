# Vigile — Session Init & Status

*Ce fichier permet à n'importe quel assistant IA ou développeur de comprendre instantanément le contexte du projet, son architecture et son état d'avancement.*

---
<!-- Dernière session : 2026-05-15 — Sprint 2 FINI, déploiement youcloud.ovh validé -->
<!--
Résumé de la dernière session :
- Sprint 2 terminé et déployé sur youcloud.ovh
- 218 tests unitaires verts
- Tests terrain passés : 45 services systemd, 39 containers Docker, logs SSH temps réel
- Bug Docker socket Go fixé (DialContext écrase Dial dans containers.go)
- Worker run natif sur l'hôte via sudo (keypair dans /etc/vigile)
- Prochaine étape : Sprint 3 (couche IA) ou améliorations diverses
-->
---

## 🎯 Vision du Projet
**Vigile** est un Fleet Manager intelligent pour serveurs et homelabs, conçu avec un focus absolu sur la sécurité (Zero-Trust) et l'auditabilité.
- **Zéro dépendance tierce sur le "Core"** : L'intelligence est construite nativement (inspiration de LiteLLM, Pluggy, Instructor).
- **Zéro SSH** : Les connexions sont toujours initiées par les Workers vers le Master via des WebSockets sécurisées (contournement NAT).
- **Human-in-the-Loop** : L'IA propose des actions de remédiation, mais c'est toujours un humain qui approuve l'action avant son exécution par le Worker.
- **Audit Immuable** : Chaque action est hachée cryptographiquement en chaîne (SHA256) dans la base de données.

---

## 🏗️ Architecture

Le système est divisé en deux composants majeurs :

### 1. Master Node (Python / FastAPI)
- **Rôle** : Cerveau central. Gère l'authentification, les WebSockets des Workers, la base de données, l'IA et sert l'API REST.
- **Stack autorisée** : `fastapi`, `uvicorn`, `aiosqlite`, `python-jose`, `passlib`, `httpx`, `pydantic`. Strictement aucune autre librairie tierce pour le backend.
- **Base de données** : SQLite asynchrone (`aiosqlite`) avec mode WAL activé. Aucune utilisation d'ORM complexe, tout est en SQL pur défini dans `master/db/models.py`.

### 2. Worker Node (Go) *(Développement prévu Sprint 2)*
- **Rôle** : Agent exécutable autonome déployé sur les serveurs cibles.
- **Stack autorisée** : Stdlib Go **uniquement**. Zéro dépendance externe.
- **Comportement** : Liste d'actions autorisées (Whitelist) hardcodée. Pas de shell interactif.

---

## 🚀 État d'avancement : SPRINT 2 EN COURS

Sprint 1 terminé — toutes les fondations cryptographiques, de sécurité et l'API de base du Master Node.

**Sprint 2 (Plugins OS) — En développement :**

### ✅ Ce qui est implémenté et validé (218 Tests — terrain validé) :

**Core (57 tests) :**
- `SecurityManager` : JOIN_TOKEN HMAC-SHA256, Ed25519 challenge/response, JWT + RBAC, bcrypt
- `NodeManager` : Machine à états (PENDING→ENROLLING→CONNECTED→LOST→REVOKED→STALE), registre WebSocket, heartbeat monitor
- `PluginManager` : Système de hooks natif (inspiré Pluggy), dispatch synchrone/async
- **Audit Trail** : SHA256 hash chain, détection de falsification
- **API REST** : Auth + Nodes + kickstart.sh
- **WebSocket** : Enrollment Ed25519 + protocole opérationnel

**Logs API (22 tests) :**
- `test_logs_api.py` : Tests unitaires pour `GET /api/nodes/{id}/logs`
  - Couvre : file logs, service logs, défaut syslog, 404, 503, 504, erreur worker, 401, 403
  - Mock `node_manager.send_intent` pour simuler les réponses Worker

**Services & Containers API (36 tests) :**
- `test_services_api.py` : Tests pour `GET /api/nodes/{id}/services`, `GET /services/{name}`,
  `POST /services/{name}/restart`, `GET /containers`, `POST /containers/{id}/restart`
  - Couvre : succès, 404, 503, 504, RBAC admin/operator/viewer, fallback sur erreur Worker

**Systemd & Docker Plugins :**
- `systemd_plugin.py` : Pydantic models `ServiceInfo`, `ServiceStatus`, parse helpers, hooks
- `docker_plugin.py` : Pydantic model `ContainerSummary`, parse helpers, hooks
- Les deux plugins déclarent `get_supported_actions` pour l'introspection

**Plugins (88 tests) :**
- `metrics_plugin.py` : Modèle `MetricsSnapshot` (CPU/RAM/disque/swap/uptime), validation Pydantic
  - 3 hooks : `get_supported_actions`, `normalize_status_report`, `on_status_report`
  - Pipeline STATUS_REPORT complet intégré dans `worker_handler.py`
  - Persistance des snapshots en base (`metrics_snapshots` table)
  - Support formats plat et imbriqué (`{"metrics": {...}}`)
  - Graceful degradation si aucun plugin chargé

**API Stats :**
- Table `metrics_snapshots` avec colonnes CPU/MEM/SWAP/DISK/Uptime
- `_on_status_report` async : insert en DB à chaque STATUS_REPORT
- `GET /api/nodes/{id}/stats` : Operator+, param `limit` (1-100, défaut 10)
- Pydantic response models : `MetricsSnapshotResponse`, `NodeStatsResponse`

**Worker Go (9 fichiers, zéro dépendance) :**
- `wsclient.go` : Client WebSocket RFC 6455 implémenté à la main (stdlib pure)
- `enrollment.go` : Génération Ed25519, handshake challenge/response
- `connection.go` : Reconnexion avec backoff exponentiel, heartbeat 30s, STATUS_REPORT 60s
- `dispatcher.go` : Whitelist d'actions (GET_STATS, READ_LOGS, containers, services)
- `discovery.go` : Fingerprint (hostname, machine-id, arch, OS)
- `stats.go` : Métriques depuis /proc (CPU, RAM, disque, uptime)
- `containers.go` : API Docker via socket Unix (list + restart)
- `services.go` : Gestion systemd (list, status, restart)
- `logs.go` : Lecture logs (journalctl, fichier)

**Docker Compose :**
- `Dockerfile.master` : Python 3.12-slim avec uvicorn
- `worker/Dockerfile` : Multi-stage (golang:1.23 → alpine)
- `docker-compose.yml` : Stack complète avec healthcheck
- `scripts/setup_test.sh` : Automation (build → tokens → workers)

---

## 🛠️ Comment travailler sur ce projet (Commandes utiles)

### 1. Lancer le serveur (Master Node)
L'environnement virtuel se trouve dans `.venv`.
```bash
# Depuis la racine du projet
PYTHONPATH="." uvicorn master.main:app --host 127.0.0.1 --port 8000 --reload

# Sous Windows PowerShell (Python système si .venv cassé) :
# $env:PYTHONPATH="."; uvicorn master.main:app --host 127.0.0.1 --port 8000 --reload
```
- API Docs : `http://127.0.0.1:8000/api/docs`
- Compte Administrateur par défaut : `admin` / `admin`

### 2. Lancer les tests
Les tests ont été catégorisés pour ne pas s'emmêler les pinceaux :
```bash
# Tests Unitaires (160 tests — ne nécessite pas Uvicorn)
# Linux/macOS :
PYTHONPATH="." PYTHONIOENCODING=utf-8 .venv/bin/python tests/unit/test_core.py
PYTHONPATH="." PYTHONIOENCODING=utf-8 .venv/bin/python tests/unit/test_worker_handler.py
PYTHONPATH="." PYTHONIOENCODING=utf-8 .venv/bin/python tests/unit/test_plugins.py

# Windows (cmd) :
# set PYTHONPATH=. && set PYTHONIOENCODING=utf-8 && python tests/unit/test_core.py
# set PYTHONPATH=. && set PYTHONIOENCODING=utf-8 && python tests/unit/test_worker_handler.py
# set PYTHONPATH=. && set PYTHONIOENCODING=utf-8 && python tests/unit/test_plugins.py

# Tests d'Intégration (API REST) - Nécessite que Uvicorn soit lancé sur le port 8000
PYTHONPATH="." .venv/bin/python tests/integration/test_api.py
```

---

## ⏭️ Prochaines Étapes (Sprint 2 & 3)

**Sprint 4 : Frontend React** ← PROCHAINE ÉTAPE

**Sprint 2 : Plugins OS et Worker Go (Terminé ✅)**
- ✅ `metrics_plugin.py` — Métriques CPU/RAM/disque/swap/uptime, validation Pydantic, pipeline STATUS_REPORT
- ✅ API `GET /api/nodes/{id}/stats` — exposition des métriques (persistance DB, limit param, Operator+)
- ✅ Worker Go — Binaire autonome (zéro dépendance), handshake Ed25519, collecte métriques
- ✅ Docker Compose test stack : Master + Workers isolés
- ✅ API `GET /api/nodes/{id}/logs` — logs live des Workers via intent (READ_LOGS / READ_LOGS_SERVICE)
- ✅ Plugin `systemd` + `docker` — déclarent les actions supportées via `get_supported_actions`
- ✅ API systemd : `GET /services`, `GET /services/{name}`, `POST /services/{name}/restart`
- ✅ API Docker : `GET /containers`, `POST /containers/{id}/restart`
- ✅ **218 tests unitaires** (57 core + 88 plugins + 15 WS + 22 logs + 36 services)
- ✅ **Déploiement sur youcloud.ovh, test end-to-end complet**
  - 45 services systemd listés, ssh.service actif/enabled
  - 39 containers Docker listés (via socket Unix fixé)
  - Logs SSH temps réel (journalctl)
  - Métriques CPU/MEM/DISK via STATUS_REPORT 60s
  - Bug `containers.go:DialContext` fixé (écrasait le socket Unix par TCP)

**Sprint 3 : Couche IA et Human-in-the-Loop (Terminé ✅)**
- `LLMClient` natif : complete + stream SSE
- `StructuredLLM` : boucle retry + validation Pydantic
- `ActionProposal` : modèle Pydantic + table DB (PENDING→APPROVED→EXECUTED|FAILED)
- Chat API : POST /api/chat (SSE), POST /proposals/approve, POST /proposals/reject

**Sprint 4 : Frontend React** ← PROCHAINE ÉTAPE
- Application React standalone (Vite + TailwindCSS + shadcn/ui)
- ChatPanel, NodeCard, LogViewer, AuditLog, Auth UI
- Plugin Catalogue (page d'accueil, prépare Sprint 5)

**Sprint 5 : Plugin Ecosystem (Home Assistant-like)**
- Format standard de plugins, catalogue installable
- Moteur d'automatisations (trigger → condition → action)
- Exemples : backup, alerting, DNS updater

**Sprint 6 : Production Hardening**
- Rate limiting, rotation tokens, cross-compile Worker

---
*Fin du résumé. Fournis ce fichier comme contexte en début de chaque nouvelle session.*
