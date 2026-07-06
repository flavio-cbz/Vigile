# Sprint 9 — Moteur de Plugins — Plan d'Exécution

> **Lead orchestrator** : Sisyphus (mode hyperplan dégradé — team adverse indisponible, cross-critique hostile realizée en interne).
> **Date de rédaction** : 2026-07-07
> **Provenance** : le plan qui suit a été écrit en mode direct par le lead Sisyphus après échec du mode team (3/4 personnes in joignables), en appliquant la cross-critique hostile prévue par hyperplan selon 5 angles : YAGNI, cassure de migration, schema risk, hazard machine à états, zero-trust regression. Les décisions défendables sont reproduites ici, les items contestés sont marqués `[DÉFENDU]` ou `[CONCÉDÉ]`.
> **Pré-requis** : avoir lu `docs/plans/PLAN.md` § Sprint 9 (lignes 642-973). Ce document **remplace** la vision § Sprint 9 de `PLAN.md` par un plan livrable ; la vision reste source pour la sémantique.

---

## 0. Résumé exécutif

Sprint 9 construit le **`PluginEngine`** — cœur du nouveau moteur de plugins — et migre les 6 plugins existants (docker, systemd, metrics, clean_logs, discord_alert, slack_alert) sans casser les callers main/ws/automation_engine/admin/chat. **Pas d'UI** dans ce sprint (PageRegistry expose un endpoint ; son consumer frontend est Sprint 10). **Pas de marketplace** (Sprint 11).

**Philosophie livrable** : minimal-viable surface, stubber ce que Sprint 10/11 construiront, garder `register(pm: PluginManager)` fonctionnel via `LegacyPluginWrapper`. Hot-reload inotify **reporté à Sprint 10** (signal SIGUSR1 + endpoint `/api/plugins/_reload` à la place, ~10 lignes, plus sûr sur un bind mount Docker).

**Taille estimée** : ~12 jours de travail effectif (1.5 jour scanner non-watchdog, 1.5 registry, 2 lifecycle, 1.5 routeRegistrar, 0.5 pageRegistry, 1 HookBus lift, 1 DBAuto, 1 Scheduler intervalle-only, 1 PluginBase+SDK, 1 LegacyPluginWrapper, 1 migration). **Gate de prod** : pré-requis Sprint 6 (TLS, rotation WORKER_TOKEN) si `OFFLINE_MODE` et déploiement Internet ; pour un homelab/local, ce sprint est shippable seul.

---

## 1. Non-buts explicites du sprint (DÉFENDU contre le vision doc)

Le vision doc PLAN.md décrit 12 capacités dans le cahier des charges. Nous **ne livrons pas** dans Sprint 9 les morceaux qui servent uniquement à capacité frontend ou marketplace :

| Capacité vision doc | Couper | Raison |
|---|---|---|
| `pages[]` → composant React injecté | Stub manifest only — pas de registration côté React | Frontend = Sprint 10 |
| `widgets[]` → composant React dashboard | Stub manifest only | Frontend = Sprint 10 |
| Marketplace 1-clic | Pas dans le scope | Sprint 11 |
| Hot-reload inotify temps réel | **Reporté** — `/_reload` endpoint + SIGUSR1 pendant Sprint 9 ; inotify surveillé en Sprint 10 | Voir §6.4 |
| Scheduler CRON parser | Intervalle `seconds` only en Sprint 9 ; CRON parser en Sprint 10 | Le seul plugin qui schedule aujourd'hui n'existe pas encore ; YAGNI |
| Dépendances entre plugins (`dependencies.extras`) | Validation déclarative uniquement — pas de résolution automatique | Aucun cas réel existant |
| Update notification (badge quand nouvelle version dispo) | Pas dans le scope | Sprint 11 (marketplace) |
| Plugin with `frontend/assets/icon.svg` | Pas lu | Sprint 10 |

**Défendu** : si on livre les 8 composants en Sprint 9 on expose une surface de code qu'on va refactor en Sprint 10/11. Le pragmatiste gagne.

---

## 2. Architecture ciblée — PluginEngine v1

```
┌─────────────────────────────────────────────────────────────────┐
│                        PluginEngine                              │
│                                                                 │
│  Scanner (sans inotify) ──┐                                     │
│   scan dir plugins/ au    │                                     │
│   boot + endpoint         │                                     │
│   /api/plugins/_reload    ├─→ LifecycleManager                   │
│   déclenche transition    │    (DECOUVERT→INSTALLED→              │
│                           │     ACTIVE→RUNNING→                  │
│                           │     DEACTIVATED→UNINSTALL)            │
│                           │       │                             │
│                           │       │ appelle sur_install,         │
│                           │       │ on_activate, on_deactivate,  │
│                           │       │ on_uninstall                 │
│                           │       ↓                             │
│   Registry (SQL)          │    ┌──────────────┐                 │
│   plugin_registry table   ─┤    │  Dispatcher  │                 │
│   source de vérité        ─┤    │  RouteRegist │ monte routes    │
│                           │    │  PageRegistr │ GET /pages stub │
│                           │    │  HookBus     │ async fan-out   │
│                           │    │  DBAuto      │ CREATE TABLE    │
│                           │    │  Scheduler   │ asyncio.tasks   │
│                           │    └──────────────┘                 │
│                                                                 │
│   PluginBase (classe mère)            LegacyPluginWrapper        │
│   @route, @hook, @page, @widget,     adapte register(pm) →      │
│   @scheduled (decorators)            manifest + PluginBase       │
└─────────────────────────────────────────────────────────────────┘
```

**8 composants, verdict livrable** :

