# Vigile — Session Init & Status

*Ce fichier permet à n'importe quel assistant IA ou développeur de comprendre instantanément le contexte du projet, son architecture et son état d'avancement.*

---
<!-- Dernière session : 2026-05-21 — Sprint 4.6 (Test Coverage Maximization to 93%) FINI -->
<!--
Résumé de la dernière session :
- Sprint 4.6 (Hausse de la couverture de tests à 93%) entièrement complété.
- Création de tests unitaires exhaustifs pour les routes API (test_auth.py, test_nodes.py, test_audit_api.py).
- Augmentation de la couverture sur les modules de cœur (NodeManager, SecurityManager, RateLimiter, ActionProposal, StructuredLLM, Database) à 100%.
- Correction des bugs dans la suite de tests (contrainte de clé étrangère SQLite pour nonexistent-user-id dans les tests de refresh token, et validation de longueur de mot de passe dans les tests de modification de mot de passe).
- Validation de 189 tests unitaires avec une couverture globale de 93%.
- Prochaine étape : Sprint 5 (Frontend React SPA).
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

## 🚀 État d'avancement : SPRINT 5 (Frontend React SPA)

Sprints 1 à 4 terminés — Fondations, Plugins OS, Couche IA, et prototype Frontend SSR + HTMX (remplacé par la React SPA).

**Sprint 5 (Frontend React SPA) — En développement :**

### ✅ Ce qui est implémenté et validé (189 Tests Unitaires — Couverture globale 93% ✅)

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

```bash
# Lancer le serveur Master en local
$env:PYTHONPATH="."  # Windows PowerShell
# ou export PYTHONPATH="." # Linux/macOS
python -m uvicorn master.main:app --host 127.0.0.1 --port 8000 --reload
```

- API Docs : `http://127.0.0.1:8000/api/docs`
- Compte Administrateur par défaut : `admin` / `admin` (Changement de mot de passe obligatoire à la première connexion)

### 2. Lancer les tests

Les tests sont gérés par `pytest` :

```bash
# Lancer les tests unitaires (ne requiert pas que le serveur tourne)
$env:PYTHONPATH="."  # Windows PowerShell
# ou export PYTHONPATH="." # Linux/macOS
python -m pytest -m "not integration" -v

# Lancer les tests d'intégration (requiert le serveur en marche sur http://127.0.0.1:8000)
python -m pytest -m "integration" -v

# Lancer la totalité des tests (requiert le serveur en marche)
python -m pytest -v
```

---

## ⏭️ Prochaines Étapes (Sprint 5)

**Sprint 5 : Frontend React SPA** ← PROCHAINE ÉTAPE

**Sprint 2 : Plugins OS et Worker Go (Terminé ✅)**

- ✅ `metrics_plugin.py` — Métriques CPU/RAM/disque/swap/uptime, validation Pydantic, pipeline STATUS_REPORT
- ✅ API `GET /api/nodes/{id}/stats` — exposition des métriques (persistance DB, limit param, Operator+)
- ✅ Worker Go — Binaire autonome (zéro dépendance), handshake Ed25519, collecte métriques
- ✅ Docker Compose test stack : Master + Workers isolés
- ✅ API `GET /api/nodes/{id}/logs` — logs live des Workers via intent (READ_LOGS / READ_LOGS_SERVICE)
- ✅ Plugin `systemd` + `docker` — déclarent les actions supportées via `get_supported_actions`
- ✅ API systemd : `GET /services`, `GET /services/{name}`, `POST /services/{name}/restart`
- ✅ API Docker : `GET /containers`, `POST /containers/{id}/restart`
- ✅ **285 tests** (tous niveaux : unitaires + intégration + simulation)
- ✅ **Déploiement sur youcloud.ovh, test end-to-end complet**
  - 45 services systemd listés, ssh.service actif/enabled
  - 39 containers Docker listés (via socket Unix fixé)
  - Logs SSH temps réel (journalctl)
  - Métriques CPU/MEM/DISK via STATUS_REPORT 60s
  - Bug `containers.go:DialContext` fixé (écrasait le socket Unix par TCP)

**Sprint 3 : Couche IA et Human-in-the-Loop (Terminé ✅ — validé niveaux 1, 2, 3, 4)**

