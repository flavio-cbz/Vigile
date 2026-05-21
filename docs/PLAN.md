# Vigile — Plan Technique

> Fleet Manager intelligent pour serveurs et homelabs.
> Zero-Trust. Zéro Dépendance Tierce sur le Core. Zéro SSH.
> Construit pour le homelab, architecturé pour la flotte.

---

## Vision

Une plateforme d'administration de serveurs en deux parties : un **Master Node** qui centralise l'intelligence, et des **Worker Nodes** (agents binaires autonomes) déployés sur chaque machine. L'IA analyse, propose, l'humain approuve, le Worker exécute. Jamais l'inverse.

### Ce que Vigile résout

1. **Le shell root donné à une IA est dangereux** — Vigile interpose un Worker avec une whitelist de commandes immuable. L'IA ne touche jamais un terminal.
2. **Monitorer depuis le serveur qu'on surveille est une erreur** — Le Master vit sur un VPS stable, indépendant du homelab.
3. **Les outils d'admin sont trop complexes** — Vigile est un copilote : tu poses une question en langage naturel, il propose une solution, tu approuves.

### Public cible

- **Aujourd'hui** : administrateurs de homelab (1-5 machines, Docker, Home Assistant, Plex)
- **Demain** : petites équipes ops gérant des dizaines de serveurs

Le différenciateur n'est pas la liste de features. C'est la confiance : chaque ligne de code du core est lisible, auditable, sans dépendance cachée.

---

## Philosophie Technique : Zéro Dépendance Tierce sur le Core

La règle est simple. Pour chaque partie complexe du système, on identifie le projet open source de référence, on étudie son code source, on extrait le pattern, on l'implémente nativement. Pas d'installation de la librairie.

Ce que ça garantit :

- **Zéro supply chain attack** sur le core
- **Binaire Worker autonome** sans aucune dépendance système
- **Auditabilité totale** : chaque ligne est la nôtre
- **Déploiement trivial** : un seul binaire, zéro configuration d'environnement

### Dépendances acceptées

| Couche | Dépendances | Justification |
|--------|-------------|---------------|
| **Master (Python)** | `fastapi`, `uvicorn`, `aiosqlite`→`asyncpg`, `python-jose`, `passlib`, `httpx`, `pydantic` | Fondations bas-niveau stables |
| **Worker (Go)** | **Zéro import externe** — stdlib uniquement | Sécurité maximale |
| **Frontend (React)** | `react`, `vite`, `tailwindcss`, `shadcn/ui`, `recharts`, `zustand` | Outils de construction UI |
| **Dev tooling** | `pytest`, `ruff`, `mypy` | Qualité de développement (pas en prod) |

> **Règle** : La whitelist runtime (Master + Worker) est sacrée. Le dev tooling (pytest, linters) est séparé et n'impacte pas le déploiement.

---

## Sources d'Inspiration (Code Étudié, Pas Installé)

| Projet Open Source | Ce qu'on étudie | Ce qu'on implémente nativement |
|---|---|---|
| **LiteLLM** | Abstraction universelle provider, format OpenAI-compatible | `LLMClient` : httpx, stream SSE, zéro vendor lock |
| **Open WebUI** | Format message chat, streaming SSE côté React | Composant `ChatPanel` React natif, SSE reader |
| **Instructor** | Boucle retry sur structured outputs, validation Pydantic | `StructuredLLM` : wrapper qui force un schéma Pydantic |
| **Portainer Agent** | Reconnexion WebSocket avec backoff, heartbeat, dispatch | Worker Go intégral |
| **Pluggy (pytest)** | Système hookspec/hookimpl, registre de plugins | `PluginManager` : dict de hooks, chargement dynamique |
| **FastAPI-Users** | JWT, refresh token, hashing bcrypt, middleware d'auth | `SecurityManager` : JWT natif, bcrypt passlib |
| **Netdata kickstart.sh** | Détection OS/arch, vérification SHA256, installation systemd | `kickstart.sh` Vigile |
| **Dozzle** | Streaming de logs Docker via WebSocket | Plugin `LOG_STREAM` du Worker |
| **Home Assistant** | Architecture plugin, automations (trigger→condition→action) | Automation Engine natif |