| # | Composant | Sprint 9 | Stub OK | Justification |
|---|---|---|---|---|
| 1 | Scanner | **REAL** | sans inotify | Découvre les dossiers `master/plugins/<id>/manifest.json` + fichiers `.py` plats legacy |
| 2 | Registry | **REAL** | — | Source de vérité persistée (states, versions, config) |
| 3 | LifecycleManager | **REAL** | — | Machine à états sauvegardée en base |
| 4 | RouteRegistrar | **REAL** | — | Monte routes FastAPI sous `/api/plugins/{id}/` — critique pour isolement |
| 5 | PageRegistry | **STUB** | exposé | `GET /api/plugins/pages` retourne `[]` si pas de pages déclarées — pas de consumer React en Sprint 9 |
| 6 | HookBus | **REAL** | — | Remplace hook dispatch synchrone — async strict, AGENTS.md requiert `async_call` |
| 7 | DBAuto | **REAL** | — | CREATE TABLE IF NOT EXISTS depuis manifest — déjà patron pattern de `migrations.py` (idempotent) |
| 8 | Scheduler | **REAL, partiel** | intervalle only | Intervalle `seconds/minutes/hours` — pas de CRON parser |

---

## 3. Manifest v1.0 — Spécification JSON Schema

`manifest.json` à la racine de chaque dossier plugin. **Validation via Pydantic v2** (pas une chaîne JSON Schema libre — schema risk).

### 3.1 Modèle Pydantic

```python
# master/core/plugin_manifest.py (nouveau fichier, ~150 LOC)
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Literal
from enum import Enum

class PluginManifestStatus(str, Enum):
    DECOUVERT = "decouvert"
    INSTALLED = "installed"
    ACTIVE = "active"
    RUNNING = "running"
    DEACTIVATED = "deactivated"
    UNINSTALL = "uninstall"

class ManifestPage(BaseModel):
    id: str
    title: str
    icon: str | None = None
    sidebar: bool = False
    component: str                       # Sprint 10 consumer lit "Containers" → frontend/plugins/<id>/pages/Containers.tsx
    roles: list[Literal["viewer", "operator", "admin"]] = ["viewer"]
    params: list[str] = []               # params d'URL (ex: container_id)
    model_config = ConfigDict(extra="forbid")

class ManifestRoute(BaseModel):
    path: str                            # relatif, ex: "/containers/{id}/logs"
    method: Literal["GET", "POST", "PUT", "DELETE"]
    handler: str                         # nom de la méthode sur PluginBase subclass, ex: "list_containers"
    roles: list[Literal["viewer", "operator", "admin"]] = ["viewer"]

class ManifestTableColumn(BaseModel):
    name: str
    type: str                            # ex: "TEXT PRIMARY KEY" — validé AntiPattern ci-dessous

class ManifestTable(BaseModel):
    name: str
    columns: list[ManifestTableColumn]

class ManifestScheduledTask(BaseModel):
    id: str
    interval: int = Field(ge=5, le=86400, description="Seconds")
    handler: str                         # nom de la méthode sur PluginBase subclass

class ManifestCopilotAction(BaseModel):
    action: str                          # ex: "RESTART_CONTAINER" — doit être dans Worker ALLOWED_ACTIONS
    description: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    params_schema: dict                  # JSON Schema du payload → converti en modèle Pydantic ad-hoc
    target_resolver: str | None = None   # ex: "docker.resolve_container_target" — appel_pointeur vers modulequalifié

class ManifestHooks(BaseModel):
    """HookBus verbs allowed. Validé contre une whitelist stricte."""
    verbs: list[str]                     # ex: ["on_heartbeat", "on_intent_result", "on_status_report"]

class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Identity (obligatoire)
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,30}$")
    name: str
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    author: str
    icon: str | None = None
    category: str
    description_short: str = Field(min_length=5, max_length=200)
    description_full: str | None = None
    license: str = "MIT"

    # Compatibility (obligatoire)
    min_master_version: str

    # Capabilities (optionnelles en Sprint 9,prises en charge par le moteur)
    pages: list[ManifestPage] = Field(default_factory=list)
    widgets: list[dict] = Field(default_factory=list)         # pas de modèle dur en Sprint 9 — Sprint 10 le définira
    routes: list[ManifestRoute] = Field(default_factory=list)
    hooks: list[str] = Field(default_factory=list)           # verbs de HookBus
    database: dict[str, list[ManifestTable]] | None = None   # { tables: [...] }
    config_schema: dict | None = None         # JSON Schema pour le formulaire de configuré — parse en POST
    dependencies_plugins: list[str] = Field(default_factory=list)
    copilot_actions: list[ManifestCopilotAction] = Field(default_factory=list)
    scheduler: list[ManifestScheduledTask] = Field(default_factory=list)

    @field_validator("database")
    @classmethod
    def validate_tables(cls, v):
        if v is None: return v
        if "tables" not in v:
            raise ValueError("manifest.database doit avoir une clé 'tables' (liste)")
        return v
```

### 3.2 Risques schema-intentionnel — `[DÉFENDU]`

| Risque | Mitigation |
|---|---|
| Plugin renommé → collision `id` en base | `id` valide `^[a-z][a-z0-9_]{1,30}$` (impossible à renommer silencieusement). Sur `LifecycleManager.on_install` : si `id` existe déjà avec autre chose qu'un réinstall, fail-closed. |
| Préfixe table fuit dans le core | `ManifestTable.name` DOIT commencer par `<plugin_id>_` — validé dans `LifecycleManager.on_install`. Sinon `ValueError`. |
| `copilot_actions` JSON non-typé → LLM hallucine | Modèle `ManifestCopilotAction` + `params_schema` converti en modèle Pydantic (via `pydantic.create_model`) au runtime — les actions Copilot ne sortent jamais sans validation de params. |
| `config_schema` JSON Schema non cyclé | Validation via `jsonschema` (lib tierce ajoutée à `requirements.txt` nouvelle dépendance — pas sur le core, seulement le moteur). **Alternative native** : implémenter subset JSON Schema validator (5 types + required + min/max + enum) — ~80 LOC. `[CONCÉDÉ]` : utiliser subset natif pour éviter la dépendance. |
| `target_resolver` arbitrary callable pointer | Syntaxe stricte `module.qualname` validée par whitelist. Pour Sprint 9, seul `docker.resolve_container_target` est autorisé. `[DÉFENDU]`. |

