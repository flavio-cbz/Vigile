# Vigile Audit — Rapport d'exécution des corrections (2026-08-04)

**Statut global :** ✅ Terminé — toutes les corrections validées.
**Suite de tests :** 579 passed, 2 deselected (`-m "not integration"`), 0 échec.
**compileall :** master/ + worker/ → OK.

---

## Corrections appliquées (APPLIED)

### Couche API

| Fichier | Corrections |
|---------|-------------|
| `master/api/nodes.py` | Imports `typing` nettoyés (`Annotated`/`List` inutilisés), `DEMO_NODE_METRICS`/`ARCH_MAP` importés au module au lieu des imports inline, `import json` inline supprimé. |
| `master/api/nodes_helpers.py` | Consolidation helpers / suppression code mort (53 lignes touchées). |
| `master/api/nodes_management.py` | Corrections mineures de gestion nœuds (24 lignes). |
| `master/api/nodes_models.py` | Corrections modèles Pydantic (28 lignes). |
| `master/api/nodes_operations.py` | Corrections opérations nœuds (13 lignes). |
| `master/api/admin.py` | Nettoyage + commentaire threat model sur le `compile()`/`exec()` dynamique (accès strictement rôle-gated maintenu) ; `_PATCH_ALLOWED_FIELDS` séparé de `_VALID_NODE_FIELDS` (223 lignes). |

### Couche core

