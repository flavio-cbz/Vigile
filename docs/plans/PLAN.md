# Vigile — Plan Technique

> Fleet Manager intelligent pour serveurs et homelabs.
> Zero-Trust. Zéro Dépendance Tierce sur le Core. Zéro SSH.
> Vision long terme : système autonome dirigé par l'IA (Sprints 13→17).

---

## Vision

Une plateforme d'administration de flotte de serveurs en deux parties : un **Master Node** qui centralise l'intelligence, et des **Worker Nodes** (agents binaires autonomes) déployés sur chaque machine. L'IA analyse, propose, l'humain approuve, le Worker exécute. Jamais l'inverse.

Le différenciateur n'est pas la liste de features. C'est la confiance : chaque ligne de code du core est lisible, auditable, sans dépendance cachée.

---

## Philosophie Technique : Zéro Dépendance Tierce sur le Core

La règle est simple. Pour chaque partie complexe du système, on identifie le projet open source de référence, on étudie son code source, on extrait le pattern, on l'implémente nativement. Pas d'installation de la librairie. Pas de `pip install litellm`. Pas de `npm install open-webui`.

Ce que ça garantit :

- **Zéro supply chain attack** sur le core
- **Binaire Worker autonome** sans aucune dépendance système
- **Auditabilité totale** : chaque ligne est la nôtre
- **Déploiement trivial** : un seul binaire, zéro configuration d'environnement

Les seules dépendances acceptées sont les fondations bas-niveau stables et incontournables :

- Master : `fastapi`, `uvicorn`, `aiosqlite`, `python-jose`, `passlib`, `httpx`
- Worker : **zéro import externe** — stdlib Go uniquement (`net/http`, `crypto/ed25519`, `encoding/json`, `os/exec`)
- Frontend : React, TailwindCSS, shadcn/ui

---

## Sources d'Inspiration (Code Étudié, Pas Installé)

| Projet Open Source | Ce qu'on étudie | Ce qu'on implémente nativement |
| --- | --- | --- |
| **LiteLLM** | Abstraction universelle provider, format OpenAI-compatible, gestion Base URL + headers | `LLMClient` : classe Python 150 lignes, httpx, stream SSE, zéro vendor lock |
| **Open WebUI** | Format message chat, streaming SSE côté React, gestion historique de conversation | Composant `ChatPanel` React natif, SSE reader, store de conversation |
| **Instructor** | Boucle retry sur structured outputs, validation Pydantic, prompt engineering | `StructuredLLM` : wrapper qui force un schéma Pydantic avec 3 tentatives max |
| **Portainer Agent** | Reconnexion WebSocket avec backoff, heartbeat, dispatch d'intents, états de connexion | Intégralité du Worker Go |
| **Pluggy (pytest)** | Système hookspec/hookimpl, registre de plugins, dispatch par hook | `PluginManager` : 80 lignes Python, dict de hooks, chargement dynamique |
| **FastAPI-Users** | Génération JWT, validation, refresh token, hashing bcrypt, middleware d'auth | `SecurityManager` : JWT natif avec python-jose, bcrypt avec passlib |
| **Netdata kickstart.sh** | Détection OS/arch, vérification SHA256 binaire, installation systemd/launchd, cleanup trap | `kickstart.sh` Vigile avec cascade d'installation et enrollment en deux phases |
| **Dozzle** | Streaming de logs Docker via WebSocket, chunking, buffer circulaire | Plugin `LOG_STREAM` du Worker |

---

## Architecture

```text
┌─────────────────────────────────────────────────────────┐
│                      MASTER NODE                        │
│                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ FastAPI  │  │     Core     │  │   LLM Client     │  │
│  │ REST+WSS │  │ ────────── │  │  (natif httpx)   │  │
│  │          │  │ Security    │  │                  │  │
│  │ /api/*   │  │ Manager     │  │  → OpenAI        │  │
│  │ /ws/*    │  │ Node        │  │  → Ollama        │  │
│  │ /chat/*  │  │ Manager     │  │  → Anthropic     │  │
│  │          │  │ Plugin      │  │  → n'importe qui │  │
│  └──────────┘  │ Manager     │  └──────────────────┘  │
│                └──────────────┘                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │                  SQLite (aiosqlite)             │    │
│  │  nodes | tokens | users | audit_log | proposals │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
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

### JOIN_TOKEN (structure)

```python
# Côté Master — SecurityManager.generate_join_token()
import hmac, hashlib, json, base64, time

def generate_join_token(node_id: str, ip_prefix: str) -> str:
    payload = {
        "node_id": node_id,
        "expires_at": int(time.time()) + 1800,  # 30 minutes
        "ip_prefix": ip_prefix,
        "single_use": True
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(SERVER_SECRET_KEY, payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{sig}.{payload_b64}"
```

### WORKER_TOKEN (cycle de vie)

```text
issued_at      ←─────────────── maintenant
rotation_due   ←─────────────── +7 jours  (soft: Master envoie nouveau token à la prochaine connexion)
expires_at     ←─────────────── +30 jours (hard: connexion refusée)
revoked        ←─────────────── false (révocation manuelle par Admin)
```

Règle de sécurité : si le même WORKER_TOKEN est présenté depuis deux IPs simultanément → révocation immédiate + alerte Admin.

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

| Rôle | Lire les stats | Voir les logs | Approuver une action | Gérer les nodes | Gérer les users |
| --- | --- | --- | --- | --- | --- |
| **Viewer** | ✓ | ✓ | ✗ | ✗ | ✗ |
| **Operator** | ✓ | ✓ | ✓ | ✗ | ✗ |
| **Admin** | ✓ | ✓ | ✓ | ✓ | ✓ |

### Audit Trail avec hash chaîné

Chaque entrée contient le hash SHA256 de l'entrée précédente. Toute modification de la base est détectable.

```python
class AuditEntry(BaseModel):
    id: str
    timestamp: datetime
    user_id: str
    action: str
    node_id: str
    intent: dict
    approved_by: str
    previous_hash: str         # hash de l'entrée N-1
    entry_hash: str            # sha256(previous_hash + timestamp + action + ...)
```

---

## LLM Client Natif (inspiré de LiteLLM)

Pattern extrait du code source de LiteLLM. Zéro import de la librairie.

```python
# core/llm_client.py — ~150 lignes, httpx uniquement
import httpx, json
from typing import AsyncIterator

class LLMClient:
    """
    Client universel OpenAI-compatible.
    Fonctionne avec OpenAI, Anthropic (via proxy), Ollama, OpenRouter,
    Mistral, ou n'importe quel endpoint compatible.
    """
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.model = model

    async def complete(self, messages: list[dict], **kwargs) -> str:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self.headers,
                json={"model": self.model, "messages": messages, **kwargs}
            )
            return r.json()["choices"][0]["message"]["content"]

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        async with httpx.AsyncClient() as client:
            async with client.stream("POST",
                f"{self.base_url}/v1/chat/completions",
                headers=self.headers,
                json={"model": self.model, "messages": messages, "stream": True}
            ) as r:
                async for line in r.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        chunk = json.loads(line[6:])
                        if token := chunk["choices"][0]["delta"].get("content"):
                            yield token
```

---

## Structured LLM pour les ActionProposals (inspiré d'Instructor)

Pattern extrait du code source d'Instructor. Zéro import de la librairie.

```python
# core/structured_llm.py
from pydantic import BaseModel
from typing import Type, TypeVar
import json

T = TypeVar("T", bound=BaseModel)

class StructuredLLM:
    def __init__(self, llm_client: LLMClient):
        self.client = llm_client

    async def create(self, response_model: Type[T], messages: list[dict], max_retries: int = 3) -> T:
        schema = response_model.model_json_schema()
        system_prompt = f"""Tu dois répondre UNIQUEMENT en JSON valide correspondant à ce schéma :
{json.dumps(schema, indent=2)}
Aucun texte avant ou après. Aucun bloc markdown."""

        full_messages = [{"role": "system", "content": system_prompt}] + messages

        for attempt in range(max_retries):
            raw = await self.client.complete(full_messages)
            try:
                return response_model.model_validate_json(raw)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise ValueError(f"Structured output failed after {max_retries} attempts: {e}")
                full_messages.append({"role": "assistant", "content": raw})
                full_messages.append({"role": "user", "content": f"Erreur de validation : {e}. Corrige."})
```

---

## Plugin Manager (inspiré de Pluggy)

Pattern extrait du code source de Pluggy. Zéro import de la librairie.

```python
# core/plugin_manager.py — ~80 lignes
from typing import Callable
import importlib, os

class PluginManager:
    def __init__(self):
        self._hooks: dict[str, list[Callable]] = {}

    def register(self, hook_name: str, fn: Callable):
        self._hooks.setdefault(hook_name, []).append(fn)

    def call(self, hook_name: str, **kwargs):
        results = []
        for fn in self._hooks.get(hook_name, []):
            result = fn(**kwargs)
            if result is not None:
                results.append(result)
        return results

    def load_plugins_from_dir(self, plugins_dir: str):
        for fname in os.listdir(plugins_dir):
            if fname.endswith(".py") and not fname.startswith("_"):
                module_name = fname[:-3]
                spec = importlib.util.spec_from_file_location(module_name, f"{plugins_dir}/{fname}")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "register"):
                    module.register(self)