---

## 4. PluginBase API — Surface publique

Le SDK pour écrire un plugin. Toute la machinerie est opt-in.

```python
# master/core/plugin_base.py (nouveau fichier, ~120 LOC)
import asyncio, json, logging
from typing import Any, Callable
from collections.abc import Awaitable

logger = logging.getLogger(__name__)

class PluginContext:
    """Runtime API handed by the engine to a plugin instance."""
    def __init__(self, engine: "PluginEngine", plugin_id: str, db, config: dict):
        self._engine = engine
        self._plugin_id = plugin_id
        self._db = db
        self.config = config

    async def db_execute(self, sql: str, params: tuple = ()) -> list[dict]:
        # SQL restreinte — table name match ^<plugin_id>_, pas d'écriture core
        ...

    async def db_execute_mut(self, sql: str, params: tuple = ()) -> int:
        # Pour INSERT/UPDATE/DELETE — wrappé dans transaction()
        ...

    async def fetch_node_stats(self, node_id: str) -> dict | None: ...
    async def fetch_connected_nodes(self) -> list[str]: ...
    async def create_proposal(self, action: str, target: str | None, params: dict, reasoning: str, risk_level: str, node_id: str | None = None) -> str:
        # Proxy vers le module chat_proposal normalizer — alias explicite
        # NE BYPASSE PAS la normalisation RESTART_CONTAINER — voir §7
        ...

    async def emit_event(self, name: str, payload: dict) -> None:
        # proxy vers HookBus.publish
        ...

def route(path: str, method: str = "GET", roles: list[str] = ("viewer",)):
    def deco(fn): fn.__plugin_route__ = {"path": path, "method": method, "roles": roles}; return fn
    return deco

def hook(verb: str):
    def deco(fn): fn.__plugin_hook__ = verb; return fn
    return deco

def scheduled(interval: int):
    def deco(fn): fn.__plugin_sched__ = {"interval": interval}; return fn
    return deco

def page(title: str, *, icon: str | None = None, sidebar: bool = False, roles: list[str] = ("viewer",)):
    def deco(fn): fn.__plugin_page__ = {"title": title, "icon": icon, "sidebar": sidebar, "roles": roles}; return fn
    return deco

class PluginBase:
    id: str                          # subclass class attr ; override
    name: str
    version: str
    # ... autres identity (recopiés du manifest si absent)

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self.config = ctx.config

    # Lifecycle hooks (optionnels). Override seulement.
    async def on_install(self) -> None: pass
    async def on_activate(self) -> None: pass
    async def on_deactivate(self) -> None: pass
    async def on_uninstall(self) -> None: pass
```

### 4.1 Règles critique de `PluginContext.db_execute`

- SQL command starts with SELECT, INSERT, UPDATE, DELETE, CREATE, DROP (whitelist).
- Tout identifiant de table doit matcher `^<plugin_id>_` ou être dans une exception whitelist `__VIGILE_SHARED__` (vide en Sprint 9).
- Refus de lire `users`, `nodes`, `audit_log`, `proposals`, `plugin_registry`, `tokens`, `insights`.
- En cas de violation → `RuntimeError` loggé dans audit (réutilisant `master.core.audit.add_audit_entry`).

---

## 5. LegacyPluginWrapper — Bridge de compatibilité

Le bridge permet aux 6 plugins existants (`register(pm)`) d'être discoverés par le nouveau `Scanner` sans réécriture immédiate. **Migrés un par un en post-Sprint-9**.

```python
# master/core/plugin_engine_legacy_bridge.py (nouveau fichier, ~80 LOC)
"""
Adapte register(pm: PluginManager) → PluginEngine avec manifest synthétisé.
Le manifest est généré à partir de :
  - le module Python existant s'il expose get_config_schema()
  - la liste des hooks enregistrés (lue après register() dans un faux PluginManager)
"""
import importlib.util, os, sys
from .plugin_manifest import PluginManifest, ManifestPage, ManifestRoute

class _FakePluginManager:
    """Capture-register : enregistre les hooks sans les exécuter."""
    def __init__(self):
        self.calls = []                                   # liste de (hook_name, plugin_name)
    def register(self, hook_name, fn, *, plugin_name="anonymous"):
        self.calls.append((hook_name, plugin_name))

def wrap_legacy_plugin(plugin_path: str, plugin_id_hint: str) -> tuple[PluginManifest, type[PluginBase]]:
    """Charge module register(pm), capture les hooks, synthétise un manifest minimal."""
    module_name = f"vigile.plugins_legacy.{plugin_id_hint}"
    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {plugin_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "register"):
        raise ImportError(f"Legacy plugin {plugin_id_hint} n'expose pas register()")

    fake = _FakePluginManager()
    module.register(fake)
    hooks_verb = list({hook_name for hook_name, _ in fake.calls})

    config_schema = None
    if hasattr(module, "get_config_schema"):
        schema_dict = module.get_config_schema()
        config_schema = schema_dict.get("schema") if isinstance(schema_dict, dict) else None

    manifest = PluginManifest(
        id=plugin_id_hint,
        name=plugin_id_hint,                                  # sera surchargé par get_config_schema().name
        version="1.0.0",
        author="vigile-legacy",
        category="legacy",
        description_short=f"Legacy plugin {plugin_id_hint} (auto-wrapped)",
        min_master_version="0.0.0",                            # toujours OK
        hooks=hooks_verb,
        config_schema=config_schema,
        copilot_actions=[],                                    # injectés ailleurs en Sprint 9 (§7.1)
    )

    class _LegacyPluginBase(PluginBase):
        async def on_activate(self):      # exécute les hooks capturés via HookBus
            engine = self.ctx._engine
            for verb in hooks_verb:
                # bind module.<fn> vers HookBus.subscribe(verb, ...)
                # détail en §6.5 HookBus
                ...
        async def on_deactivate(self):
            engine = self.ctx._engine
            # unsubscribe
            ...

    return manifest, _LegacyPluginBase
```

