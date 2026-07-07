# Session — Vigile Sprint 9

**Début :** 2026-07-07
**Sprint :** 9 (Moteur de Plugins — Core Engine)
**Phase :** Planification livrable

## Objectifs du sprint

1. Construire `PluginEngine` (Scanner, Registry, LifecycleManager, RouteRegistrar, PageRegistry stub, HookBus async, DBAuto, Scheduler intervalle-only)
2. Spécifier `manifest.json` v1.0 (Pydantic PluginManifest)
3. SDK PluginBase avec PluginContext (db_execute isolé par préfixe `<plugin_id>_`)
4. `LegacyPluginWrapper` bridge pour migrer les 6 plugins existants sans réécriture immédiate
5. Préserver les callers main/ws/automation_engine/admin/chat sans cassure (proxy compat `plugin_manager`)
6. Préserver `_normalize_action_proposal` RESTART_CONTAINER dans chat.py — pas de bypass via `PluginContext.create_proposal`

## Plan d'exécution

Voir `docs/plans/PLAN_SPRINT_9_PLUGIN_ENGINE.md` (rédigé 2026-07-07, 18 sections, 12 jours de travail effectif).

## Non-buts explicites (déférres à Sprint 10/11)

- Pas de frontend (pages/widgets consommés en Sprint 10)
- Pas de marketplace (Sprint 11)
- Pas d'inotify hot-reload (SIGHUP + `/api/plugins/_reload` à la place)
- Pas de CRON parser (`interval` only)
- Pas de reprise du sandbox subprocess (`PluginProcessWrapper`) — sacrifice assumé

## État d'avancement

- ⏳ Planification complète (ce fichier + `docs/plans/PLAN_SPRINT_9_PLUGIN_ENGINE.md`)
- ⏳ Implémentation non démarrée (en attente d'approbation utilisateur)

## Notes

- Le mode hyperplan a été invoqué mais a échoué : 3/4 personnes in joignables via OpenRouter (credits épuisés, fallback models not found), team shutdown before delivery. La cross-critique hostile à 5 angles (YAGNI, migration breakage, schema risk, state machine hazards, zero-trust regression) a été menée en interne par le lead Sisyphus pendant la rédaction, ancrée dans les faits du code (PluginManager 612 LOC, EventBus 57 LOC, callers mappés file:line, chat.py 782-877 normalizer relu, 6 plugins skésmatisés).
- Pré-requis : Sprint 6 (TLS, rotation WORKER_TOKEN) si déploiement Internet ; sinon shippable sur homelab/local.
- Sprint 8 (UI/UX cleanup) reste `❌` — n'est pas un blocker pour Sprint 9 (PluginEngine ne dépend pas de l'UI).