# Un plugin s'écrit ainsi (plugins/docker_plugin.py) :
def register(pm: PluginManager):
    pm.register("get_supported_actions", lambda: ["RESTART_CONTAINER", "LIST_CONTAINERS", "READ_LOGS"])
    pm.register("handle_intent", handle_intent)

def handle_intent(intent: dict, node_id: str, node_ws):
    if intent["action"] not in ["RESTART_CONTAINER", "LIST_CONTAINERS", "READ_LOGS"]:
        return None
    # dispatch vers le Worker via node_ws
```

---

## Worker (Go — Zéro Import Externe)

Le binaire Worker n'utilise que la stdlib Go. Aucun `go get`. Compilable sur n'importe quelle machine avec Go installé.

```text
Packages stdlib utilisés :
- crypto/ed25519      → génération keypair + signature challenge
- crypto/sha256       → fingerprint machine-id
- encoding/json       → sérialisation des messages
- net/http            → connexion WebSocket (upgrade manuel ou golang.org/x/net/websocket si on accepte ce seul import x/)
- os                  → lecture machine-id, écriture clés
- time                → heartbeat, backoff
- log                 → logs structurés vers stdout (collectés par systemd)
```

Actions whitelist hardcodée dans le Worker :

```go
var ALLOWED_ACTIONS = map[string]bool{
    "GET_STATS":          true,
    "READ_LOGS":          true,
    "RESTART_CONTAINER":  true,
    "LIST_CONTAINERS":    true,
    "READ_CONFIG":        true,
    "LIST_SERVICES":      true,
}

func handleIntent(intent Intent) IntentResult {
    if !ALLOWED_ACTIONS[intent.Action] {
        return IntentResult{Error: "action not in whitelist"}
    }
    // dispatch
}
```

---

## Flux IA : Human-in-the-Loop

Le LLM ne touche jamais un Worker directement.

```text
Utilisateur tape une demande dans le ChatPanel
           ↓
Master reçoit → construit le contexte (état du node, métriques récentes)
           ↓
LLMClient.stream() → ChatPanel affiche la réponse en streaming
           ↓
Si une action est nécessaire :
StructuredLLM.create(ActionProposal) → objet Python typé et validé
           ↓
UI affiche la proposition :
┌──────────────────────────────────────────┐
│ 💡 Action proposée                       │
│ Action    : RESTART_CONTAINER            │
│ Container : nginx-prod                   │
│ Risque    : MEDIUM                       │
│ Raison    : "Le container répond 502..."│
│                                          │
│  [Approuver]          [Refuser]          │
└──────────────────────────────────────────┘
           ↓ (clic Approuver par un Operator ou Admin)
Master route l'Intent JSON au Worker via WSS
           ↓
Worker exécute (action dans sa whitelist)
           ↓
Résultat renvoyé au Master → Audit Trail signé
```

---

## Structure des Dossiers

```tree
vigile/
├── master/
│   ├── main.py                      # Point d'entrée FastAPI
│   ├── config.py                    # Settings depuis env vars
│   ├── core/
│   │   ├── security_manager.py      # JOIN_TOKEN, WORKER_TOKEN, Ed25519, JWT, RBAC
│   │   ├── node_manager.py          # États nodes, WebSockets actives, heartbeat
│   │   ├── plugin_manager.py        # Système de hooks natif + sandbox sous-processus
│   │   ├── plugin_worker.py         # Worker IPC sandbox (JSON-RPC, DB proxy)
│   │   ├── automation_engine.py     # Moteur d'automatisations (règles, triggers, actions)
│   │   ├── llm_client.py            # Client LLM universel (inspiré LiteLLM)
│   │   ├── structured_llm.py        # Structured outputs (inspiré Instructor)
│   │   └── rate_limiter.py          # Sliding window rate limiter
│   ├── api/
│   │   ├── nodes.py                 # POST /generate-join, GET /kickstart.sh, binaires
│   │   ├── chat.py                  # POST /chat (stream SSE), POST /chat/approve
│   │   ├── auth.py                  # POST /auth/login, /auth/refresh
│   │   ├── admin.py                 # Gestion users, révocation tokens, audit log
│   │   ├── automations.py           # CRUD règles d'automatisation
│   │   └── schemas/
│   │       ├── automations.py       # Schémas Pydantic automations
│   │       └── ...
│   ├── ws/
│   │   └── worker_handler.py        # WebSocket /ws/worker/join — enrollment + opérationnel
│   ├── plugins/
│   │   ├── docker_plugin.py         # Actions Docker (LIST_CONTAINERS, RESTART_CONTAINER)
│   │   ├── systemd_plugin.py        # Actions systemd (LIST_SERVICES, RESTART_SERVICE)
│   │   ├── metrics_plugin.py        # CPU, RAM, disque, uptime (cross-platform)
│   │   ├── clean_logs.py            # Proposition nettoyage logs obsolètes
│   │   ├── discord_alert.py         # Notification Discord
│   │   └── slack_alert.py           # Notification Slack
│   └── db/
│       ├── models.py                # Tables SQLite (nodes, tokens, users, audit, proposals, rules)
│       └── migrations.py            # Schema init + migrations
│
├── worker/
│   ├── main.go
│   ├── enrollment.go                # Génération Ed25519, handshake, stockage token
│   ├── connection.go                # WebSocket, reconnexion backoff, heartbeat
│   ├── dispatcher.go                # Whitelist + dispatch des intents
│   ├── discovery.go                 # Détection Docker, systemd, métriques OS
│   └── actions/
│       ├── stats.go
│       ├── logs.go
│       └── containers.go
│
├── frontend/
│   ├── src/
│   │   ├── pages/                   # 8 pages réelles (~2750 lignes)
│   │   │   ├── Dashboard.tsx         # Vue d'ensemble (Insights/Servers/Containers/Activity)
│   │   │   ├── LoginPage.tsx        # Authentification
│   │   │   ├── ServersPage.tsx      # Liste des serveurs
│   │   │   ├── NodeDetail.tsx       # Détail d'un nœud (métriques, logs, actions)
│   │   │   ├── ProposalsPage.tsx    # Propositions IA (approuver/rejeter)
│   │   │   ├── PluginsPage.tsx      # Catalogue des plugins
│   │   │   ├── AutomationsPage.tsx  # Règles d'automatisation (586 lignes)
│   │   │   └── SettingsPage.tsx      # Paramètres utilisateur
│   │   ├── components/              # Nombreux composants réutilisables
│   │   │   ├── dashboard/
│   │   │   ├── ui/
│   │   │   ├── automations/
│   │   │   ├── ChatPanel.tsx
│   │   │   └── ...
│   │   ├── hooks/                   # Hooks personnalisés (useApi, useDashboardData...)
│   │   ├── store/                   # Zustand stores (nodeStore, uiStore, insightsStore...)
│   │   ├── i18n/                    # Traductions français/anglais
│   │   └── lib/
│   │       ├── ws.ts                # Client WebSocket Master ↔ Frontend
│   │       └── sse.ts               # SSE reader pour le streaming LLM
│   └── ...
│
└── scripts/
    ├── ✅ kickstart.sh                 # Script universel d'installation Worker (servi dynamiquement par l'API)
    ├── ❌ build_worker.sh              # Cross-compile Go pour toutes les cibles (MANQUANT)
    ├── ❌ dev_setup.sh                 # Setup environnement de dev (MANQUANT)
    └── ✅ setup_test.sh                # Test stack Docker (existe mais non listé dans le plan original)