**`[DÉFENDU]`** Le bridge demande un module_name unique `vigile.plugins_legacy.<id>` pour ne pas polluer le namespace `master.plugins.<id>`. **`[CONCÉDÉ]`** le `config_schema` hérité de `get_config_schema()` est loose-typed (dict pas Pydantic) — on accepte un pas-respect manifest pour la transition.

---

## 6. LifecycleManager — Machine à états

### 6.1 Transitions

```
        ┌──────────┐
        │DECOUVERT │  ← Scanner valide manifest
        └────┬─────┘
             ↓ install(plugin_id)
        ┌──────────┐
        │INSTALLED │  → DBAuto: CREATE TABLE IF NOT EXISTS <plugin_id>_*
        └────┬─────┘   init config defaults si plugin_configs vide
             ↓ activate(plugin_id)
        ┌──────────┐
        │ACTIVE    │  → RouteRegistrar monte routes /api/plugins/{id}/...
        └────┬─────┘   PageRegistry enregistre les pages (stub pour Sprint 10)
             ↓         HookBus subscribe les hooks déclarés
        ┌──────────┐   Scheduler démarre les tâches planifiées (intervalle only)
        │RUNNING   │  ← état nominal
        └────┬─────┘
             ↓ deactivate(plugin_id)
        ┌──────────┐
        │DEACTIVATED│ → inverse de activate : démonte routes, unsubscribe, stop scheduler
        └────┬─────┘
             ↓ uninstall(plugin_id) (DEMANDÉ par admin, pas automatique)
        ┌──────────┐
        │UNINSTALL │  → DBAuto: DROP TABLE <plugin_id>_*
        └──────────┘   supprime ligne plugin_registry
```

### 6.2 Persistence — table `plugin_registry`

```sql
-- dans master/db/migrations.py — nouvelle migration idempotente
CREATE TABLE IF NOT EXISTS plugin_registry (
    id TEXT PRIMARY KEY,                              -- manifest.id
    version TEXT NOT NULL,
    status TEXT NOT NULL,                             -- une des enum PluginManifestStatus
    config_json TEXT,                                 -- JSON
    discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    installed_at DATETIME,
    activated_at DATETIME,
    last_run_at DATETIME,
    deactivated_at DATETIME,
    manifest_hash TEXT NOT NULL,                      -- SHA256 du manifest.json pour détecter changements
    manifest_json TEXT NOT NULL                       -- snapshot du manifest validé
);
CREATE INDEX IF NOT EXISTS idx_plugin_registry_status ON plugin_registry(status);
```

Table séparée de `plugin_configs` (existant) — `plugin_configs` reste pour la compat legacy pendant la transition puis est migrée.

### 6.3 Hazards machine à états — `[DÉFENDU]` (cross-critique hostile)

| Hazard | Mitigation |
|---|---|
| Partial failure mid-transition (CREATE TABLE réussit mais RouteRegistrar échoue) | `transaction()` wrapper pour la DB ; routes sont montées en post-commit seulement. Si RouteRegistrar échoue → état reste `INSTALLED` avec colonne `activated_at=NULL` et entry logge dans audit avec niveau ERROR. Pas de `RUNNING` silencieux. |
| Inotify race pendant hot reload | **Pas d'inotify en Sprint 9** — `POST /api/plugins/_reload` prend un lock asyncio pour scanner pendant qu'un plugin running peut finir son hook en cours. Rechargement = deactivate + uninstall + re-install + activate. Verbeux mais sans course. |
| Upgrade-in-place (RUNNING→INSTALLED pour nouvelles version) | `LifecycleManager.upgrade(plugin_id, new_version)` appelle deactivate → DBAuto preserve tables (PAS de DROP) → install avec `manifest_hash` mis à jour. Les tables ne sont DROPPED qu'en uninstall final. `[DÉFENDU]` |
| Concurrent deactivate + uninstall from admin UI | Mécanique d'async lock par `plugin_id` dans `LifecycleManager._locks: dict[str, asyncio.Lock]`. Première opération gagne ; deuxième retourne `409 Conflict` à l'admin. |
|lient redémarre pendant RUNNING | 0 problème — Scanner au boot lit `plugin_registry`, si status `RUNNING` alors plugin était actif ; le moteur le ré-active (call sequence install→activate) si manifest_hash matches. Si mismatch → status replacé à `INSTALLED`, admin notifié via audit. |

---

## 6.4 Scanner — Pas d'inotify en Sprint 9

```
Scanner.scan() → liste os.listdir(plugins_dir)
    → pour chaque entrée :
       - si dossier avec manifest.json → parse PluginManifest, lifecycle.install_or_upgrade()
       - si fichier .py → wrap via wrap_legacy_plugin(plugin_path) → lifecycle.install_or_upgrade()
    → après scan, expose POST /api/plugins/_reload pour forcer re-scan (admin only)
```

Le hook `/_reload` déclenche aussi `SIGHUP` au process via `os.kill(os.getpid(), signal.SIGHUP)` — `PluginEngine` installe un handler au boot qui appelle `Scanner.scan()` et re-monte les plugins ayant changé de `manifest_hash`. **C'est le seul mécanisme de hot-reload en Sprint 9**. Inotify est différé à Sprint 10 car :