---

## Architecture

```text
┌───────────────────────────────────────────────────────────────┐
│                         MASTER NODE                           │
│                                                               │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐       │
│  │ FastAPI  │  │     Core     │  │   LLM Client     │       │
│  │ REST+WSS │  │ ──────────── │  │  (natif httpx)   │       │
│  │          │  │ Security     │  │                   │       │
│  │ /api/*   │  │ Manager      │  │  → OpenAI        │       │
│  │ /ws/*    │  │ Node         │  │  → Ollama        │       │
│  │          │  │ Manager      │  │  → Anthropic     │       │
│  │          │  │ Plugin       │  │  → Any OpenAI-   │       │
│  │          │  │ Manager      │  │    compatible     │       │
│  └──────────┘  └──────────────┘  └──────────────────┘       │
│                                                               │
│  ┌──────────────────────┐  ┌──────────────────────────────┐  │
│  │ SQLite (dev/small)   │  │ React SPA (Vite build)       │  │
│  │ PostgreSQL (prod)    │  │ Servi via /static/ en prod   │  │
│  └──────────────────────┘  └──────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
              ↑ WSS (Workers initient, contournent NAT)
              │
    ┌─────────┴──────────┐
    │                    │
┌───┴──────┐      ┌──────┴────┐
│ Worker A │      │ Worker B  │
│ (Go bin) │      │ (Go bin)  │
│          │      │           │
│ Debian   │      │ Alpine    │
│ x86_64   │      │ ARM64     │
│ Docker ✓ │      │ Docker ✗  │
└──────────┘      └───────────┘
```

**Règle absolue** : le Master ne connaît pas l'OS des Workers au moment du déploiement. Tout est découvert dynamiquement lors de la première connexion.

---

## Sécurité et Enrollment

### Flux complet d'enrollment en deux phases

```text
PHASE 1 — Installation (kickstart.sh)
─────────────────────────────────────
1. L'Admin clique "Ajouter un Node" dans l'UI
2. Master génère un JOIN_TOKEN signé HMAC-SHA256 :
   payload = { node_id, expires_at (+30min), ip_prefix, single_use: true }
   token   = base64url(HMAC-SHA256(server_secret, payload)) + "." + base64url(payload)
3. UI affiche :
   curl -sSL https://master/api/nodes/kickstart.sh | sh -s -- --token TOKEN --master https://master
4. kickstart.sh s'exécute :
   a. Détecte OS (Linux/Darwin/FreeBSD) et ARCH (x86_64/aarch64/armv7l)
   b. Télécharge le bon binaire : /api/nodes/binary/{os}/{arch}/worker
   c. Télécharge le hash     : /api/nodes/binary/{os}/{arch}/worker.sha256
   d. Vérifie SHA256 → abort si mismatch
   e. Installe le binaire comme service natif (systemd/launchd/rc.d)
   f. Stocke le JOIN_TOKEN dans /etc/vigile/enrollment.token (chmod 600)
   g. Démarre le service
   h. trap EXIT → cleanup /tmp systématique

PHASE 2 — Claiming (Worker → Master, au démarrage du service)
─────────────────────────────────────────────────────────────
1. Worker génère une paire Ed25519 (clé privée /etc/vigile/worker.key, chmod 400)
2. Worker ouvre une connexion WSS vers master/ws/worker/join
3. Worker envoie :
   { type: "ENROLLMENT_REQUEST",
     join_token: "...",
     public_key: "ed25519:base64...",
     fingerprint: { hostname, machine_id: sha256(/etc/machine-id), arch } }
4. Master valide : HMAC du token, TTL, ip_prefix, single_use (vérifie en DB)
5. Master envoie un CHALLENGE :
   { type: "ENROLLMENT_CHALLENGE", challenge: "random_32_bytes_base64" }
6. Worker signe le challenge avec sa clé privée Ed25519
7. Worker envoie :
   { type: "ENROLLMENT_RESPONSE", signature: "base64..." }
8. Master vérifie la signature avec la clé publique reçue
9. Master stocke : node_id + public_key + fingerprint en DB
10. Master invalide le JOIN_TOKEN (single_use → consumed: true)
11. Master envoie :
    { type: "ENROLLMENT_SUCCESS",
      worker_token: "...",
      master_public_key: "..." }
12. Connexion WSS bascule en mode opérationnel
```