```

---

## Sprints

> **Légende :** ✅ = fait | ⚠️ = partiel | ❌ = manquant
>
> **Critères de test :** Les Sprints 7→17 doivent être validés selon les 5 niveaux de `RULES.md §8` avant de passer à l'étape suivante. Les critères spécifiques sont définis dans chaque sprint.

### Sprint 1 — Core Sécurisé et Enrollment ✅

- ✅ `SecurityManager` : JOIN_TOKEN HMAC, challenge Ed25519, WORKER_TOKEN avec cycle de vie
- ✅ `NodeManager` : registre des nodes, machine à états, dictionnaire WebSockets
- ✅ `PluginManager` : chargement dynamique, système de hooks
- ✅ API : `POST /api/nodes/generate-join`, `GET /api/nodes/kickstart.sh`, `GET /api/nodes/binary/{os}/{arch}/worker`
- ✅ WebSocket : `/ws/worker/join` — handshake complet enrollment + bascule opérationnel
- ✅ DB : schema SQLite complet (nodes, tokens, audit)
- ✅ Worker Go : enrollment Ed25519, heartbeat, reconnexion backoff, dispatcher whitelist

### Sprint 2 — Plugins OS et Métriques ✅ (100%)

- ✅ Plugin `metrics` : CPU, RAM, disque, uptime (cross-platform, sans dépendance)
- ✅ Plugin `docker` : list containers, restart, logs (si Docker détecté dynamiquement)
- ✅ Plugin `systemd` : list services, status, restart (si Linux)
- ✅ `kickstart.sh` complet : détection OS/arch, vérification SHA256, cascade installation
- ✅ API : `GET /api/nodes`, `GET /api/nodes/{id}/stats`, `GET /api/nodes/{id}/logs`

### Sprint 3 — Couche IA et Human-in-the-Loop ✅

- ✅ `LLMClient` natif : complete + stream SSE
- ✅ `StructuredLLM` : boucle retry + validation Pydantic
- ✅ Modèle `ActionProposal` : action, params, reasoning, risk_level
- ✅ API : `POST /api/chat` (stream), `POST /api/proposals/{id}/approve`, `POST /api/proposals/{id}/reject`
- ✅ Audit Trail : hash chaîné, stockage immuable

### Sprint 4 — Frontend React SPA ⚠️ (construit mais buggué)

**Ce qui est construit :**
- ✅ Application React standalone (vite + TailwindCSS + shadcn/ui) — 9 pages réelles, ~3000 lignes
- ✅ `CopilotPanel` (ChatPanel) : streaming SSE natif, historique de conversation
- ✅ `ProposalInline` / `ProposalCard` (ActionProposal) : carte d'approbation avec contexte et niveau de risque
- ✅ `NodeCard` / `NodeDetail` : état, métriques temps réel, logs
- ✅ Auth UI : login, gestion de session JWT
- ✅ `PluginsPage` : catalogue des plugins
- ✅ `AutomationsPage` : moteur d'automatisations (règles, déclencheurs, actions)
- ✅ `SettingsPage`, `ServersPage`, `Dashboard` avec sections Insight/Servers/Containers/Activity/Fleet

**Bugs connus (à corriger dans Sprint 7-8) :**
- ❌ CPU indique 0-1% au lieu de la valeur réelle
- ❌ Un seul disque visible au lieu de 3
- ❌ Erreur réseau "Request timed out" sur l'onglet Docker
- ❌ Badge de navigation affiche `(.)` au lieu du count
- ❌ Logs chargés en boucle infinie
- ❌ Surlignage des métriques au survol non fonctionnel
- ❌ Carte "État de la flotte" : le temps déborde de la carte
- ❌ Prédiction disque aberrante (+2145 Go/j)

### Sprint 5 — Plugin Ecosystem (Sandbox + Automations) ⚠️ (core OK, extension UI à venir)

**Ce qui est construit :**
- ✅ **Plugin isolation** : chaque plugin dans son propre sous-processus (sandbox) avec proxy DB transparent — `PluginProcessWrapper` + `plugin_worker.py` (JSON-RPC IPC, DB proxying) — **totalement réel**
- ✅ **Plugin Registry** : catalogue de plugins téléchargeables (endpoints API + fallback offline) — commit `8c220c6`
- ✅ **Moteur d'automatisations** : backend `automation_engine.py` + API `automations.py` + frontend `AutomationsPage.tsx` (586 lignes) — règles, déclencheurs, conditions, actions enum
- ✅ **Plugins existants** : docker, systemd, metrics, clean_logs, discord_alert, slack_alert — 6 plugins fonctionnels au format `register(pm)`
- ✅ **Plugin SDK** : documentation `docs/PLUGIN_SDK.md` + template
- ❌ **Format profond (dossier + manifest.json + pages auto-découvertes)** : n'existe pas — c'est le Sprint 9
- ❌ **Marketplace 1-clic depuis l'UI** : le catalogue frontend existe mais l'installation distale automatique n'est pas finalisée
- ❌ **Plugins avec pages dédiées** : tous les plugins sont des fichiers `.py` uniques, aucun n'a de composant React — c'est le Sprint 9-10

### Sprint 6 — Production Hardening ❌ (sauf rate limiter)

Le passage en production nécessite de verrouiller les limites du système et d'automatiser le cycle de vie des credentials.

> **Note** : Le rate limiter middleware + endpoint `/metrics` Prometheus sont les seules parties entamées (commit `3f9ae11`). Le reste est à zéro.

#### 1. Rate Limiting Multi-Niveaux (FastAPI Middleware) ⚠️
- ✅ **Sliding-window rate limiter** : Implémenté via `master/core/rate_limiter.py`, endpoints `/metrics` Prometheus opérationnels (commit `3f9ae11`).
- ❌ **Limites configurables via `settings`** : Les defaults (5/min login, 10/min script, 100/min API) ne sont pas encore branchés aux settings.

#### 2. Rotation Automatique des `WORKER_TOKEN`
- **Mécanisme** : Lors du heartbeat, si `rotation_due` (7 jours écoulés depuis `issued_at`), le Master génère un nouveau token et l'envoie dans une payload asynchrone :
  ```json
  { "type": "TOKEN_ROTATION_COMMAND", "new_worker_token": "JWT..." }
  ```
- **Validation** : Le Worker stocke le nouveau binaire de clé/token, recharge sa configuration, répond avec un message `TOKEN_ROTATION_ACK`, puis bascule sur le nouveau token. Le Master marque l'ancien token comme `revoked`.

#### 3. Mode Offline & Distribution Hermétique
- **Binaires préchargés** : Option `OFFLINE_MODE=true` dans `settings` forçant le Master à servir des binaires compilés localement sous `data/binaries/` au lieu de tenter un téléchargement distant.
- **Script `kickstart.sh` hors-ligne** : Support des certificats CA personnalisés pour les environnements d'entreprise isolés.

#### 4. Pipeline de Build Cross-Platform (`scripts/build_worker.sh`)
- Script Go de compilation croisée ciblant :
  - `GOOS=linux GOARCH=amd64` (Linux standard)
  - `GOOS=linux GOARCH=arm64` (Raspberry Pi 4/5, serveurs ARM)
  - `GOOS=darwin GOARCH=arm64` (macOS Apple Silicon)
  - `GOOS=freebsd GOARCH=amd64` (Homelabs TrueNAS Core)

#### 5. Métriques & Health Checks Master
- Point d'entrée `/metrics` exposant des métriques natives au format Prometheus :
  - `vigile_connected_workers_total` : Nombre de connexions WebSocket actives.
  - `vigile_proposals_pending_total` : Actions en attente d'approbation humaine.
  - `vigile_database_latency_seconds` : Temps de réponse des requêtes aiosqlite.

---
---

### Sprint 7 — Corrections Métriques et Fiabilité ✅

#### 1. Métriques CPU et Disque (Node Details)

- ✅ **CPU à 0-1% au lieu de 80%** : Corrigé — l'idle CPU additionnait le field index 0 au lieu du field index 4 (iowait). (`worker/stats.go`)
- ✅ **Un seul disque visible sur 3** : Corrigé — `MetricsSnapshot` expose maintenant `Disks []DiskMount` avec tous les points de montage collectés via `getLinuxDiskMetrics()`. (`worker/stats.go`)
- ✅ **« Disque plein dans moins d'un jour ! Taux de croissance de +2145.23 Go/jour »** : Corrigé — `DiskPredictionCard` utilise une régression linéaire avec seuil de confiance R² < 0.3. Prédictions à 1/6/24/48h. (`frontend/.../NodeDetailMetricsTab.tsx`)
- ✅ **Aucune info de version Worker** : Corrigé — `var Version` injecté par ldflags, envoyé dans HEARTBEAT et STATUS_REPORT, affiché dans `NodeDetailHeader`. (`worker/discovery.go`, `worker/connection.go`, `frontend/.../NodeDetailHeader.tsx`)

#### 2. Stabilité des Onglets et Requêtes

- ✅ **Erreur réseau « Request timed out »** : Corrigé — ajout de `timeoutMs: 30000` aux appels API services/containers, nettoyage des dépendances `useCallback`. (`frontend/src/hooks/useNodeDetailData.ts`)
- ✅ **Logs chargés en boucle infini** : Corrigé — remplacement des abonnements complets au store Zustand par des sélecteurs individuels, ajout de guards `loadingServices`/`loadingContainers` dans le `useEffect` de changement d'onglet. (`frontend/src/hooks/useNodeInsights.ts`, `frontend/src/pages/NodeDetail.tsx`)

### Sprint 8 — Rafraîchissement UI/UX ❌

#### 1. Corrections d'Affichage

- ❌ **Surlignage des métriques au survol** : L'effet hover sur les graphiques/tables de métriques est moche et non fonctionnel. À refaire avec un tooltip propre ou un highlight stylé (shadcn/ui Card + animation Tailwind).
- ❌ **Badge de navigation « Services (.) »** : Au lieu d'afficher « Services (24) », le badge affiche « Services (.) ». Problème de formatage ou d'état vide/NaN dans le compteur. Idem pour Docker. À corriger dans le composant Sidebar.
- ❌ **Carte « État de la flotte » débordée** : Le temps d'activité (ex: `4228462s`) dépasse les limites de la carte. Tronquer ou formater en jours/heures lisibles (ex: « 48 jours »).
- ❌ **Appliquer le logo Vigile partout** : Le logo Vigile (favicon, sidebar, login, topbar, pages) doit être systématiquement utilisé. Vérifier et remplacer : favicon, titre onglet, logo sidebar, logo page de connexion, branding dans les cartes et headers. (`frontend/src/components/ui/VigileLogo.tsx`)
- ❌ **Sidebar : ajouter un raccourci Docker** : Accès direct aux conteneurs Docker depuis la navigation latérale, sans passer par les détails d'un nœud.
- ❌ **Descriptions des plugins manquantes** : On ne sait pas à quoi sert chaque plugin. Ajouter un champ `description` dans les métadonnées et l'afficher dans le catalogue. (Prérequis UI avant le nouveau moteur — Sprint 10)
- ❌ **Toggle d'activation cassé** : Cocher un plugin désactivé affiche « Plugin désactivé » mais ne l'active pas. Corriger le flux activation/désactivation. (Prérequis UI avant le nouveau moteur — Sprint 10)
- ❌ **Pas de désinstallation possible** : Aucun bouton pour supprimer un plugin. Ajouter une action de désinstallation. (Prérequis UI avant le nouveau moteur — Sprint 10)

#### 2. Dashboard — Filtrage par Défaut

- ❌ **Afficher uniquement les conteneurs en échec par défaut** : Le dashboard montre tous les conteneurs, ce qui noie l'information. Comportement attendu : ne montrer que les conteneurs avec un statut autre que `running`/`healthy`, avec un toggle « Voir tout » en haut pour afficher l'intégralité.

#### 3. Registre d'Audit Cryptographique

- ✅ **Page supprimée** : La page « Registre d'Audit Cryptographique » et son entrée dans la topbar ont été retirées de l'UI (aucune route `/audit`, aucun composant `AuditPage`). L'audit reste accessible via l'endpoint API `GET /api/audit` et la vérification `GET /api/admin/audit-verify`.

#### 4. Nettoyage UX — Bruit et Hiérarchie

- ❌ **Cartes d'insight « NORMAL »** : Les cartes « CPU stable », « Mémoire stable » (severity=ok) polluent la section Insights et noient les vraies alertes (warning/critical). Masquer les statuts `ok` par défaut, n'afficher que warning+critical+offline, avec un toggle « Afficher les stables ».
- ❌ **Fil d'activité pollué par login/logout** : Les évènements de connexion/déconnexion des utilisateurs n'ont pas leur place dans le fil d'activité principal. Les filtrer ou les dédier à un onglet séparé.
- ❌ **Carrousels horizontaux qui cachent du contenu** : Les sections en carrousel (ex: serveurs, conteneurs) tronquent l'information. Si un élément ne tient pas dans la vue, il devient invisible sans scroll — ce qui rend les alertes critiques potentiellement hors-champ. Remplacer par une grille responsive ou un layout à défilement vertical avec indicateur de nombre total.

#### 5. Thème Warm Dark

- ❌ **Appliquer le thème Warm Dark confirmé** : Le thème actuel (Glass Dark Ops / teal / Inter) est à remplacer par le Warm Dark validé : fond `#0e0d0c`, accent orange `#E8650A`, titrage DM Serif Display. Vérifier la cohérence sur toutes les pages (modales, cartes, sidebar, formulaires).
- ❌ **Règle d'usage de l'orange** : `#E8650A` sert à la fois d'accent décoratif (boutons, titres) et d'alerte (warning, critique). Risque de confusion visuelle si un bouton orange "Nouveau conteneur" est perçu comme une alerte. Définir une règle d'usage : orange réservé aux alertes + actions critiques ; accents décoratifs sur une teinte dérivée (ex: `#F59E0B` amber plus doux) ou le blanc cassé.