| Fichier | Corrections |
|---------|-------------|
| `master/core/insights.py` | Profilage en arrière-plan sur connexion dédiée (`_generate_profile_with_own_connection`, fallback pool) au lieu de la connexion request-scoped ; `observation_ready` basé sur `window.cpu_ready` ; suppression limite 30 jours pour l'analyse disque ; correctif **RuntimeError** (queue pool liée à un autre event loop en environnement de test) ajouté au fallback. |
| `master/core/llm_client.py` | Corrections client LLM (33 lignes). |
| `master/core/node_manager.py` | Corrections machine à états / registres WS (177 lignes). |
| `master/core/audit.py` | `AuditAction.LOCKDOWN` ajouté (chaîne de hash — action manquante). |
| `master/core/hook_bus.py` | `asyncio.ensure_future` → `asyncio.create_task` ; `unregister()` prunes `_metrics` (fuite mémoire sur hot-reload) ; `except Exception` → `except BaseException` dans `call()`/`call_first()` (un `KeyboardInterrupt`/`SystemExit` ne doit pas être avalé). |
| `master/core/circuit_breaker.py` | `reset()` → async sous `_lock` (atomicité) ; appels sync offloadés via `run_in_executor` (ne bloquent plus l'event loop) ; commentaire `record_success` (streak semantics). |
| `master/core/plugin_engine.py` | Dead code retiré (`use_sandbox`, `_is_class_based`, `plugin_dir`, `init_file`) ; `initialize()` commit en try/finally ; EOF subprocess → futures résolues en erreur (pas de hang) ; pop `sys.modules` si `exec_module` échoue ; **zip-slip** + traversal `manifest.id` validés (`Path.resolve`/`is_relative_to`) ; `PYTHONPATH` forcé, `HOME` via `expanduser` ; `shutdown()` sans doublons (`set` union) ; classe morte `_Lifecycle` supprimée (zéro référence, note AGENTS.md mise à jour) ; version sentinelle `1.0.0` → `0.0.0`. |
| `master/core/structured_llm.py` | Renommage `max_retries` → `max_attempts` (appelant `chat_stream.py:712` + tests mis à jour) ; boucle de stripping `<think>` **imbriqués** (le regex non-greedy simple laissait des blocs) ; cap `MAX_RETRY_FEEDBACK_PAIRS = 5` avec trim des paires les plus anciennes (croissance bornée du contexte LLM). |
| `master/core/outbox.py` | Claim anti-double-dispatch `processed=2` + `rowcount` (deux sweeps concurrents ne re-dispatchent plus la même entrée) ; reset du claim en échec ; `replay_unprocessed()` reset les claims orphelins (crash mid-dispatch) ; no-op `retry_count = retry_count` supprimé ; sémantique at-least-once documentée (échec per-handler → REJECTED si non contenu, pas de schéma DB). |
| `master/core/scheduler.py` | Double-décrément du compteur `_active_callbacks` supprimé (le `finally` décrémente sur tous les chemins) ; `start()` idempotent (cancel du task existant avant re-création) ; docstring corrigée. |
| `master/core/worker_query_port.py` | `get_stats`/`list_services`/`list_containers`/`read_logs` déléguent à `query()` (suppression duplication, un seul chemin d'envoi read-only). |
| `master/core/plugin_lifecycle.py` | `update_runtime_state` wrapé dans `transaction()` (aiosqlite pas en autocommit — conflit de séquence possible sur la connexion partagée). |
| `master/core/investigation_manager.py` | DI corrigée : `insights` injecté via constructeur/`set_insights()` au lieu d'import `master.api.deps` (violation DI) ; statut `'skipped'` persisté tel quel (était forcé à `'failed'`). |
| `master/core/security_manager.py` | `ExpiredTokenError(SecurityError, ValueError)` — MRO double pour compatibilité `except ValueError` (worker_handler.py:452) tout en restant typable ; `jwt.ExpiredSignatureError` → `ExpiredTokenError` explicite ; `load_or_generate_master_key` → `O_EXCL` + re-read si course (deux processus ne génèrent plus deux clés différentes) ; docstring `sign_policy_bundle` corrigée (sorted-keys ≠ RFC 8785 JCS). |
| `master/core/alert_engine.py` | **Fuites mémoire** : `cleanup_orphaned_alerts` purge les clés composites `f"{nid}:{alert_name}"` du rate limiter (le `pop(nid)` nu ne matchait jamais) ; **auto-résolution** `node_reboot_detected` (uptime stable) et `node_connection_flap` (fenêtre < 5) — ces alertes ne se résolvaient jamais ; **doublon de seuil** `cpu_high_load` supprimé (identique à `cpu_load_per_core_high` → doublon d'alertes, frontend référence le second). |

### Worker

| Fichier | Corrections |
|---------|-------------|
| `worker/stats.go` | Corrections stats worker (171 lignes, vérifiées statiquement — pas de toolchain Go locale). |

---

## ALREADY-FIXED / REJECTED (aucune modification)

| Fichier | Finding | Verdict | Justification |
|---------|---------|---------|---------------|
| `master/core/proposal_dispatcher.py` | PD-1 : dispatch orphelins au startup | **ALREADY-FIXED** | Sweep de réconciliation déjà présent (`master/lifespan.py:183-207`). |
| `master/core/proposal_dispatcher.py` | PD-2 : `send_intent()` public | **REJECTED** | Le stub RuntimeError est un piège volontaire pour forcer `WorkerQueryPort`/`ApprovedProposalDispatcher`. |
| `master/core/proposal_dispatcher.py` | PD-3 : code mort | **REJECTED** | Zéro caller, volontairement conservé. |
| `master/core/proposal_autoexpire.py` | AE-1 : propositions jamais expirées | **REJECTED** | Faux positif : `insights` crée des statuts APPROVED directement, jamais PENDING → hors périmètre du TTL. |

## SKIP (noté, hors périmètre — refactor architectural)

- `connection_registry.py` / `insights_analyzer.py` / sandbox RCE plugins — refactors architecturaux, signalés uniquement (pas de refactor pendant un audit de corrections).

---

## Vérifications

- **compileall** : `PYTHONPATH="." .venv/bin/python -m compileall -q master/ worker/` → exit 0.
- **Suite complète** : `python -m pytest -m "not integration"` → **579 passed, 2 deselected, 0 failed** (3 runs ; 2 échecs transitoires diagnostiqués et corrigés, voir ci-dessous).
- **Tests ciblés** (hook_bus, plugin_engine, crash_resilience, scheduler, cron, structured_llm, outbox, security, investigation, node_manager, db_migration, db_auto) → 147 passed.
- **Alert engine** : `-k "alert"` → 2 passed ; investigation_manager + rate_limiter → 11 passed.
- **Pool + insights (repro interférence)** : `test_pool_health.py` + `test_insights_saturation.py` → 23 passed.
- **Non-régression garantie** : `proposal_dispatcher.py`, `proposal_autoexpire.py`, `worker_handler.py` intacts (diff vide).

## Régression détectée pendant la campagne (corrigée)

Le nouveau `_generate_profile_with_own_connection()` (insights.py) échouait en suite complète avec `RuntimeError: Queue is bound to a different event loop` : la queue du pool module-level est liée au premier event loop qui la touche ; en tests (loop frais par test), un test antérieur via `init_db` liait la queue, puis la tâche background de profil plantait. Le fallback ne capturait que `TimeoutError`. **Correctif** : `RuntimeError` ajouté à la clause d'exception du fallback (connexion appelante utilisée). Test `test_stale_profile_triggers_reprofile_while_serving_insights` passe ensuite en isolation ET en suite complète.

Un flake pré-existant (`test_plex_fastapi_mounted_routes`, pollution cross-loop, fichiers plex modifiés avant l'audit) est apparu une fois puis ne s'est pas reproduit (3e run complet : 579 passed).