- `LLMClient` natif : complete + stream SSE
- `StructuredLLM` : boucle retry + validation Pydantic
- `ActionProposal` : modèle Pydantic + table DB (PENDING→APPROVED→EXECUTED|FAILED)
- Chat API : POST /api/chat (SSE), POST /proposals/approve, POST /proposals/reject

**Sprint 4 : Prototype Frontend (FastAPI + Jinja2 + HTMX + Tailwind) (Terminé ✅ — Déprécié/Remplacé)**

- Architecture SSR initiale avec Jinja2 templates (supprimés lors de la migration React au Sprint 5)
- HTMX pour l'interactivité (navigation, polling, formulaires)
- Responsive mobile et design System Glass Dark Ops (carrousels, overlays, sidebars)
- ChatPanel/Copilot sidebar, NodeCard, LogViewer, AuditLog, Auth UI
- Plugin Catalogue (page d'accueil)

**Sprint 4.5 : Stabilisation & Migration Tests (Terminé ✅)**

- Résolution de 6 bugs critiques de `LIMITS.md` :
  - Support de migrations Alembic lors de l'initialisation de l'application
  - Tâche en arrière-plan asynchrone pour nettoyer la mémoire du rate limiter
  - Système de détection de vol avec rotation de famille de refresh tokens et révocation globale
  - Obligation de changement du mot de passe admin par défaut à la première connexion (code d'erreur 403 `MUST_CHANGE_PASSWORD`)
  - Pagination de la liste de nœuds et du journal d'audit
  - Protection contre la double-inscription des plugins lors des rechargements
- Résolution des violations d'Injection de Dépendances (DI) des paramètres système dans `database.py`, `auth.py`, `nodes.py`, et `worker_handler.py`.
- Migration complète du harnais de test (~305 assertions) vers `pytest` dans un format modulaire (90 tests unitaires, 1 test d'intégration).
- Nettoyage et suppression des répertoires de tests historiques `tests/unit` et `tests/integration`.
- Réécriture globale du `README.md`.

**Sprint 4.6 : Test Coverage Maximization to 93% (Terminé ✅)**

- Augmentation de la couverture de test globale de 60% à 93% (dépassant l'objectif de 90%+).
- Couverture complète de toutes les routes de l'API REST :
  - Authentification (`tests/test_api/test_auth.py`)
  - Nœuds (`tests/test_api/test_nodes.py`)
  - Logs d'audit (`tests/test_api/test_audit_api.py`)
- Couverture maximale (100% ou proche) pour tous les gestionnaires cœurs (`NodeManager`, `RateLimiter`, `SecurityManager`, `ActionProposal`, `StructuredLLM`, `Database`).
- Résolution de deux bugs identifiés dans la suite de tests (contrainte FK sur les refresh tokens pour nonexistent-user-id et schéma de validation de longueur pour le mot de passe).

**Sprint 5 : Frontend React SPA**
- Reconstruire le frontend en React/Vite avec design Glass Dark Ops
- Chat SSE streaming, proposals approve/reject, et Recharts
- Intégration shadcn/ui et Tailwind CSS v4

**Sprint 6 : Plugin SDK & Intégrations (Plugin Ecosystem)**
- Format de plugin standardisé, catalogue installable
- Intégrations concrètes (Home Assistant, Plex/Arr)
- UI d'installation et activation dans le frontend

**Sprint 7 : Automation Engine & Notifications**
- Moteur d'automatisations (trigger → condition → action)
- Alertes multi-canal (Webhook, Ntfy, Email SMTP)

**Sprint 8 : Production Hardening & PostgreSQL**
- Migration SQLite → PostgreSQL, rate limiter persistant
- Rotation automatique WORKER_TOKEN, endpoint /metrics Prometheus

**Sprint 9 : Alertes Intelligentes & Runbooks**
- Baseline automatique des métriques et alertes prédictives
- Bibliothèque de runbooks pour auto-healing et rollback automatique

**Sprint 10 : Mémoire Conversationnelle & Autonomie Graduée**
- Historique et recherche sémantique des conversations
- Niveaux d'autonomie graduée par type d'action

---
*Fin du résumé. Fournis ce fichier comme contexte en début de chaque nouvelle session.
Voir aussi `docs/PLAN.md` pour la vision long terme (Sprints 7→11).*