### Sprint 9 — Moteur de Plugins — Core Engine ❌

> **Problème** : Le système actuel (`PluginManager` avec hooks et sandbox sous-processus) permet aux plugins
> de réagir à des évènements et de s'isoler, mais ils n'ont aucune notion d'UI, de page dédiée, de stockage
> persistant autonome, ou de configuration structurée. C'est un système de scripts hookables, pas un
> vrai moteur de plugins.
>
> **Objectif du Sprint 9** : Construire le cœur du nouveau moteur — `PluginEngine` avec scanner,
> lifecycle manager, registre, bus d'évènements, DB auto, et scheduler. Remplacer le `PluginManager`
> actuel tout en gardant la compatibilité avec les plugins existants.
>
> Voir aussi Sprint 10 (intégration frontend) et Sprint 11 (marketplace).
>
> Inspiration : **Jeedom** — chaque plugin est un mini-module autonome.

---

#### 1. Cahier des Charges Fonctionnel

| Capacité | Exemple concret | Aujourd'hui | Demain |
|---|---|---|---|
| **Avoir sa propre page** | Docker → page "Conteneurs" liste + statuts + actions | ❌ hooks only | ✅ Page dédiée dans la sidebar |
| **Avoir ses propres routes API** | `/api/plugins/docker/containers/{id}/logs` | ❌ | ✅ Auto-montées par le moteur |
| **Stocker ses données** | Sauvegarder préférences, historique, cache | ❌ rien | ✅ Tables SQL auto-créées + KV store |
| **Avoir sa configuration** | Configurer socket Docker, timeout, options | ❌ | ✅ Formulaires générés depuis un schéma JSON |
| **Ajouter des widgets au dashboard** | Widget "Docker Stats" sur la page d'accueil | ❌ | ✅ Panels injectables |
| **Étendre le Copilot IA** | Le LLM connaît les actions du plugin et les propose | ❌ | ✅ Actions déclarées dans le manifest |
| **Réagir aux évènements système** | Déclencher une action quand un nœud se connecte | ✅ hooks basiques | ✅ Hooks enrichis + scheduler CRON |
| **Tâches planifiées** | Nettoyage automatique toutes les heures | ❌ | ✅ Scheduler interne (intervalle, CRON) |
| **Dépendre d'un autre plugin** | Plugin `nginx` dépend du plugin `docker` | ❌ | ✅ Dépendances déclaratives |
| **S'installer/désinstaller proprement** | Créer ses tables à l'install, les détruire à la désinstall | ❌ copie fichier | ✅ Cycle de vie complet géré |
| **Se mettre à jour** | Nouvelle version dispo → notification 1-clic | ❌ | ✅ Détection de version intégrée |
| **S'exécuter isolé** | Pas d'accès aux données des autres plugins | ❌ pas d'isolation | ✅ Routes/DB/UI isolées par plugin |