1. Watcher sur bind mount Docker peut générer un événement par fichier temp (éditeur vim, rsync) → storm
2. Aucun cas d'usage pré-Sprint-10 (les plugins ne sont pas édités en prod)
3. ~10 lignes vs ~150 LOC pour inotify + debounce + path filter

**`[DÉFENDU]`** Perte : sur un homelab, l'utilisateur devra appeler `/api/plugins/_reload` après avoir téléchargé un plugin. C'est acceptable.

---

## 6.5 HookBus — Évolution de `event_bus.py` existant

`master/core/event_bus.py` (57 LOC) existe déjà. **On ne le duplique pas.** HookBus est une spécialisation :

```python
# master/core/plugin_engine.py (nouveau fichier, ~250 LOC attendu)
class PluginEngine:
    def __init__(self, db, settings, sandbox: bool):
        self._db = db
        self._settings = settings
        self._sandbox = sandbox
        self._plugins: dict[str, PluginInstance] = {}     # plugin_id → instance loaded
        self._scanner = Scanner(self)
        self._lifecycle = LifecycleManager(self)
        self._routes = RouteRegistrar(self)
        self._pages = PageRegistry(self)
        self._scheduler = Scheduler(self)
        self._lock_per_plugin: dict[str, asyncio.Lock] = {}
        self.bus = get_event_bus()                          # réutilise event_bus singleton

    async def initialize(self):
        # 1. migration idempotente plugin_registry (CREATE TABLE)
        await self._ensure_registry_schema()
        # 2. scan au boot
        await self._scanner.scan()
        # 3. pour chaqueligne en base au status RUNNING/ACTIVE, re-activate
        ...

    async def publish_hook(self, verb: str, payload: dict):
        """HookBus entrypoint — publie sur topic 'plugin:<verb>'."""
        await self.bus.publish(f"plugin:{verb}", payload)

    async def dispatch_hook(self, verb: str, payload: dict) -> list:
        """Replace plugin_manager.async_call(verb, **payload) — async strict."""
        # Affiche-map plugins cuntomabi: subscribe('plugin:<verb>', cb) par cb
        ...
```

**HookBus verbs whitelist** — imposée par `LifecycleManager.on_activate` qui refuse un manifest dont `hooks` contient un verb inconnu. Sprint 9 whitelist :
```
on_heartbeat, on_status_report, on_intent_result, on_node_connect,
on_node_disconnect, on_proposal_approved, on_proposal_rejected,
on_config_changed, on_cron_minute, on_cron_hour
```

(`on_cron_*` sont publiés par le Scheduler, pas par event external.)

---

## 7. Zero-trust regression — `[DÉFENDU]` critique

### 7.1 RESTART_CONTAINER normalization reste en chat.py

**État actuel** : `master/api/chat.py:782-877` contient `_normalize_action_proposal`, `_extract_container_target`, `_resolve_container_target`, `_match_container`. Logique : extrait le target du payload LLM, le résout contre containers cache, fallback live `LIST_CONTAINERS` via `node_manager`, fail-closed sur ambiguïté.

**`[CONCÉDÉ]`** à l'argument schema architect : si la logique de normalisation reste dans `chat.py`, un plugin tiers `docker` ne peut pas fournir son propre resolver (le plugin-appelé n'exécute jamais la résolution). Donc `ManifestCopilotAction.target_resolver` est **prévu mais non utilisé en Sprint 9**. La signature est gardée dans le manifest pour éviter un breaking change en Sprint 10.

**Verdict Sprint 9** :
- `chat.py` reste l'unique point de normalisation des proposals `RESTART_CONTAINER`. Non touchée par Sprint 9.
- `PluginContext.create_proposal` route **uniquement** sur des actions non-`RESTART_CONTAINER`. Pour `RESTART_CONTAINER` une exception est levée : `ValueError("RESTART_CONTAINER must flow through chat proposal normalizer")`. Cela force les plugins à ne pas court-circuiter la safety net.
- Audit : entrée `audit_log` recordée à chaque appel `PluginContext.create_proposal`.

### 7.2 Isolement DB

- `PluginContext.db_execute` refuse les tables hors préfixe `<plugin_id>_`.
- WRBAC : `PluginContext.db_execute` ne peut pas écrire dans `audit_log` (préfixe refusé).
- Logique implémentée dans `PluginContext._validate_sql` (regex + AST lite parser ~40 LOC). Refus → audit entry ERROR + `RuntimeError`.

### 7.3 Route mount RBAC

Chaque `ManifestRoute.roles` est validé à l'exécution par `RouteRegistrar` qui wrap handler dans `with require_role(roles)`. Reprise de `master.api.deps.require_role` existant.

---

## 8. RouteRegistrar — Montage des routes FastAPI

### 8.1 Pattern

```python
# master/core/plugin_engine.py — extrait
class RouteRegistrar:
    def __init__(self, engine): self._engine = engine; self._mounted: dict[str, APIRouter] = {}

    async def mount(self, plugin_id: str, routes: list[ManifestRoute], instance: PluginBase):
        router = APIRouter(prefix=f"/api/plugins/{plugin_id}", tags=[f"plugin:{plugin_id}"])
        for r in routes:
            handler = getattr(instance, r.handler, None)
            if handler is None or not callable(handler):
                raise RuntimeError(f"Plugin {plugin_id}: handler '{r.handler}' non défini")
            wrapped = _apply_roles(handler, r.roles)         # dépend deps.require_role
            router.add_api_route(r.path, wrapped, methods=[r.method])
        self._engine.app.include_router(router)
        self._mounted[plugin_id] = router

    async def unmount(self, plugin_id: str):
        router = self._mounted.pop(plugin_id, None)
        if router is None: return
        # FastAPI ne supporte pas le unmount direct — stratégie manuelle:
        # - On filtre app.routes pour ne garder que ceux dont le path ne commence pas par /api/plugins/{id}/
        self._engine.app.router.routes = [
            r for r in self._engine.app.router.routes
            if not (hasattr(r, 'path') and r.path.startswith(f"/api/plugins/{plugin_id}/"))
        ]
```

