# Vigile — Plan Technique

> Fleet Manager intelligent pour serveurs et homelabs.
> Zero-Trust. Zéro Dépendance Tierce sur le Core. Zéro SSH.
> Vision long terme : système autonome dirigé par l'IA (Sprints 7→11).

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
│   ├── main.py
│   ├── config.py                    # Settings depuis env vars
│   ├── core/
│   │   ├── security_manager.py      # JOIN_TOKEN, WORKER_TOKEN, Ed25519, JWT, RBAC
│   │   ├── node_manager.py          # États nodes, WebSockets actives, heartbeat
│   │   ├── plugin_manager.py        # Système de hooks natif (inspiré Pluggy)
│   │   ├── llm_client.py            # Client LLM universel (inspiré LiteLLM)
│   │   └── structured_llm.py        # Structured outputs (inspiré Instructor)
│   ├── api/
│   │   ├── nodes.py                 # POST /generate-join, GET /kickstart.sh, binaires
│   │   ├── chat.py                  # POST /chat (stream SSE), POST /chat/approve
│   │   ├── auth.py                  # POST /auth/login, /auth/refresh
│   │   └── admin.py                 # Gestion users, révocation tokens, audit log
│   ├── ws/
│   │   └── worker_handler.py        # WebSocket /ws/worker/join — enrollment + opérationnel
│   ├── plugins/
│   │   ├── docker_plugin.py         # Actions Docker (si Docker détecté)
│   │   ├── systemd_plugin.py        # Actions systemd (si Linux)
│   │   └── metrics_plugin.py        # CPU, RAM, disque (cross-platform)
│   └── db/
│       ├── models.py                # Tables SQLite (nodes, tokens, users, audit, proposals)
│       └── migrations.py            # Schema init
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
│   │   ├── components/
│   │   │   ├── ChatPanel.tsx        # Chat streaming (inspiré Open WebUI)
│   │   │   ├── ActionProposal.tsx   # Carte d'approbation Human-in-the-Loop
│   │   │   ├── NodeCard.tsx         # État d'un node + métriques
│   │   │   ├── LogViewer.tsx        # Terminal lecture seule (Xterm.js natif)
│   │   │   └── AuditLog.tsx         # Trail immuable
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

### Sprint 4 — Frontend ✅

- ✅ Application React standalone (vite + TailwindCSS + shadcn/ui)
- ✅ `CopilotPanel` (ChatPanel) : streaming SSE natif, historique de conversation
- ✅ `ProposalInline` / `ProposalCard` (ActionProposal) : carte d'approbation avec contexte et niveau de risque
- ✅ `NodeCard` : état, métriques temps réel, logs
- ✅ `NodeDetailLogsTab` (LogViewer) : terminal lecture seule, WebSocket streaming
- ✅ `AuditPage` (AuditLog) : timeline des actions approuvées
- ✅ Auth UI : login, gestion de session JWT
- ✅ **Plugin Catalogue** : page d'accueil des plugins disponibles avec installation en 1 clic

### Sprint 5 — Plugin Ecosystem (Home Assistant-like) ✅ (100%)

- ✅ **Format de plugin standardisé** : métadonnées, dépendances, hooks, configuration
- ✅ **Plugin Registry** : catalogue de plugins téléchargeables (GitHub / registre local) — endpoints API et fallback résilient hors-ligne validés
- ✅ **Installation frontend** : browse, install, activate, configure depuis l'UI
- ✅ **Plugin isolation** : chaque plugin dans son propre sous-processus (sandbox) avec proxy DB transparent
- ✅ **Moteur d'automatisations** : déclencheur (trigger) → conditions (conditions) → actions
  - Triggers : heartbeat, STATUS_REPORT, INTENT_RESULT, timer, webhook
  - Conditions : métrique > seuil, service down, log match, time window
  - Actions : intent Worker, webhook, notification, logs
- ✅ **Plugin SDK** : documentation + template pour créer des plugins tiers (`docs/PLUGIN_SDK.md`)
- ✅ Exemples de plugins : Discord Alert, Slack Alert, Clean Logs (propositions de nettoyage de disque)

### Sprint 6 — Production Hardening ⚠️

Le passage en production nécessite de verrouiller les limites du système et d'automatiser le cycle de vie des credentials.