### États du Node (NodeManager)

```text
ENROLLING    → Handshake Ed25519 en cours
CONNECTED    → WSS active, heartbeat OK (toutes les 30s)
RECONNECTING → Connexion perdue, backoff exponentiel (5s → 10s → 20s → ... → 5min max)
LOST         → Aucun heartbeat depuis > seuil configurable (défaut : 5 min)
STALE        → LOST depuis > 24h
REVOKED      → Révocation manuelle ou sécurité, toute connexion refusée
```

### RBAC

| Rôle | Stats | Logs | Approuver action | Gérer nodes | Gérer users |
|---|---|---|---|---|---|
| **Viewer** | ✓ | ✓ | ✗ | ✗ | ✗ |
| **Operator** | ✓ | ✓ | ✓ | ✗ | ✗ |
| **Admin** | ✓ | ✓ | ✓ | ✓ | ✓ |

### Audit Trail avec hash chaîné

Chaque entrée contient le hash SHA256 de l'entrée précédente. Toute modification de la base est détectable. Append-only. Jamais de DELETE.

---

## Worker & Registre de Commandes (Go — Zéro Import Externe)

Le binaire Worker n'utilise que la stdlib Go. Aucun `go get`. Compilable sur n'importe quelle machine avec Go installé.

### Architecture du Registre de Commandes

```text
WORKER GO (immuable, compilé dans le binaire)
├── Liste des commandes autorisées (CommandID → CommandDef)
├── Chemins absolus des binaires
├── Patterns de validation des arguments (regex)
├── Timeout par commande
├── MaxOutputBytes par commande
├── MaxInputBytes par commande
├── Plancher de classification minimum (MinClassification)
└── Classification par défaut (DefaultClassification)

MASTER FASTAPI (configurable, stocké en base)
├── Classification choisie par l'utilisateur, par serveur
├── Ne peut JAMAIS descendre en dessous du plancher Worker
├── Logique de confirmation selon classification
├── Expiration des confirmations (30 secondes)
└── Log d'audit de chaque commande exécutée/refusée
```

### Niveaux de classification des commandes

| Niveau | Comportement | Exemples |
|--------|-------------|----------|
| `READ_ONLY` | Exécution directe sans confirmation | `docker.ps`, `systemd.status` |
| `AMBIGUOUS` | Avertissement d'exposition de données | `docker.logs`, `file.read.config` |
| `DESTRUCTIVE` | Confirmation humaine obligatoire | `docker.stop`, `service.reload.nginx` |

### Sécurité du Système de Fichiers

- **ValidatedPath** : double vérification (blacklist immuable Worker + whitelist configurable Master)
- **`docker.exec` décomposé** en 4 commandes distinctes (top, cp.out, exec.safe, exec.shell)
- **Shells strictement interdits** dans `docker.exec.safe` (sh, bash, zsh, python, node)
- **Path traversal impossible** : `filepath.Clean()` + `filepath.EvalSymlinks()` sur le chemin réel

### Protections contre les Saturations de Ressources

1. **`io.LimitReader`** : coupe la sortie à `MaxOutputBytes`, tue le processus
2. **Timeout strict** : terminaison active via contexte
3. **WebSocket Write Deadline** : 10s par envoi, abort si blocage

---

## Flux IA : Human-in-the-Loop

Le LLM ne touche jamais un Worker directement.

```text
Utilisateur pose une question dans le ChatPanel
           ↓
Master construit le contexte (état du node, métriques récentes)
           ↓
LLMClient.stream() → ChatPanel affiche la réponse en streaming
           ↓
Si une action est nécessaire :
StructuredLLM.create(ActionProposal) → objet Python typé et validé
           ↓
UI affiche la proposition avec boutons [Approuver] / [Refuser]
           ↓ (clic Approuver par un Operator ou Admin)
Master route l'Intent JSON au Worker via WSS
           ↓
Worker exécute (action dans sa whitelist)
           ↓
Résultat renvoyé au Master → Audit Trail signé
```