---

#### 2. Architecture du Moteur

Le `PluginManager` actuel est remplacé par un **`PluginEngine`** qui gère le cycle de vie complet,
la découverte, l'isolation et l'intégration automatique dans l'UI.

```
 ┌─────────────────────────────────────────────────────────────────┐
 │                        PluginEngine                            │
 │                                                                 │
 │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
 │  │   Scanner    │  │   Registry   │  │   Lifecycle Manager  │  │
 │  │              │  │              │  │                      │  │
 │  │ Watche le    │  │ Catalogue    │  │ install → activate   │  │
 │  │ dossier      │  │ des plugins  │  │ → configure → run    │  │
 │  │ plugins/     │  │ installés    │  │ → deactivate →       │  │
 │  │ (hot-reload) │  │ en DB        │  │   uninstall          │  │
 │  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
 │         │                │                     │              │
 │  ┌──────┴────────────────┴─────────────────────┴───────────┐  │
 │  │                Plugin Dispatcher                         │  │
 │  │  RouteRegistrar  │  PageRegistry  │  HookBus  │  DBAuto  │  │
 │  │  Monte les routes│  Injecte les   │  Distribue│  Crée les │  │
 │  │  API du plugin   │  pages dans le │  les hooks│  tables du │  │
 │  │  sous /api/...   │  routeur React │  système  │  manifest  │  │
 │  └──────────────────┴───────────────┴───────────┴────────────┘  │
 └─────────────────────────────────────────────────────────────────┘
```

**Composants clés du moteur :**

- **`Scanner`** : au démarrage du master, scanne `master/plugins/` à la recherche de dossiers avec
  `manifest.json`. Puis watcher en temps réel (inotify) pour détecter ajouts, modifications, suppressions.
  Hot-reload : un plugin modifié est rechargé sans redémarrer le master.

- **`Registry`** : table SQL `plugin_registry` qui stocke l'ID, la version, le statut (decouvert/installed/
  active/running/deactivated), la configuration courante de chaque plugin. C'est la source de vérité.
  Le frontend l'interroge avec `GET /api/plugins` pour afficher le catalogue.

- **`LifecycleManager`** : machine à états qui gère les transitions. Chaque transition exécute les
  callbacks associés (`on_install` → crée les tables, `on_activate` → monte les routes + injecte
  les pages, `on_uninstall` → supprime les tables + fichiers).

- **`RouteRegistrar`** : inspecte les routes déclarées dans `manifest.json.routes` ou via les
  décorateurs `@plugin.route()`, et les monte dynamiquement dans FastAPI sous `/api/plugins/{id}/...`.
  Check RBAC à l'exécution. Un plugin A ne peut pas appeler les routes d'un plugin B sans dépendance.