#### 1. Rate Limiting Multi-Niveaux (FastAPI Middleware)
- **Middleware IP & Token** : Limitation du nombre de requêtes à l'aide d'un algorithme de *sliding-window* stocké en mémoire locale (avec option d'extension Redis).
- **Limites configurables via `settings`** :
  - Authentification (`/api/auth/login`) : max 5 requêtes par minute par IP.
  - Endpoints de script (`/api/nodes/kickstart.sh`) : max 10 requêtes par minute par IP.
  - API de contrôle des Workers : max 100 requêtes par minute par utilisateur.

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

## Vision Long Terme — Système Autonome Dirigé par l'IA

Le chemin vers un système entièrement autonome où l'IA gère les opérations courantes et n'escalade que l'inconnu.

### Sprint 7 — Autonomie Graduée

L'IA passe d'un rôle d'assistant passif à un rôle d'acteur régulé, avec trois niveaux d'autonomie paramétrables.

#### 1. Niveaux de Confiance et Approbation
- **`LOW_RISK`** : Actions d'observation ou de maintenance mineure (ex: `GET_STATS`, nettoyage temporaire). Exécution automatique immédiate sans intervention humaine.
- **`MEDIUM_RISK`** : Actions modifiant des ressources non-critiques (ex: restart d'un container de dev, vidage de cache). Notification SSE/WebSocket instantanée dans l'UI avec possibilité d'annulation sous 10 secondes.
- **`HIGH_RISK`** : Actions affectant l'infrastructure globale ou le réseau (ex: reboot de node, restart de service systemd critique). Requiert une double validation explicite par un Admin ou Operator.

#### 2. Profiling Comportemental & Apprentissage
- Stockage de l'historique des interactions avec les propositions dans la table `confidence_history` :
  ```sql
  CREATE TABLE confidence_history (
      id TEXT PRIMARY KEY,
      action_type TEXT NOT NULL,
      confidence_score REAL NOT NULL,
      human_decision TEXT NOT NULL, -- APPROVED, REJECTED, AUTO_EXECUTED
      decided_at REAL NOT NULL,
      feedback_text TEXT
  );
  ```
- Un score d'évaluation dynamique réajuste le niveau de risque d'un type d'action selon le ratio d'acceptation de l'utilisateur (ex: si l'administrateur rejette systématiquement le nettoyage de disque automatique, l'action bascule de `LOW_RISK` à `HIGH_RISK`).

---

### Sprint 8 — Détection Proactive

Le système n'attend pas la panne pour proposer des remédiations. Il surveille en continu et extrait des signaux faibles.

#### 1. Calcul Automatique des Baselines (EMA & Anomaly Detection)
- Utilisation de moyennes mobiles exponentielles (EMA) locales sur les rapports de métriques (CPU, RAM, Load) :
  $$\text{Baseline}_{t} = \alpha \times \text{Metric}_{t} + (1 - \alpha) \times \text{Baseline}_{t-1}$$
- En cas de déviation majeure (> 3 écarts-types) pendant plus de 5 minutes, une proposition d'investigation est générée de manière proactive.

#### 2. Log Scanner Intelligent sur le Worker
- Le Worker Go intègre un scanner de fichier de logs léger en streaming avec correspondance d'expressions régulières (configuré dynamiquement par le Master).
- En cas de détection de patterns comme `FATAL`, `OutOfMemoryError` ou `Connection reset by peer`, le Worker lève immédiatement un évènement `LOG_PATTERN_MATCHED` vers le Master, qui lance une analyse contextuelle avec l'IA.

#### 3. Prédiction de Saturation de Disque
- Modèle linéaire d'extrapolations temporelles sur le disque dur. L'IA avertit l'utilisateur : *"Le disque dur de node-1 sera saturé dans 48h au rythme actuel d'écriture (12 Go/jour)."* et propose une action de nettoyage ciblée.

---

### Sprint 9 — Runbooks & Auto-Healing

Les diagnostics de l'IA sont codifiés sous forme de runbooks dynamiques auto-exécutés.

#### 1. Moteur de Runbooks en Base
- Définition de graphes d'actions conditionnels (YAML stocké en DB) :
  ```yaml
  name: Auto-healing Nginx 502
  trigger:
    metric: http_response_code
    condition: "== 502"
  steps:
    - action: RESTART_CONTAINER
      params: { container_name: "nginx-prod" }
    - action: CHECK_HEALTH
      delay: 5
    - if_failed:
        - action: SEND_DISCORD_NOTIFICATION
          params: { level: "CRITICAL", msg: "Remediation failed. Nginx is still down." }
  ```
- **Moteur d'exécution asynchrone** capable de gérer les temps de pause, les boucles de vérification et les cascades conditionnelles.

#### 2. Rollback Automatique en Cas d'Échec
- Avant toute remédiation destructive, le Worker sauvegarde l'état actuel de la configuration. Si le service ciblé ne valide pas ses health checks après action, le Worker effectue un rollback sur l'état valide précédent et lève une alerte.

---

### Sprint 10 — Coordination Multi-Nœuds

L'IA gère la topologie de l'infrastructure globale comme un ensemble cohérent et interdépendant.

#### 1. Graphe de Dépendances Automatique
- Analyse des connexions réseau ouvertes par les containers/processus pour dresser une topologie (ex: *le container Web sur le node-1 dépend de PostgreSQL sur le node-2*).
- Empêche les arrêts en cascade non planifiés et planifie intelligemment l'ordre des redémarrages (Database d'abord, puis API, puis Frontend).

#### 2. Déploiement Gradué (Canary Operations)
- Application d'une modification de configuration ou d'une mise à jour de plugin sur un unique nœud "canari".
- Monitoring automatique de ses performances et métriques d'erreur pendant 1 heure avant de valider et de propager la modification sur le reste des serveurs de la flotte.

---

### Sprint 11 — Apprentissage & Mémoire

L'IA tire parti de l'expérience opérationnelle passée pour affiner ses analyses et résolutions.

#### 1. Indexation et Base de Connaissances Locale (FTS5 / Vector DB)
- Chaque incident résolu (avec ses logs associés, la cause racine identifiée et l'action corrective validée) est archivé et indexé à l'aide de SQLite FTS5 ou d'une base vectorielle locale légère.
- Lors d'une nouvelle alerte, l'IA interroge la base locale pour retrouver les cas similaires : *"Incident similaire résolu le 12 juin sur node-3 en redémarrant le service Docker daemon."*

#### 2. Mémoire Conversationnelle & Contextuelle
- Maintien d'un historique enrichi par node détaillant les pannes passées, les surcharges régulières et les particularités de l'OS. Le LLM adapte ses propositions de commande en fonction de ces spécificités matérielles et logicielles propres à chaque serveur.

---

## Ce qu'on ne construira jamais

- Pas de shell interactif. Jamais.
- Pas d'exécution de commande arbitraire. Whitelist hardcodée, point final.
- Pas de connexion sortante du Master vers les Workers (zéro SSH, zéro push).
- Pas de dépendance à un cloud provider (AWS, GCP, Azure).
- Pas de compte obligatoire chez un tiers pour fonctionner.

Le produit fonctionne entièrement en self-hosted, sur un Raspberry Pi si nécessaire.