---

## Structure des Dossiers (état cible)

```tree
vigile/
├── master/
│   ├── main.py                      # FastAPI entrypoint, lifespan
│   ├── config.py                    # Settings depuis env vars
│   ├── core/
│   │   ├── security_manager.py      # JOIN_TOKEN, WORKER_TOKEN, Ed25519, JWT, RBAC
│   │   ├── node_manager.py          # États nodes, WebSockets, heartbeat
│   │   ├── plugin_manager.py        # Hooks natif (inspiré Pluggy)
│   │   ├── llm_client.py            # Client LLM universel (inspiré LiteLLM)
│   │   ├── structured_llm.py        # Structured outputs (inspiré Instructor)
│   │   ├── action_proposal.py       # ActionProposal state machine
│   │   ├── automation_engine.py     # Trigger → Condition → Action (Sprint 7)
│   │   └── notification_manager.py  # Webhook, Ntfy, Email (Sprint 7)
│   ├── api/
│   │   ├── auth.py                  # POST /auth/login, /auth/refresh
│   │   ├── nodes.py                 # Nodes CRUD + kickstart.sh + binaires
│   │   ├── services.py              # Services + Containers
│   │   ├── chat.py                  # POST /chat (SSE), proposals approve/reject
│   │   ├── plugins.py               # Plugin CRUD (Sprint 6)
│   │   ├── automations.py           # Automations CRUD (Sprint 7)
│   │   └── deps.py                  # FastAPI DI
│   ├── ws/
│   │   └── worker_handler.py        # WebSocket enrollment + opérationnel
│   ├── plugins/
│   │   ├── metrics_plugin.py        # CPU, RAM, disque (cross-platform)
│   │   ├── docker_plugin.py         # Actions Docker
│   │   ├── systemd_plugin.py        # Actions systemd
│   │   ├── homeassistant_plugin.py  # Home Assistant (Sprint 6)
│   │   └── plex_plugin.py           # Plex/Arr stack (Sprint 6)
│   ├── db/
│   │   ├── models.py                # DDL (SQLite → PostgreSQL)
│   │   └── migrations.py            # Migrations versionnées
│   ├── templates/                   # Jinja2 (legacy, conservé comme fallback)
│   └── static/                      # Build React servi en prod
│
├── frontend/                        # React SPA (Sprint 5)
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatPanel.tsx        # Chat streaming SSE
│   │   │   ├── ActionProposal.tsx   # Human-in-the-Loop
│   │   │   ├── NodeCard.tsx         # État node + métriques
│   │   │   ├── LogViewer.tsx        # Logs temps réel
│   │   │   ├── MetricsChart.tsx     # Graphiques Recharts
│   │   │   ├── ServiceList.tsx      # Services systemd
│   │   │   ├── ContainerList.tsx    # Containers Docker
│   │   │   └── AuditLog.tsx         # Trail immuable
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── NodeDetail.tsx
│   │   │   ├── Proposals.tsx
│   │   │   ├── Audit.tsx
│   │   │   └── Plugins.tsx
│   │   ├── lib/
│   │   │   ├── api.ts               # Client API typé
│   │   │   ├── sse.ts               # SSE reader pour streaming LLM
│   │   │   └── auth.ts              # JWT auth + refresh
│   │   └── store/
│   │       ├── nodes.ts             # State management (Zustand)
│   │       └── chat.ts
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── package.json
│
├── worker/                          # Go binary (stdlib only)
│   ├── main.go
│   ├── wsclient.go                  # WebSocket RFC 6455 stdlib
│   ├── enrollment.go                # Ed25519 handshake
│   ├── connection.go                # Reconnect, heartbeat, STATUS_REPORT
│   ├── dispatcher.go                # Whitelist + dispatch
│   ├── discovery.go                 # OS/arch/hostname detection
│   ├── stats.go                     # CPU/RAM/disk from /proc
│   ├── logs.go                      # journalctl + file logs
│   ├── containers.go                # Docker via Unix socket
│   ├── services.go                  # systemd management
│   └── Dockerfile                   # Multi-stage alpine
│
├── tests/
│   ├── unit/                        # pytest (Sprint 4.5)
│   ├── integration/                 # pytest + httpx
│   └── conftest.py                  # Fixtures partagées
│
└── scripts/
    ├── kickstart.sh                 # Installation Worker universelle
    ├── setup_test.sh                # Docker Compose test stack
    └── test_all_simulation.py       # Simulation tests
```