- **`PageRegistry`** : expose `GET /api/plugins/pages` qui retourne la liste de toutes les pages
  déclarées par les plugins activés. Le frontend appelle cet endpoint au démarrage et injecte les
  pages dans le routeur React (via `React.lazy` + dynamic imports). Les entrées avec `sidebar: true`
  apparaissent automatiquement dans le menu latéral.

- **`HookBus`** : bus d'évènements asynchrone. Remplace les hooks synchrones du `PluginManager` actuel.
  Évènements disponibles : `on_heartbeat`, `on_intent_result`, `on_node_connect`, `on_node_disconnect`,
  `on_proposal_approved`, `on_proposal_rejected`, `on_plugin_installed`, `on_plugin_activated`,
  `on_cron_minute`, `on_cron_hour`, `on_cron_day`, `on_config_changed`.

- **`DBAuto`** : lit `manifest.json.database.tables`, exécute `CREATE TABLE IF NOT EXISTS` à l'activation,
  et `DROP TABLE` à la désinstallation. Les plugins n'écrivent jamais de SQL brut — ils utilisent des
  helpers fournis par `PluginBase.db` (type ORM léger).

- **`Scheduler`** : lit `manifest.json.scheduler.tasks` et planifie les tâches avec `asyncio`.
  Supporte les intervalles en secondes, minutes, heures, et les expressions CRON.

**Transitions d'état (machine à états) :**

```text
       ┌──────────┐
       │ DECOUVERT│ ← Scanner trouve le dossier, valide le manifest
       └────┬─────┘
            ↓ (on_install)
       ┌──────────┐
       │ INSTALLED│ → CREATE TABLE, init config defaults, copie les assets frontend
       └────┬─────┘
            ↓ (on_activate)
       ┌──────────┐
       │ ACTIVE   │ → monte les routes FastAPI, injecte les pages React,
       └────┬─────┘   abonne les hooks, démarre le scheduler
            ↓
       ┌──────────┐
       │ RUNNING  │ ← vie normale du plugin
       └────┬─────┘
            ↓ (on_deactivate)
       ┌──────────┐
       │DEACTIVATE│ → démonte les routes, désabonne les hooks,
       └────┬─────┘   cache les pages, arrête le scheduler
            ↓ (on_uninstall)
       ┌──────────┐
       │UNINSTALL │ → DROP TABLE, supprime les fichiers du dossier plugins/
       └──────────┘
```

---

#### 3. Structure d'un Plugin

Un plugin est un **dossier** dans `master/plugins/`. Le moteur découvre tout automatiquement —
pas besoin d'enregistrer quoi que ce soit dans le code du core.

```
master/plugins/docker/
├── manifest.json              ← Métadonnées + déclarations (OBLIGATOIRE)
├── __init__.py                 ← Code backend (optionnel si plugin purement déclaratif)
├── config/
│   └── default_config.json     ← Configuration par défaut (optionnel)
└── frontend/                   ← Code frontend React (optionnel)
    ├── pages/                  ← Pages découvertes automatiquement par PageRegistry
    │   ├── Containers.tsx
    │   └── ContainerDetail.tsx
    ├── widgets/                ← Widgets injectables dans le dashboard
    │   └── DockerStats.tsx
    └── assets/
        └── icon.svg
```

---

#### 4. Le manifest.json en Détail

C'est le fichier le plus important. Il déclare tout ce que le plugin peut faire.

```json
{
  "id": "docker",
  "name": "Docker Manager",
  "version": "1.0.0",
  "author": "Vigile",
  "icon": "docker",
  "category": "containers",
  "description": {
    "short": "Gestion complète des conteneurs Docker",
    "full": "Permet de lister, inspecter, démarrer, arrêter et redémarrer les conteneurs Docker\nsur chaque nœud de la flotte. Ajoute une page dédiée avec streaming logs,\nfiltres et actions en un clic."
  },
  "license": "MIT",
  "min_master_version": "2.0.0",

  "pages": [
    {
      "id": "containers",
      "title": "Conteneurs",
      "icon": "docker",
      "sidebar": true,
      "component": "Containers",
      "roles": ["admin", "operator"]
    },
    {
      "id": "container-detail",
      "title": "Détails du conteneur",
      "sidebar": false,
      "component": "ContainerDetail",
      "params": ["container_id"],
      "roles": ["admin", "operator"]
    }
  ],

  "widgets": [
    {
      "id": "docker-stats",
      "title": "Statistiques Docker",
      "component": "DockerStats",
      "sizes": ["small", "medium"],
      "roles": ["viewer", "operator", "admin"]
    }
  ],

  "routes": [
    {
      "path": "/containers",
      "method": "GET",
      "handler": "list_containers",
      "roles": ["admin", "operator", "viewer"]
    },
    {
      "path": "/containers/{id}/logs",
      "method": "GET",
      "handler": "stream_container_logs",
      "roles": ["admin", "operator"]
    },
    {
      "path": "/containers/{id}/start",
      "method": "POST",
      "handler": "start_container",
      "roles": ["admin", "operator"]
    },
    {
      "path": "/containers/{id}/stop",
      "method": "POST",
      "handler": "stop_container",
      "roles": ["admin", "operator"]
    },
    {
      "path": "/containers/{id}/restart",
      "method": "POST",
      "handler": "restart_container",
      "roles": ["admin", "operator"]
    }
  ],

  "hooks": [
    "on_node_connected",
    "on_intent_result"
  ],

  "database": {
    "tables": [
      {
        "name": "docker_container_cache",
        "columns": [
          {"name": "id", "type": "TEXT PRIMARY KEY"},
          {"name": "node_id", "type": "TEXT NOT NULL"},
          {"name": "name", "type": "TEXT NOT NULL"},
          {"name": "status", "type": "TEXT"},
          {"name": "image", "type": "TEXT"},
          {"name": "ports", "type": "TEXT"},
          {"name": "cached_at", "type": "DATETIME DEFAULT CURRENT_TIMESTAMP"}
        ]
      }
    ]
  },

  "config_schema": {
    "type": "object",
    "properties": {
      "docker_socket": {
        "type": "string",
        "title": "Chemin du socket Docker",
        "default": "/var/run/docker.sock",
        "description": "Chemin vers le socket Unix de Docker sur chaque nœud"
      },
      "refresh_interval": {
        "type": "integer",
        "title": "Intervalle de rafraîchissement (s)",
        "default": 30,
        "minimum": 5,
        "maximum": 300
      }
    },
    "required": ["docker_socket"]
  },

  "dependencies": {
    "plugins": [],
    "extras": []
  },

  "copilot_actions": [
    {
      "action": "LIST_CONTAINERS",
      "description": "Liste tous les conteneurs Docker sur un nœud",
      "risk_level": "LOW",
      "params_schema": {
        "type": "object",
        "properties": {
          "node_id": {"type": "string", "description": "ID du nœud cible"},
          "filter": {"type": "string", "enum": ["all", "running", "stopped"]}
        },
        "required": ["node_id"]
      }
    },
    {
      "action": "RESTART_CONTAINER",
      "description": "Redémarre un conteneur Docker",
      "risk_level": "MEDIUM",
      "params_schema": {
        "type": "object",
        "properties": {
          "node_id": {"type": "string"},
          "container_id": {"type": "string"}
        },
        "required": ["node_id", "container_id"]
      }
    }
  ],

  "scheduler": {
    "tasks": [
      {
        "id": "refresh_cache",
        "interval": 60,
        "handler": "refresh_container_cache"
      }
    ]
  }
}
```