### 8.2 Mitigation hazard

* **`[DÉFENDU]`** FastAPI n'a pas d'API publique pour `unmount`. La méthode filter `app.router.routes = [...]` est dans `app.router.routes` liste — opération documentée par Starlette source. Test de non-régression à écrire (crée route, unmount, vérifie 404). Sprint 10 pourra switcher sur un mount/unmount plus propre si besoin.
* Sur conflicting path → `RuntimeError` au moment du mount, ne silent fail pas. Le plugin reste en `INSTALLED`, pas `RUNNING`.

---

## 9. Scheduler — Intervalle only

```python
# master/core/plugin_engine.py — extrait
class Scheduler:
    def __init__(self, engine): self._engine = engine; self._tasks: dict[str, asyncio.Task] = {}
    async def start(self, plugin_id: str, tasks: list[ManifestScheduledTask], instance: PluginBase):
        for t in tasks:
            handler = getattr(instance, t.handler, None)
            if not callable(handler) or not asyncio.iscoroutinefunction(handler):
                raise RuntimeError(f"Plugin {plugin_id}: scheduler task {t.id} handler non async")
            key = f"{plugin_id}:{t.id}"
            self._tasks[key] = asyncio.create_task(self._loop(plugin_id, t, handler), name=key)

    async def stop(self, plugin_id: str):
        for key in list(self._tasks):
            if key.startswith(f"{plugin_id}:"):
                self._tasks[key].cancel()
                try: await self._tasks[key]
                except asyncio.CancelledError: pass
                del self._tasks[key]

    async def _loop(self, plugin_id, t, handler):
        while True:
            try: await handler()
            except Exception: logger.exception("scheduled task %s failed", t.id)
            await asyncio.sleep(t.interval)
```

**Pas de CRON parser en Sprint 9.** `[DÉFENDU]` : aucun plugin existant n'utilise le scheduler. Premier plugin schedulé vient en Sprint 10 (metrics refresh cache). YAGNI wins. `interval` ≥5s et ≤86400s.

---

## 10. PageRegistry — Stub Sprint 9, consommable en Sprint 10

```python
class PageRegistry:
    def __init__(self, engine): self._engine = engine
    async def register(self, plugin_id: str, pages: list[ManifestPage]):
        # En Sprint 9 : garde en mémoire dans self._pages_per_plugin[plugin_id]
        # API GET /api/plugins/pages l'expose
        ...
```

Endpoint `GET /api/plugins/pages` retourne un tableau plat de toutes les pages déclarées par les plugins au status `RUNNING`. Le frontend (Sprint 10) lira cela au boot et montera les routes via `React.lazy`. **Stub livré en Sprint 9 — endpoint OK, mais aucun plugin ne déclare de `pages` réelles avant Sprint 10.**

---

## 11. DBAuto — Idempotent

```python
class DBAuto:
    async def install(self, plugin_id: str, manifest: PluginManifest):
        if manifest.database is None: return
        for table in manifest.database["tables"]:
            if not table.name.startswith(f"{plugin_id}_"):
                raise ValueError(f"Table {table.name} doit préfixer {plugin_id}_")
            cols_sql = ", ".join(f"{c.name} {c.type}" for c in table.columns)
            await self._engine._db.execute(f"CREATE TABLE IF NOT EXISTS {table.name} ({cols_sql})")
        await self._engine._db.commit()

    async def uninstall(self, plugin_id: str, manifest: PluginManifest):
        if manifest.database is None: return
        for table in manifest.database["tables"]:
            await self._engine._db.execute(f"DROP TABLE IF EXISTS {table.name}")
        await self._engine._db.commit()
```

**Wrappé dans `transaction()`** si plus d'une table (single shared aiosqlite connection).

---

## 12. Mapping callers — Cassure de migration

### 12.1 Pointeurs actuels identificiés (fichiers + lignes)

| Appelant | Ligne | Code actuel | Sprint 9 action |
|---|---|---|---|
| `master/main.py` | 47 | `from master.core.plugin_manager import plugin_manager` | **Remplacé** : `from master.core.plugin_engine import get_plugin_engine`. Le singleton `plugin_manager` deviendra un proxy LibreOffice-compat : voir §12.3 |
| `master/main.py` | 267 | `await plugin_manager.initialize(db, sandbox=...)` | `await engine.initialize(db, settings, sandbox=settings.plugin_sandbox)` |
| `master/main.py` | 270 | `loaded = await plugin_manager.load_plugins_from_dir(settings.plugins_dir)` | `loaded = await engine.scan()` |
| `master/main.py` | 285 | `plugin_manager.register("on_status_report", automation_engine.evaluate_metric_trigger, plugin_name="automation_engine")` | `engine.register_internal_hook("on_status_report", automation_engine.evaluate_metric_trigger)` — l'automation_engine n'est pas un plugin, just un subscriber |
| `master/ws/worker_handler.py` | 43 | `from master.core.plugin_manager import plugin_manager` | `from master.core.plugin_engine import get_plugin_engine` |
| `master/ws/worker_handler.py` | 683 | `await plugin_manager.async_call_first("normalize_status_report", raw_report=msg)` | `await engine.dispatch_hook("normalize_status_report", {"raw_report": msg})` (retourne first non-None) |
| `master/ws/worker_handler.py` | 687 | `await plugin_manager.async_call("on_status_report", node_id=..., snapshot=..., db=db)` | `await engine.dispatch_hook("on_status_report", {"node_id": ..., "snapshot": ..., "db": db})` |
| `master/core/automation_engine.py` | 93, 103 | Commentaires mentionnent "hooked via plugin_manager" — pas de couplage code | Aucun changement code |
| `master/api/admin.py` | 38 | `from master.core.plugin_manager import canonical_plugin_id, plugin_file_stem, plugin_manager` | Gardé **pour compat** — déplacé vers `plugin_engine_legacy_compat.py` qui re-exporte les helpers + le singleton proxy |
| `master/api/admin.py` | 344, 345 | `plugin_manager._sandbox` and `plugin_manager._wrappers` (private API access!) | **Refactor majeur** — admin expose `GET /api/plugins/{id}/status` qui retourne sandbox state publiquement. Plus de `_sandbox`/`_wrappers` access. |
| `master/api/admin.py` | 351 | `plugin_manager.get_hooks()` | `engine.get_hooks()` — public API stable |
| `master/api/admin.py` | 372, 373 | `"loaded_plugins": plugin_manager.loaded_plugins`, `"hooks": plugin_manager.get_hooks()` | Même |
| `master/api/admin.py` | 552, 650 | `await plugin_manager.load_plugin(plugin_name, settings.plugins_dir)` | `await engine.install_plugin(plugin_id)` — noms reconciliés |
| `master/api/admin.py` | 754, 756 | `await plugin_manager.load_plugin(plugin_stem, settings.plugins_dir); await plugin_manager.unload_plugin(plugin_stem)` | `await engine.reactivate_plugin(plugin_id)` — l'admin a désormais un verbe unique |
| `master/api/admin.py` | 801 | `await plugin_manager.unload_plugin(plugin_stem)` | `await engine.deactivate_plugin(plugin_id)` — pas supprime les tables, status `DEACTIVATED` |