---

## Roadmap par Sprints

### Sprints terminés

| Sprint | Contenu | Statut |
|--------|---------|--------|
| 1 | Core Sécurisé : SecurityManager, NodeManager, PluginManager, DB, WebSocket enrollment, Worker Go basics | ✅ Done |
| 2 | Plugins OS : metrics, systemd, docker + APIs REST + kickstart.sh + simulation stack | ✅ Done |
| 3 | Couche IA : LLMClient, StructuredLLM, ActionProposal, Chat API (SSE stream) | ✅ Done |
| 4 | Frontend Jinja2 + HTMX + Tailwind CSS v4 (Glass Dark Ops design) | ✅ Done |

---

### Sprint 4.5 — Stabilisation & Migration Tests 🔧

**Objectif** : Corriger les bugs critiques documentés dans LIMITS.md et migrer le framework de test vers pytest. Aucune feature nouvelle.

**Critères de sortie** :
- [ ] Tous les bugs 🔴 de LIMITS.md corrigés
- [ ] Suite pytest opérationnelle avec couverture ≥ anciens 305 checks
- [ ] README.md mis à jour (plus d'informations fausses)
- [ ] Tous les tests verts

**Contenu** :

#### Bugs critiques (LIMITS.md 🔴)

| Bug | Fix |
|-----|-----|
| Rate limiter : `cleanup_expired()` jamais appelé | Tâche asyncio périodique dans le lifespan |
| Refresh token sans invalidation | Table `refresh_tokens` avec flag `revoked` |
| Pas de force-change admin password | Flag `must_change_password` + middleware |
| Plugin deduplication absente | Check `already_loaded` dans `load_plugins_from_dir()` |
| Aucune pagination sur `list_nodes` et `verify_chain` | `limit`/`offset` params sur les endpoints REST |
| Migration DB non versionnée | Table `schema_version` + scripts numérotés |

#### Migration Tests

- Installer pytest comme dépendance dev
- Réécrire les 9 fichiers de test en pytest avec fixtures
- Les 305 checks actuels deviennent le cahier des charges des tests pytest
- Créer `conftest.py` avec fixtures partagées (fake DB, fake SecurityManager, etc.)
- Supprimer l'ancien harness custom (`check()` + `results` pattern)

#### README.md

- Corriger les erreurs factuelles (Redis → SQLite, E2E → TLS)
- Ajouter section Getting Started propre
- Ajouter section Architecture avec diagramme
- Garder l'histoire personnelle (c'est l'âme du projet)

---

### Sprint 5 — Frontend React SPA 🎨

**Objectif** : Reconstruire le frontend en React/Vite avec le design Glass Dark Ops identique au Sprint 4. Le Master sert le build React via `/static/` en prod.

**Critères de sortie** :
- [ ] Toutes les pages du Sprint 4 Jinja2 reproduites en React
- [ ] Chat SSE streaming fonctionnel
- [ ] Proposals approve/reject fonctionnel
- [ ] Design pixel-perfect Glass Dark Ops
- [ ] Vite dev proxy → FastAPI (:8000) configuré
- [ ] Build prod copié dans `master/static/`, servi par FastAPI

**Contenu** :

#### Setup

- Initialiser projet Vite + React + TypeScript dans `frontend/`
- Configurer Tailwind CSS v4 avec la palette Glass Dark Ops
- Configurer le proxy Vite → `http://localhost:8000/api/`
- Ajouter shadcn/ui comme librairie de composants de base

#### Pages

| Page | Composants | Interactivité |
|------|-----------|---------------|
| **Login** | Auth form, JWT storage | POST /api/auth/login |
| **Dashboard** | NodeCard carousel, MetricsBar, HeroDiscovery | Polling 15s |
| **Node Detail** | Tabs (Stats, Services, Containers, Logs), MetricsChart | Polling + on-demand |
| **Proposals** | ProposalList, ApproveButton, RejectButton | POST approve/reject |
| **Audit** | AuditTimeline, HashVerification | GET + polling |
| **Plugins** | PluginGrid, PluginCard | GET /api/plugins |

#### Composants clés

| Composant | Technologie |
|-----------|------------|
| `ChatPanel` (Copilot sidebar) | EventSource SSE, streaming token-by-token |
| `MetricsChart` | Recharts (line charts CPU/RAM/disk) |
| `LogViewer` | Composant scroll avec auto-follow |
| `ActionProposal` | Card glassmorphic avec boutons approve/reject |

#### Design System

- Palette : `#050505` (bg), `#0a0a0c` (surface), `#111114` (surface-2), `teal-400` (accent)
- Glassmorphism : `bg-white/[0.02] border border-white/[0.05] backdrop-blur-xl`
- Layout : Sidebar gauche (80→240px hover) + Main + Copilot droite (340-400px)
- Typographie : Inter uniquement, text-[13px] à text-[15px]
- Icônes : Tabler Icons SVG

---

### Sprint 6 — Plugin SDK & Intégrations 🔌

**Objectif** : Créer un framework de plugins standardisé avec métadonnées, configuration UI, et les premières intégrations concrètes (Home Assistant, Plex/Arr).

**Critères de sortie** :
- [ ] Format de plugin documenté (manifest.json, hooks, config schema)
- [ ] Plugin Home Assistant fonctionnel (lire config YAML, proposer des fixes)
- [ ] Plugin Plex/Arr fonctionnel (monitoring, restart)
- [ ] UI d'installation/activation de plugins dans le frontend React
- [ ] Plugin SDK documenté (template + guide pour créer un plugin)

**Contenu** :

#### Plugin SDK

```text
plugins/
├── homeassistant/
│   ├── manifest.json      # Nom, version, hooks, config schema
│   ├── plugin.py          # Hooks + logique métier
│   └── README.md          # Documentation
├── plex/
│   ├── manifest.json
│   ├── plugin.py
│   └── README.md
```

Chaque plugin déclare :
- **Métadonnées** : nom, version, description, auteur, icône
- **Configuration** : schéma JSON des paramètres (URL, tokens, chemins)
- **Hooks** : `get_supported_actions`, `handle_intent`, `on_status_report`, etc.
- **Actions Worker** : commandes supplémentaires que le Worker devrait supporter

#### Intégrations concrètes

| Plugin | Actions | Classification |
|--------|---------|---------------|
| **Home Assistant** | Lire config YAML, diagnostiquer logs, proposer fixes, restart service | READ_ONLY → DESTRUCTIVE |
| **Plex** | Status API, sessions actives, restart service | READ_ONLY → DESTRUCTIVE |
| **Radarr/Sonarr** | Status queue, health check, restart | READ_ONLY → DESTRUCTIVE |

#### API Plugins

- `GET /api/plugins` — lister les plugins installés
- `POST /api/plugins/{name}/enable` — activer un plugin
- `POST /api/plugins/{name}/disable` — désactiver un plugin
- `PUT /api/plugins/{name}/config` — configurer un plugin (schéma validé)

---

### Sprint 7 — Automation Engine & Notifications 🤖

**Objectif** : Construire un moteur d'automatisations (trigger → condition → action) et un système de notifications multi-canal. C'est ce qui rend Vigile proactif plutôt que réactif.

**Critères de sortie** :
- [ ] Moteur d'automatisations fonctionnel avec au moins 5 triggers différents
- [ ] Notifications Webhook + Ntfy + Email fonctionnelles
- [ ] Au moins 3 automatisations pré-configurées (exemples)
- [ ] UI de création/gestion d'automatisations dans le frontend
- [ ] Tests E2E d'une chaîne complète : trigger → condition → action → notification

**Contenu** :

#### Moteur d'Automatisations

```text
Trigger (événement)
    ↓
Condition (vérification)
    ↓
Action (exécution)
    ↓
Notification (alerte)
```

| Type | Exemples |
|------|----------|
| **Triggers** | STATUS_REPORT reçu, métrique > seuil, service down, container restart, CRON timer, webhook entrant |
| **Conditions** | CPU > 90% depuis 5min, disk usage > 80%, service failed, container exited, AND/OR/NOT |
| **Actions** | Intent Worker (restart service/container), appel LLM (diagnostic), webhook sortant, notification |
| **Notifications** | Webhook POST, Ntfy push, Email SMTP |

#### Automatisations pré-configurées (exemples)

| Nom | Trigger | Condition | Action |
|-----|---------|-----------|--------|
| **Disk Full Alert** | STATUS_REPORT | disk_usage > 85% | Notification Ntfy |
| **Container Auto-Restart** | STATUS_REPORT | container exited (non-zero) | Restart container + notification |
| **HA Config Watch** | Timer CRON (5min) | HA service état changed | Notification + diagnostic LLM |

#### Notifications

| Canal | Implémentation |
|-------|---------------|
| **Webhook** | POST HTTP configurable (URL, headers, body template) |
| **Ntfy** | POST sur `https://ntfy.sh/topic` ou instance self-hosted |
| **Email** | SMTP async (aiosmtplib ou httpx vers un relay) |

#### API Automations

- `GET /api/automations` — lister les automatisations
- `POST /api/automations` — créer une automation (JSON schema)
- `PUT /api/automations/{id}` — modifier
- `DELETE /api/automations/{id}` — supprimer
- `POST /api/automations/{id}/test` — tester (dry-run)

---

### Sprint 8 — Production Hardening & PostgreSQL 🏗️

**Objectif** : Rendre Vigile prêt pour un usage quotidien fiable. Migration SQLite → PostgreSQL, rate limiter robuste, métriques de santé, cross-compilation Worker.

**Critères de sortie** :
- [ ] PostgreSQL fonctionnel en remplacement de SQLite
- [ ] Migration automatique depuis une base SQLite existante
- [ ] Métriques `/metrics` Prometheus-compatible
- [ ] Rate limiter persistent (pas memory-only)
- [ ] Rotation automatique WORKER_TOKEN
- [ ] Cross-compilation Worker pour Linux/Darwin × x86_64/arm64
- [ ] Health check Master (`/health`) complet

**Contenu** :

#### Migration PostgreSQL

- Remplacer `aiosqlite` par `asyncpg` (ajout à la whitelist)
- Adapter tout le SQL (SQLite → PostgreSQL syntax)
- Script de migration automatique (lecture SQLite → écriture PostgreSQL)
- Garder SQLite comme option pour les petites installations (via config)

#### Hardening

| Fix | Détail |
|-----|--------|
| Rate limiter | Redis ou PostgreSQL backend (pas memory) |
| WORKER_TOKEN rotation | Rotation automatique soft (7j) / hard (30j) |
| CORS validation | Refuser wildcard si `allow_credentials=True` |
| Ed25519 key permissions | Vérifier `0o600` au chargement |
| WebSocket limits | Limite max connexions par IP |
| `_pending_intents` cleanup | TTL + garbage collector |

#### Build & Monitoring

- Cross-compilation Worker : `GOOS=linux GOARCH=amd64/arm64`
- Endpoint `/metrics` Prometheus (sans librairie, format texte natif)
- Health check `/health` : DB, nodes connectés, mémoire

---

### Sprint 9 — Alertes Intelligentes & Runbooks 🧠

**Objectif** : Donner à l'IA la capacité de détecter des problèmes avant qu'ils n'arrivent et d'exécuter des procédures de résolution pré-approuvées.

**Critères de sortie** :
- [ ] Baseline automatique des métriques (CPU/RAM/disk normaux vs anormaux)
- [ ] Alertes prédictives fonctionnelles ("disque plein dans 3 jours")
- [ ] Bibliothèque de runbooks (≥ 5 scénarios pré-configurés)
- [ ] Auto-healing sur les scénarios simples (container restart)
- [ ] Rollback automatique si une action empire la situation

**Contenu** :

#### Détection Proactive

- **Baseline métriques** : moyenne glissante sur 7 jours par node
- **Anomaly detection simple** : écart > 2σ de la baseline → alerte
- **Prédiction saturation** : extrapolation linéaire du trend disk/RAM → "plein dans N jours"
- **Analyse de logs** : patterns connus (OOM killer, segfault, permission denied) → alerte

> **Note** : Pas de ML complexe. Des heuristiques simples et fiables qui fonctionnent avec le volume de données d'un homelab.

#### Runbooks

```text
Runbook = {
  name: "nginx-502-fix",
  trigger: "LLM détecte un 502 dans les logs nginx",
  steps: [
    { action: "CHECK", command: "nginx -t" },
    { action: "RESTART", command: "systemctl restart nginx",
      rollback: "systemctl restart nginx-backup" },
    { action: "VERIFY", command: "curl -s localhost:80",
      expect: "status_code == 200" }
  ],
  on_failure: "NOTIFY + ESCALATE_TO_HUMAN"
}
```

- Stockés en base, éditables via l'UI
- Pré-approuvés par l'admin (pas de confirmation à chaque exécution)
- Historique complet dans l'audit trail
- Rollback automatique si `VERIFY` échoue

---

### Sprint 10 — Mémoire Conversationnelle & Autonomie Graduée 🧩

**Objectif** : L'IA se souvient des conversations précédentes, apprend des patterns d'approbation/rejet, et ajuste son niveau de confiance.

**Critères de sortie** :
- [ ] Conversations persistées et contextualisées par node
- [ ] L'IA rappelle les incidents passés dans ses diagnostics
- [ ] Niveaux de confiance par type d'action (auto-exécution des actions LOW risk)
- [ ] Tableau de bord "décisions de l'IA" (approuvées, rejetées, auto-exécutées)

**Contenu** :

#### Mémoire Conversationnelle

- Table `conversations` : historique par session et par node
- L'IA reçoit un résumé des 5 derniers incidents du node dans son contexte
- Recherche sémantique simple (keyword matching) dans l'historique

#### Autonomie Graduée

| Niveau de confiance | Comportement | Exemple |
|---------------------|-------------|---------|
| `AUTO` | Exécution directe, notification post-action | Restart container déjà approuvé 5x |
| `NOTIFY` | Exécution + notification simultanée | Cleanup logs > 1GB |
| `APPROVE` | Confirmation humaine requise (défaut) | Toute action nouvelle |

- Table `confidence_history` : chaque (action, contexte) → score de confiance
- Le score augmente avec les approbations, diminue avec les rejets
- Seuils configurables par l'admin

---

### Sprints futurs (non planifiés en détail)

| Sprint | Titre | Description courte |
|--------|-------|--------------------|
| 11 | **Distribution & CI/CD** | GitHub Actions, releases binaires, kickstart.sh fonctionnel, Docker Hub |
| 12 | **Mobile & WhatsApp** | PWA responsive, bot WhatsApp pour chatter avec Vigile |
| 13+ | **Fleet Scale** | Multi-tenant, coordination multi-nœuds, canary deployment |

> Ces sprints ne seront détaillés que quand les précédents seront terminés et le besoin réel validé.

---

## Ce qu'on ne construira jamais

- Pas de shell interactif. Jamais.
- Pas d'exécution de commande arbitraire. Whitelist hardcodée, point final.
- Pas de connexion sortante du Master vers les Workers (zéro SSH, zéro push).
- Pas de dépendance à un cloud provider (AWS, GCP, Azure).
- Pas de compte obligatoire chez un tiers pour fonctionner.

Le produit fonctionne entièrement en self-hosted, sur un Raspberry Pi si nécessaire.