**Ce que le moteur fait automatiquement avec ce manifest :**

1. 🔍 **Scanner** détecte le dossier `docker/` au démarrage, lit et valide le manifest
2. 📦 **Installation** : crée la table `docker_container_cache`, écrit la config par défaut
3. 🚀 **Activation** : monte les 5 routes dans FastAPI, injecte les pages dans le routeur React
4. 🖼️ **Sidebar** : l'entrée "Conteneurs" avec l'icône Docker apparaît automatiquement dans le menu
5. 🔌 **Hooks** : le plugin reçoit `on_node_connected` et `on_intent_result`
6. ⚙️ **Config UI** : l'interface génère un formulaire interactif depuis `config_schema`
7. 🤖 **Copilot** : le LLM connaît `LIST_CONTAINERS` et `RESTART_CONTAINER` — peut les proposer dans le chat
8. ⏰ **Scheduler** : toutes les 60s, `refresh_container_cache()` est appelé automatiquement

---

### Sprint 10 — Moteur de Plugins — Intégration Frontend ❌

> Construire l'interface entre le moteur de plugins et le frontend React : découverte automatique des pages,
> injection dans le routeur, SDK pour écrire des plugins en quelques lignes, et exemples concrets
> (Docker avec page dédiée, Systemd, Metrics, Notifications).
>
> Prérequis : Sprint 9 (Core Engine) doit être fonctionnel.

---

#### 1. Fonctionnement Côté Frontend (Injection Transparente)

Le frontend n'a pas besoin d'être recompilé pour ajouter un plugin. Tout est dynamique.

**Au démarrage de l'app React :**
1. Appel à `GET /api/plugins/pages` → reçoit la liste de toutes les pages des plugins activés
2. Pour chaque page avec `sidebar: true`, le composant `Sidebar` ajoute une entrée dans le menu
3. Le routeur React enregistre les routes dynamiquement via `React.lazy(() => import(...))`
4. Les imports pointent vers `frontend/plugins/<plugin_id>/pages/<component>.tsx`

**PluginAPI (sandbox frontend) :**
Chaque page de plugin reçoit une API restreinte en props, pas d'accès direct au store global :

```tsx
// frontend/plugins/docker/pages/Containers.tsx
// Aucune importation manuelle nécessaire — découverte automatique
import { PluginPage, PluginAPI } from '@vigile/plugin-sdk'

export default function DockerContainers({ api }: { api: PluginAPI }) {
  const [containers, setContainers] = useState([])

  useEffect(() => {
    // L'API préfixe automatiquement vers /api/plugins/docker/...
    api.fetch('/containers').then(setContainers)
  }, [])

  return (
    <div>
      <h1>🐳 Conteneurs Docker</h1>
      <Button onClick={() => api.fetch('/containers', { method: 'POST' })}>
        Rafraîchir
      </Button>
      <ContainerTable containers={containers} />
    </div>
  )
}
```

---

#### 2. SDK — Écrire un Plugin en Quelques Lignes

Le SDK fournit tout ce qu'il faut pour qu'un plugin simple tienne dans un seul fichier.

**Plugin minimal (10 lignes, backend uniquement) :**

```python
# master/plugins/disk_cleaner/__init__.py
from core.plugin_engine import PluginBase, hook

class DiskCleanerPlugin(PluginBase):
    id = "disk_cleaner"
    name = "Disk Cleaner"
    description = "Suggère des nettoyages disque automatiques"

    @hook("on_cron_hour")
    async def check_disk(self, timestamp: int):
        nodes = await self.api.get_connected_nodes()
        for node in nodes:
            stats = await self.api.get_node_stats(node.id)
            if stats.disk.usage_pct > 85:
                await self.api.create_proposal(
                    action="CLEAN_DISK",
                    target=node.id,
                    reasoning=f"Disk at {stats.disk.usage_pct}%",
                    risk_level="LOW"
                )
```

**Plugin avec page et configuration (30 lignes) :**

```python
# master/plugins/weather/__init__.py
from core.plugin_engine import PluginBase, route, page

class WeatherPlugin(PluginBase):
    id = "weather"
    name = "Weather Monitor"
    description = "Affiche la météo pour chaque nœud"

    @route("/current")
    async def get_current(self, request):
        lat = self.config.get("latitude", 48.85)
        lon = self.config.get("longitude", 2.35)
        return await self.api.http_get(
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}&current_weather=true"
        )

    @page("Météo", icon="cloud-sun", sidebar=True,
          roles=["viewer", "operator", "admin"])
    def weather_page(self):
        return {"component": "WeatherWidget"}
```

---

#### 3. Exemple Concret : Plugin Docker Nouvelle Génération

Le plugin Docker actuel (un hook `handle_intent` qui wrapper un appel Worker) devient un **plugin
complet avec page dédiée** :

- **Page `Conteneurs`** dans la sidebar : liste tous les conteneurs de tous les nœuds
- **Tableau interactif** : nom, image, statut (couleur), ports, uptime, CPU/MEM
- **Actions en 1 clic** : ▶️ Start / ⏹️ Stop / 🔄 Restart / ⏸️ Pause
- **Page détail** : logs en streaming (WebSocket), inspection JSON, stats live
- **Filtres** : running / stopped / failed / all + recherche textuelle
- **Multi-nœuds** : switch pour voir les conteneurs d'un nœud spécifique ou tous
- **Cache local** : table `docker_container_cache` pour éviter de requêter le Worker à chaque vue
- **Scheduler** : refresh automatique du cache toutes les 60s
- **Copilot** : propose `RESTART_CONTAINER` avec `container_id` + `node_id` validés

---

#### 4. Exemple Concret : Plugin Systemd

- **Page `Services`** dans la sidebar : liste tous les services systemd de tous les nœuds
- **Filtres** : active / inactive / failed / enabled / disabled
- **Actions** : restart / start / stop / enable / disable / status
- **Recherche** par nom de service
- **Logs** : `journalctl -u <service>` en streaming WebSocket

---

#### 5. Exemple Concret : Plugin Metrics Avancé

- **Widget dashboard** : mini-graphiques CPU/RAM/DISK par nœud
- **Page dédiée** : historique des métriques avec line charts (Chart.js ou Recharts)
- **Alertes** : seuils configurables CPU/RAM/DISK avec notification in-app
- **Export** : endpoint Prometheus ou JSON

---

#### 6. Exemple Concret : Plugin Notifications

- **Widget** dans la topbar : cloche avec compteur de notifications non lues
- **Canaux** : Web in-app, email, Discord, Slack, Telegram (un sous-module par canal)
- **Déclencheurs** : seuils métriques, statut nœud, erreurs plugins
- **Configuration** : formulaire pour chaque canal (webhook URL, token, etc.)

---

### Sprint 11 — Moteur de Plugins — Marketplace ❌

> Interface de distribution, installation et mise à jour des plugins. Repose sur le Core Engine
> (Sprint 9) et l'intégration frontend (Sprint 10).
>
> Prérequis : Sprints 9 et 10.

---

#### 1. Marketplace et Distribution

**Intégré dans l'application — pas de site externe obligatoire :**