### 12.2 Tests à pré-ajouter avant migration (AGENTS.md behavioral rule)

`tests/test_plugins/` 569 LOC existants. Ajouter :

```
tests/test_plugin_engine/
├── test_manifest_validation.py      # 30 tests : schéma manifest valide/invalide
├── test_lifecycle_state_machine.py # 20 tests : transitions valides + invalides + concurrency lock
├── test_route_registrar.py         # 15 tests : mount/unmount, RBAC, conflicting path
├── test_db_auto_isolation.py       # 15 tests : table prefix enforcement, DROP en uninstall
├── test_hook_bus_dispatcher.py    # 10 tests : async fan-out, sync hooks sont warned+skip
├── test_scheduler_interval.py     #  8 tests : intervalle, cancel on deactivate
├── test_legacy_plugin_wrapper.py  # 12 tests : 6 plugins existants wrappés correctement
├── test_plugin_context_isolation.py # 15 tests : SQL refusal hors préfixe, RESTART_CONTAINER bypass refusé
└── test_admin_plugin_lifecycle.py  # 15 tests : install/activate/deactivate/uninstall via API
```

**Couverture cible** : 90% sur `master/core/plugin_engine.py` + `master/core/plugin_manifest.py` + `master/core/plugin_base.py` + `master/core/plugin_engine_legacy_bridge.py`.

### 12.3 Singleton compat — `plugin_manager` exact

