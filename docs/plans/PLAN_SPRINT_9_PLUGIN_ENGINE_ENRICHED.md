# Sprint 9 — Moteur de Plugins — Core Engine (ENRICHED)

> **Provenance**: Plan original enrichi par le workflow hyperplan adversarial (4 analyseurs hostiles : Implementation Gunner, Architecture Critic, Deep Thinker, Deep Researcher) sur la base de l'audit complet du code existant (plugin_manager.py:612 LOC, 6 plugins:853 LOC, 6 fichiers de test:1377 LOC, 5 modules importeurs).
>
> **10 correctifs adversariales incorporés** — voir Annexe pour la traçabilité.

---

## User Review Required

> [!IMPORTANT]
> **Pas de Sandbox Subprocess en Sprint 9** — exécution in-process sécurisée au niveau logique.
>
> **Règle Zero-Trust DB** : `PluginContext.db_execute` vérifie au runtime que les tables modifiées commencent par `<plugin_id>_`, **sauf** pour la whitelist `__VIGILE_SHARED__` qui autorise les plugins first-party à accéder aux tables core.
>
> **YAGNI** : Pas d'UI (Sprint 10), pas de CRON parser.

---

## Proposed Changes

### 1. Fondations & Validation du Manifest
#### [NEW] [plugin_manifest.py](master/core/plugin_manifest.py)
* Modèle Pydantic `PluginManifest` : `id`, `name`, `version`, `author`, `description`, `icon`, `routes`, `hooks`, `database` (schémas avec colonnes/types), `scheduler`, `min_master_version`.
* **Adversarial fix #H5** : `manifest_hash` calculé sur `model_dump_json(sort_keys=True)` pour éviter les faux positifs de formatage JSON.

---

### 2. Base de données & Migrations
#### [MODIFY] [migrations.py](master/db/migrations.py)
* **Adversarial fix #H4** : Fusion `plugin_configs` + `plugin_registry` → table unique `plugins` :
   ```sql
   CREATE TABLE IF NOT EXISTS plugins (
       id              TEXT PRIMARY KEY,
       version         TEXT NOT NULL DEFAULT '0.0.0',
       enabled         INTEGER NOT NULL DEFAULT 1,
       status          TEXT NOT NULL DEFAULT 'INSTALLED',
       config_json     TEXT NOT NULL DEFAULT '{}',
       manifest_hash   TEXT,
       updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   ```
* Migration : `ALTER TABLE plugin_configs RENAME TO plugins;` + `ALTER TABLE ADD COLUMN` pour version/status/manifest_hash.
* `_seed_default_plugins` mis à jour avec les nouvelles colonnes.

---

### 3. Cœur du PluginEngine
#### [NEW] [plugin_base.py](master/core/plugin_base.py)
* Classe mère `PluginBase` avec décorateurs `@route`, `@hook`, `@scheduled`.
* **Adversarial fix #C4** : `__init_subclass__` enregistre la sous-classe dans le registre des décorateurs. `LifecycleManager.on_activate()` collecte les métadonnées (`__plugin_route__`, `__plugin_hook__`, `__plugin_sched__`) via `_collect_decorated(instance)` et les dispatche.
* **Adversarial fix #H2** : `PluginContext` expose un **proxy restreint** (pas de référence `_engine` directe). Accès via `__slots__` et méthodes déléguées : `db_execute(sql)`, `emit_event(event)`, `create_proposal(action)`.

#### [NEW] [plugin_engine.py](master/core/plugin_engine.py)
##### LifecycleManager (machine à états)
* **Adversarial fix #C3** : États = `DECOUVERT→INSTALLED→ACTIVE→DEACTIVATED→UNINSTALL`. ACTIVE et RUNNING **fusionnés** (aucun précédent dans le code existant — verification par Deep Researcher).

##### RouteRegistrar
* Monte sous `/api/plugins/{id}/...`.
* **Adversarial fix #M1** : Unmount via copie de liste `app.router.routes[:] = [...]` + `app.router.on_startup()` pour invalider le cache Starlette.

