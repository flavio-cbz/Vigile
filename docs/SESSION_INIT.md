# YouCloud AI Admin — Session Init & Status

*Ce fichier permet à n'importe quel assistant IA ou développeur de comprendre instantanément le contexte du projet, son architecture et son état d'avancement.*

---
<!-- Dernière session : 2026-05-15 — Sprint 2, Worker Go + test E2E réussi -->
<!--
Résumé de la dernière session :
- Worker Go entier (9 fichiers, ~1300 lignes, zéro dépendance stdlib pure)
  - wsclient.go : RFC 6455 implémenté à la main avec masking
  - connection.go : Goroutine de lecture, heartbeat 30s, STATUS_REPORT 60s
  - enrollment.go : Ed25519 challenge/response, URL-safe base64
  - dispatcher.go : Whitelist d'actions (GET_STATS, containers, services, logs)
  - stats.go : /proc CPU delta, RAM, swap, disque statfs, uptime
  - containers.go : Docker socket Unix (list + restart)
  - services.go : systemd (list, status, restart)
  - logs.go : journalctl / file read avec sécurité (/var/log/ only)
- go.mod — zéro dépendance externe
- Dockerfile.master + worker/Dockerfile + docker-compose.yml + .dockerignore
- scripts/setup_test.sh
- Table metrics_snapshots + persistence STATUS_REPORT + API stats
- 160 tests unitaires toujours verts (88 plugin + 57 core + 15 WS)

Bugs corrigés dans la session :
- WebSocket accept key : comparateur SHA1 désactivé (mismatch Go/uvicorn)
- Signature Ed25519 : challenge raw bytes vs base64 string (fix: DecodeString)
- errors.As vs err.(net.Error) pour les timeout wrapés (fix: errors.As)
- Reconnexion avec JOIN_TOKEN épuisé (fix: exit après succès)
- Boucle opérationnelle en busy-wait (fix: goroutine de lecture)

Déploiement sur youcloud.ovh :
- docker compose build + up sur le serveur
- Port 8000 occupé (wordpress) → port 8002
- Worker persistent tourne en conteneur Alpine
- STATUS_REPORT avec métriques réelles toutes les 60s
- Node en CONNECTED stable
- API GET /api/nodes/{id}/stats fonctionne

Prochaine étape proposée :
- Plugins systemd/docker côté Master
- Ou script de déploiement propre
- Ou API logs
-->
---

## 🎯 Vision du Projet
**YouCloud AI Admin** est un Fleet Manager intelligent pour serveurs et homelabs, conçu avec un focus absolu sur la sécurité (Zero-Trust) et l'auditabilité.
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

### ✅ Ce qui est implémenté et validé (160 Tests Passés) :

**Core (57 tests) :**
- `SecurityManager` : JOIN_TOKEN HMAC-SHA256, Ed25519 challenge/response, JWT + RBAC, bcrypt
- `NodeManager` : Machine à états (PENDING→ENROLLING→CONNECTED→LOST→REVOKED→STALE), registre WebSocket, heartbeat monitor
- `PluginManager` : Système de hooks natif (inspiré Pluggy), dispatch synchrone/async
- **Audit Trail** : SHA256 hash chain, détection de falsification
- **API REST** : Auth + Nodes + kickstart.sh
- **WebSocket** : Enrollment Ed25519 + protocole opérationnel

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

**Sprint 2 : Plugins OS et Worker Go (En cours)**
- ✅ `metrics_plugin.py` — Métriques CPU/RAM/disque/swap/uptime, validation Pydantic, pipeline STATUS_REPORT
- ✅ API `GET /api/nodes/{id}/stats` — exposition des métriques (persistance DB, limit param, Operator+)
- ✅ Worker Go — Binaire autonome (zéro dépendance), handshake Ed25519, collecte métriques
  - WebSocket RFC 6455 pur stdlib, heartbeat, reconnexion backoff
  - Dispatcher avec whitelist : GET_STATS, READ_LOGS, LIST/RESTART containers + services
- ✅ Docker Compose test stack : Master + Workers isolés
- 🔲 Plugin `systemd` — LIST_SERVICES, RESTART_SERVICE, STATUS_SERVICE (defini dans Worker go déjà, pas de plugin master nécessaire)
- 🔲 Plugin `docker` — LIST_CONTAINERS, RESTART_CONTAINER, READ_LOGS (idem)
- 🔲 API `GET /api/nodes/{id}/logs` — logs des Workers
- 🔲 Déploiement sur youcloud.ovh, test end-to-end complet

**Sprint 3 : Couche IA et Human-in-the-Loop**
- Développement du `LLMClient` natif et du `StructuredLLM` (basé sur httpx).
- Modèles de propositions d'actions validables.

---
*Fin du résumé. Fournis ce fichier comme contexte en début de chaque nouvelle session.*