Pour que tous les calls ci-dessus restent OK (en attendant le refactor après Sprint 9), on garde un module `master.core.plugin_manager` déprécié qui expose un singleton `plugin_manager` proxant sur `plugin_engine`. Signature identique (`register`, `async_call`, `async_call_first`, `loaded_plugins`, `get_hooks`, `load_plugin`, `unload_plugin`, `_sandbox`, `_wrappers`, `_enabled_plugins`). Les appels sont rétro-compatibles ; `_sandbox` retourne le booléen `engine._sandbox` ; `_wrappers` retourne `{}` (legacy sandbox subprocess n'est pas repris — décision assumée, voir §13).

**`[DÉFENDU]`** : on garde 1 sprint de compat (Sprint 9) ; refacto cleanup admin.py post-Sprint-9 supprime cette couche.

---

## 13. Sandbox subprocess — `[CONCÉDÉ]` sacrifice

Le `PluginProcessWrapper` actuel (sandbox via subprocess JSON-RPC IPC, ~250 LOC) **n'est pas repris** dans PluginEngine en Sprint 9. Raisons :

1. Aucun plugin existant ne nécessite le subprocess (tous s'exécutent en in-process)
2. La complexité (IPC, db proxy, restart) est déportée à Sprint 10/11 quand il y aura des plugins tiers
3. Le setting `settings.plugin_sandbox` reste en place mais ignore en Sprint 9 (warning loggé)

`[DÉFENDU]` contre integration pessimist : les 6 plugins first-party n'ont jamais crashé le master en 4 semaines de prod (selon AGENTS.md field-validation). Le subprocess n'a jamais été exercé. La suppression n'a aucun impact de prod.

---

## 14. Plugin migration — Order & verification

After PluginEngine + LegacyPluginWrapper sont livrés et tests verts, on migre un par un les 6 plugins legacy vers format dossier + manifest.

**Ordre (du plus simple au plus complexe)** :

1. **slack_alert** (116 LOC) — pas de hooks critique, pas de table, pas de Copilot actions
2. **discord_alert** (105 LOC) — pareil
3. **clean_logs** (110 LOC) — hook `on_status_report` seul
4. **systemd_plugin** (103 LOC) — `get_supported_actions` seul (LIST_SERVICES)
5. **metrics_plugin** (330 LOC) — `normalize_status_report` hook critique, expose `MetricsSnapshot` Pydantic
6. **docker_plugin** (87 LOC) — couplage fort avec `chat.py` (normalisation RESTART_CONTAINER reste en chat)

**Verification gate** pour chaque migration :
- [ ] Plugin chargé sans erreur au boot
- [ ] `GET /api/plugins/{id}/status` retourne `running` + manifest_hash
- [ ] Test de non-régression : `tests/test_plugins/test_plugins.py` et `test_examples.py` verts
- [ ] Pour docker uniquement : `python -m pytest tests/test_chat_proposals_docker.py` verts (à créer) qui prouve que `_normalize_action_proposal` résout un container ambiguous et fail-closed comme avant
- [ ] `python -m pytest -m "not integration"` verts
- [ ] LSP diagnostics clean sur les fichiers touchés

---

## 15. Étapes livrables Sprint 9 (12 jours)

| Jour | Livrable | Verif gate |
|---|---|---|
| 1 | `master/core/plugin_manifest.py` (Pydantic) + 30 test cas | `pytest tests/test_plugin_engine/test_manifest_validation.py` verts |
| 2 | `master/db/migrations.py` extension `plugin_registry` + 5 tests | DB init au boot sans erreur ; index créé ; idempotent |
| 3 | `master/core/plugin_base.py` + `PluginContext` + 15 tests isolation SQL | `pytest test_plugin_context_isolation.py` verts — isolation refusée |
| 4 | `master/core/plugin_engine.py` LifecycleManager + 20 tests transitions | `pytest test_lifecycle_state_machine.py` verts |
| 5 | `RouteRegistrar` + 15 tests (mount/unmount) | `pytest test_route_registrar.py` verts — unmount prouve 404 |
| 6 | `PageRegistry` (stub) + `HookBus` (lift event_bus) + 10 tests | `pytest test_hook_bus_dispatcher.py` verts — async strict |
| 7 | `DBAuto` + `Scheduler` (interval only) + 23 tests combinés | `pytest test_db_auto_isolation.py test_scheduler_interval.py` verts |
| 8 | `Scanner` (sans inotify) + `POST /api/plugins/_reload` + 5 tests | `/api/plugins/_reload` retourne 200 ; log audit |
| 9 | `LegacyPluginWrapper` + 12 tests (1 par plugin legacy) | 6 plugins wrappés tous discovery → status DECOUVERT |
| 10 | `master/core/plugin_manager.py` proxy compat singleton + `master/api/admin.py` refactor (drop `_sandbox`/`_wrappers` private access) + 15 tests | `pytest test_admin_plugin_lifecycle.py` verts ; `pytest tests/test_plugins/` toujours verts |
| 11 | Migration des 6 plugins legacy → format dossier + manifest (1 par 1) | LSP clean, tests verts |
| 12 | Mise à jour `AGENTS.md` + `docs/plans/PLAN.md` (status Sprint 9 ✅) + `RULES.md` | Lint doc, plus de conflit |

**Total tests ajoutés** : ~130 nouveaux tests + 6 migrations. Couverture cible `master/core/plugin_engine.py` ≥ 90%.

---

## 16. Risques résiduels à scoper en Sprint 10+

- **Hot-reload inotify** : reporté. Si un plugin édité pendant que le master tourne → appeler `/api/plugins/_reload` ou envoyun `SIGHUP` au process.
- **Plugin first-party sandbox subprocess** : PluginProcessWrapper n'est pas repris. Si un plugin tiers arrive en Sprint 10 qui crash le process → sprint 10 devra réintroduire l'isolation.
- **Scheduler CRON parser** : différé à Sprint 10. La clause `cron` du manifest sera rejetée en Sprint 9.
- **PageRegistry consumer React** : endpoint OK, frontend pas consumer. À faire en Sprint 10.
- **Manifest config_schema form generator** : subset JSON Schema validé côté master ; génération du formulaire côté frontend en Sprint 10.
- **Marketplace** : pas dans ce sprint. `dependencies.extras` validé forme mais non résolu.

---

## 17. Mise à jour AGENTS.md

À livrer le jour 12 :
- Table CODE MAP : ajout de `PluginEngine`, `PluginManifest`, `PluginBase`, `Scanner`, `LifecycleManager`, `RouteRegistrar`, `PageRegistry`, `HookBus`, `DBAuto`, `Scheduler`, `LegacyPluginWrapper`, `PluginContext`
- Anti-patterns : ajout "Accès PluginContext.db_execute sur une table hors préfixe `<plugin_id>_` est interdit et loggé en audit"
- Unique styles : ajout "Manifest"id est immuable ; toute collision provoque fail-closed en install"
- Conventions : ajout "Toutes les tables créées par un plugin doivent préfixer `<plugin_id>_` ; SQL hors préfixe est refusé à l'exécution par `PluginContext`"
- Audit findings 2026-06-04 : mise à jour mention Sprint 9 livré + nouveaux tests en place
- FIELD VALIDATION 2026-06-17 : ajout mention "le worker binary ne varie pas en Sprint 9"

---

## 18. Mise à jour `docs/plans/PLAN.md`

Section Sprint 9 passe de `❌` à `⚠️ (core engine + 6 plugins migrated)`. Sprint 10/11 restent `❌` et sont explicitement "prérequis Sprint 9 ✅".

---

## 19. Note finale — Cross-critique hostile

Le mode team a échoué (3/4 personnes in joignables via OpenRouter, sessions deleted avec la team avant livraison). La cross-critique hostile à 5 angles (YAGNI, migration breakage, schema risk, state machine hazards, zero-trust regression) a été menée **en interne par le lead Sisyphus** directement, ancrée dans les faits du code (PluginManager 612 LOC lu, EventBus 57 LOC, callers mappés file:line, chat.py 782-877 normalizer relu, 6 plugins skésmatisés). Les décisions contestées sont marquées `[DÉFENDU]` ou `[CONCÉDÉ]` en §3.2, §6.3, §7.1, §12.3, §13. Le plan est **actionnable tel quel**.

Le plan original hyperplan exigeait que le bundle soit handé au **plan agent** (`task(subagent_type="plan", ...)`) qui own séquence, parallelization, gates. La révision de ce plan par un plan agent reste recommandée en phase d'exécution ; en mode dégradé, le §15 fournit déjà la sequentiation + les gates de verif et peut être consommé directement par `task(category="...")`.