##### HookBus — Spécification sémantique
* **Adversarial fix #C1** : 4 modes de dispatch préservés :

| Méthode | Sync | Async | Parallélisme | Gestion erreurs | Retour |
|---------|------|-------|-------------|-----------------|--------|
| `call(verb, **kw)` | ✅ exécuté | ❌ ignoré (warning) | Série | `except Exception` par hook | `list[Any]` non-None |
| `call_first(verb, **kw)` | ✅ exécuté | ❌ ignoré | Série, stop au 1er non-None | `except Exception` par hook | `Any \| None` |
| `async_call(verb, **kw)` | ✅ `run_in_executor` | ✅ `await` | Parallèle `asyncio.gather` | `return_exceptions=True` | `list[Any]` non-None |
| `async_call_first(verb, **kw)` | ✅ via async_call | ✅ via async_call | Parallèle gather | `return_exceptions=True` | `Any \| None` |

* Capture `BaseException` (pas seulement `Exception`) pour gérer `SystemExit`/`KeyboardInterrupt`.
* Timeout configurable par hook (défaut 30s).

##### Scheduler
* **Adversarial fix #H1** : Tâches traquées dans `_tasks` ET intégrées au mécanisme de drain (`_active_calls`).
* `stop(plugin_id)` : timeout 10s par tâche. Si une tâche résiste, log erreur + ré-annulation.
* `shutdown()` (nouveau) : arrêt global via lifespan FastAPI.

##### DBAuto
* `CREATE TABLE IF NOT EXISTS <plugin_id>_<table>` puis vérification via `PRAGMA table_info()`.
* **Adversarial fix #M3** : En cas de mismatch colonnes/manifest, log erreur et refuse l'activation.
* Validation SQL au niveau **AST léger** (tokenization des identifiants), pas regex uniquement — pour bloquer ATTACH DATABASE, CTEs, sous-requêtes.
* **Adversarial fix #C2** : Vérifie d'abord la whitelist `__VIGILE_SHARED__` avant la vérification de préfixe.

##### Scanner
* Verrou global `_scan_lock` pour éviter les doubles scans concurrents.
* Nettoyage des orphelins : si un plugin ACTIVE n'a plus de répertoire disque → DEACTIVATED + alerte d'audit.

---

### 4. Rétrocompatibilité & Transition
#### [NEW] [legacy_plugin_wrapper.py](master/core/legacy_plugin_wrapper.py)
* **Adversarial fix #M4** : Vérifie `sys.modules` avant chargement pour éviter le double import. `_FakePluginManager` stocke les références aux fonctions `(hook_name, plugin_name, fn)`.

#### [MODIFY] [plugin_manager.py](master/core/plugin_manager.py)
* Proxy vers `PluginEngine`. Le singleton `plugin_manager` reste accessible. Méthodes historiques redirigées.

#### [MODIFY] [admin.py](master/api/admin.py)
* **Adversarial fix #H5** (frontend) : `GET /api/admin/plugins` retourne désormais :
   ```json
   {
     "loaded_plugins": ["metrics"],
     "plugins": [{
       "id": "metrics", "name": "...", "path": "...", "module": "...",
       "loaded": true, "hooks": [...], "error": null, "version": "1.0.0",
       "description": "...", "enabled": true, "config": {}, "schema": {}
     }]
   }
   ```
* `POST /api/admin/plugins/{id}/toggle` retourne `{ "loaded": true/false }`.
* Accès direct à `_sandbox`/`_wrappers` supprimé → méthodes d'inspection publique.

#### [MODIFY] [main.py](master/main.py)
* Init `PluginEngine` → `hook_bus.subscribe("on_status_report", automation_engine.evaluate_metric_trigger)`.

---

### 5. Migration des 6 Plugins Existants
#### [DELETE] 6 fichiers plats → [NEW] 6 répertoires avec `manifest.json` + `__init__.py`