- **Onglet « Catalogue »** dans la page Plugins : liste des plugins disponibles à l'installation
- **Dépôt officiel** : registre GitHub `vigile/plugin-registry` avec plugins validés par la communauté
- **Dépôt custom** : possibilité d'ajouter une URL de registre tiers dans les paramètres
- **Installation 1 clic** : « Installer » → télécharge le ZIP → décompresse dans `master/plugins/`
  → installe les dépendances → active le plugin
- **Mises à jour** : badge dans l'UI quand une MAJ est disponible, installation en 1 clic
- **Stats** : nombre d'installations, note, compatibilité master

**Exemple de réponse du registre :**

```json
{
  "registry_url": "https://registry.vigile.dev",
  "plugins": [{
    "id": "docker",
    "name": "Docker Manager",
    "version": "1.0.0",
    "author": "Vigile",
    "download_url": "https://registry.vigile.dev/plugins/docker/v1.0.0/plugin.zip",
    "sha256": "abc123...",
    "min_master_version": "2.0.0",
    "category": "containers",
    "downloads": 1520,
    "rating": 4.5
  }]
}
```

---

#### 2. Sécurité et Isolation

- **Routes isolées** : chaque plugin sous `/api/plugins/{id}/`. Pas d'accès aux routes d'un autre
  plugin sans dépendance déclarée.
- **DB isolée** : préfixe de table par plugin (`docker_container_cache`). Aucun accès aux tables
  du core ni des autres plugins.
- **Frontend isolé** : les composants reçoivent une `PluginAPI` restreinte. Pas d'accès au store
  global, pas de `fetch` direct — seulement via le bridge API.
- **RBAC** : chaque page, route et widget déclare les rôles autorisés. Vérifié à l'exécution.
- **Sandbox** : plugins first-party chargés directement dans le process master. Plugins tiers
  optionnellement isolés dans un sous-processus avec communication IPC.
- **Pas de exec()** : un plugin ne peut PAS exécuter de code arbitraire sur le master. Les actions
  Docker/systemd passent par le Worker (whitelist). Un plugin peut seulement faire des appels API,
  lire/écrire dans ses propres tables, et envoyer des intents au Worker.

---

#### 3. Migration depuis l'Ancien Système

1. Le `PluginManager` actuel et ses hooks synchrones sont dépréciés
2. Les 3 plugins existants (docker, systemd, metrics) sont réécrits dans la nouvelle architecture
3. Pendant la transition, le `PluginEngine` bridge les anciens plugins hook-only vers le `HookBus`
4. Une fois la migration validée, l'ancien `PluginManager` est supprimé

### Sprint 12 — Propositions IA, Configuration et Chat IA ❌

#### 1. Propositions IA — Qualité et Pertinence

- ❌ **Estimation du gain dans les propositions** : Au lieu de « Proposed deletion of rotated/archived logs to free up space », la proposition doit chiffrer le gain attendu : « Supprimer 2.3 Go de logs obsolètes pour libérer ~3 jours de stockage » (ou l'équivalent). Calculer l'espace récupérable avant de formuler la proposition.
- ❌ **Cohérence linguistique** : Toute l'interface est en français (confirmé). Les propositions IA doivent suivre la même règle — pas d'anglais mélangé.

#### 2. Page Paramètres

- ❌ **Changement de nom d'utilisateur et logo** : Impossible de modifier le nom d'utilisateur ou le logo de l'instance. Ajouter des champs d'édition et les endpoints API associés.
- ❌ **Supprimer « Mode démo DÉSACTIVÉ »** : Cette information est inutile dans l'interface. La retirer.
- ❌ **« Configuration Master » doit être admin-only** : Vérifier que la section Configuration Master est masquée pour les rôles non-admin (Viewer, Operator).

#### 3. Chat IA — Réarchitecture Complète

- ❌ **Intégration trop simpliste** : Le chat IA actuel est une intégration basique sans contexte réel, sans mémoire de conversation, sans streaming fiable et sans propositions actionnables correctes. Tout refaire :
  - Contexte enrichi (état des nœuds, métriques récentes, historique des actions)
  - Streaming SSE robuste avec reconnexion
  - Mémoire de session persistante
  - Génération de propositions ActionProposal valides
  - Gestion des erreurs et fallback Ollama/local
  - UI repensée (messages, suggestions, états vides/chargement/erreur)

---

## Vision Long Terme — Système Autonome Dirigé par l'IA

Le chemin vers un système entièrement autonome où l'IA gère les opérations courantes et n'escalade que l'inconnu.

> ⚠️ **Sprints 13-17** : Vision lointaine, pas prioritaire. Ne pas détailler tant que les besoins réels ne sont pas validés par l'usage des Sprints 7-12.

### Sprint 13 — Autonomie Graduée

L'IA passe d'un rôle d'assistant passif à un rôle d'acteur régulé, avec trois niveaux d'autonomie paramétrables.

#### 1. Niveaux de Confiance et Approbation
- **`AUTO_RISK`** : Actions d'observation ou de maintenance mineure. Sous réserve de validation explicite dans `RULES.md` — le Human-in-the-Loop est un pilier fondateur.
- **`MEDIUM_RISK`** : Actions modifiant des ressources non-critiques. Notification SSE/WebSocket dans l'UI avec possibilité d'annulation sous 10 secondes.
- **`HIGH_RISK`** : Actions affectant l'infrastructure globale ou le réseau. Requiert double validation explicite.

#### 2. Profiling Comportemental & Apprentissage
- Stockage de l'historique des interactions dans la table `confidence_history`.
- Score d'évaluation dynamique réajustant le niveau de risque selon le ratio d'acceptation humain.

> **Note** : Toute déviation du Human-in-the-Loop (ex: `AUTO_RISK` sans validation) doit être explicitement documentée et justifiée. Voir `RULES.md` §13.

---

### Sprint 14 — Détection Proactive

Le système n'attend pas la panne. Surveillance continue, signaux faibles.

- Calcul automatique de baselines (EMA) sur CPU/RAM/Load
- Log scanner intelligent sur le Worker (expressions régulières configurables)
- Prédiction de saturation de disque (extrapolation linéaire)

---

### Sprint 15 — Runbooks & Auto-Healing

Codification des diagnostics IA sous forme de graphes d'actions conditionnels (YAML en DB).

- Moteur de runbooks avec conditions, délais, cascades
- Rollback automatique en cas d'échec (sous réserve de validation)

---

### Sprint 16 — Coordination Multi-Nœuds

L'IA gère la topologie de l'infrastructure globale.

- Graphe de dépendances automatique (connexions réseau entre services)
- Déploiement gradué (canary) sur un nœud avant propagation

---

### Sprint 17 — Apprentissage & Mémoire

L'IA tire parti de l'expérience opérationnelle passée.

- Indexation des incidents résolus (SQLite FTS5 uniquement — pas de base vectorielle, zéro dépendance supplémentaire)
- Mémoire conversationnelle par nœud

---

## Ce qu'on ne construira jamais

- Pas de shell interactif. Jamais.
- Pas d'exécution de commande arbitraire. Whitelist hardcodée, point final.
- Pas de connexion sortante du Master vers les Workers (zéro SSH, zéro push).
- Pas de dépendance à un cloud provider (AWS, GCP, Azure).
- Pas de compte obligatoire chez un tiers pour fonctionner.

Le produit fonctionne entièrement en self-hosted, sur un Raspberry Pi si nécessaire.