**Adversarial fix #H3** : Utilitaires partagés déplacés dans `master/core/plugin_helpers.py` :
```python
# master/core/plugin_helpers.py
from master.plugins.systemd_plugin import parse_service_list  # re-export
from master.plugins.docker_plugin import parse_container_list  # re-export
```
Les 4 fichiers qui importent ces utilitaires **ne changent pas** :
* `insights.py:153` → `from master.core.plugin_helpers import parse_service_list`
* `node_manager.py:213` → `from master.core.plugin_helpers import parse_container_list`
* `chat.py:50` → inchangé (via plugin_helpers)
* `services.py:33-35` → inchangé (via plugin_helpers)

**Whitelist `__VIGILE_SHARED__`** :
```python
__VIGILE_SHARED__ = {
    "read": {"plugins", "nodes", "action_proposals", "metrics_snapshots",
             "automation_rules", "automation_logs", "audit_log"},
    "write": {"action_proposals", "metrics_snapshots", "automation_logs", "audit_log"}
}
```

---

## Verification Plan
```powershell
$env:PYTHONPATH="."
python -m pytest tests/test_plugin_engine/ -v           # Nouveaux tests
python -m pytest tests/test_core/test_plugin_manager.py -v  # Dispatch preserved
python -m pytest tests/test_core/test_plugin_isolation.py -v  # Legacy compat
python -m pytest tests/test_plugins/ -v                  # Plugin behavior unchanged
python -m pytest tests/test_api/test_plugins_api.py -v   # Admin API + frontend contract
python -m pytest -m "not integration" -v                 # All unit tests (regression)
```

### Tests adversarial coverage
- **HookBus equivalence** : async_call/call produisent les mêmes résultats qu'avant
- **DB prefix isolation** : rejet des requêtes cross-table, whitelist fonctionne, contournements bloqués
- **Scheduler drain** : drain attend les tâches scheduler avant DEACTIVATED
- **Crash resilience** : SystemExit dans un hook ne tue pas le master
- **Frontend contract** : réponse inclut path/module/error/version

### 5.   Manuel
* `curl /api/admin/plugins` → vérifier champs path/module/version
* `curl POST /api/plugins/_reload` → vérifier logs
* `STATUS_REPORT` via WebSocket → vérifier clean_logs/metrics/discord/slack/automation reçus

---

## Annexe — Traçabilité des 10 Correctifs Adversariaux

| ID | Finding | Provenance | Correctif | Section |
|----|---------|-----------|-----------|---------|
| C1 | HookBus doit préserver 4 dispatch modes | Architecture Critic | Table sémantique + timeouts | §3 HookBus |
| C2 | Prefix DB casse clean_logs/metrics/automation | Implementation Gunner | Whitelist `__VIGILE_SHARED__` + AST validation | §3 DBAuto, §5 whitelist |
| C3 | ACTIVE vs RUNNING sans précédent code | Deep Researcher | Fusion en ACTIVE unique | §3 LifecycleManager |
| C4 | @route décorateur import-time, jamais collecté | Implementation Gunner | `__init_subclass__` + pass `on_activate()` | §3 PluginBase |
| H1 | Tâches Scheduler non trackées par le drain | Deep Thinker | Tracking + timeout + shutdown global | §3 Scheduler |
| H2 | PluginContext._engine leak totale | Deep Thinker | Proxy restreint avec __slots__ | §3 PluginContext |
| H3 | 4 fichiers oubliés dans migration | Implementation Gunner | plugin_helpers.py + table de migration | §5 |
| H4 | Deux tables DB en conflit | Architecture Critic | Fusion plugin_configs+plugin_registry → plugins | §2 |
| H5 | Frontend API contract mismatch | Deep Researcher | Ajout champs path/module/error/version | §4 admin.py |
| M1 | Unmount FastAPI sans cache invalidation | Deep Thinker | Copie liste + reset cache routage | §3 RouteRegistrar |
| M3 | DBAuto + SQLite DDL auto-commit | Implementation Gunner | PRAGMA table_info après CREATE | §3 DBAuto |
| M4 | LegacyWrapper double chargement modules | Implementation Gunner | Vérification sys.modules | §4 legacy_wrapper |
