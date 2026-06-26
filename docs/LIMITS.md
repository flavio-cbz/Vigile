# Vigile — Limites Connues et Surveillance

Ce fichier documente les limites actuelles du projet, les bugs potentiels à surveiller,
et les décisions architecturales qui pourraient devenir problématiques en évoluant.

---

## 🔴 Sécurité — À surveiller

### ~~Clé Ed25519 : permissions non vérifiées à la lecture~~ ✅ Corrigé dans Sprint 5.5
`master/core/security_manager.py:448-456`

La clé était écrite avec `0o600` si générée, mais les permissions d'une clé existante
n'étaient jamais vérifiées. Maintenant, `os.stat()` est appelé au chargement et un WARNING
est émis si les permissions ne sont pas `0o600`.

### ~~Refresh token sans invalidation~~ ✅ Corrigé dans Sprint 4.5
`master/api/auth.py:147-171`

Un nouveau refresh token est émis à chaque appel de `/auth/refresh`, mais l'ancien est invalidé. Les refresh tokens sont stockés en base de données et gèrent la rotation par famille et la détection de vol avec révocation de toute la famille de jetons.

### ~~Pas de force-change du mot de passe admin par défaut~~ ✅ Corrigé dans Sprint 4.5
`master/db/migrations.py:72-75`

Le compte `admin/admin` initial est créé avec le flag `must_change_password = 1`. L'accès aux endpoints de l'API est restreint (erreur 403 `MUST_CHANGE_PASSWORD`) tant que l'utilisateur n'a pas changé son mot de passe via `/api/auth/change-password`.

### ~~Rate limiter : buckets mémoire sans nettoyage~~ ✅ Corrigé dans Sprint 4.5
`master/core/rate_limiter.py:30`

La tâche en arrière-plan périodique `cleanup_expired()` est lancée lors du lifespan de l'application FastAPI pour vider régulièrement les buckets mémoire expirés.

### ~~CORS : `allow_credentials=True` incompatible avec wildcard~~ ✅ Mitigé dans Sprint 5
`master/main.py:238-256`

Solution : middleware HTTP qui echo le header `Origin` du request quand `CORS_ORIGINS=*`,
contournant la limitation navigateur. La config émet aussi un warning de sécurité.
**Risque résiduel :** le `CORS_ORIGINS=*` doit être explicitement changé en production.

---

## 🟡 Robustesse — À corriger avant la prod

### Connexion SQLite unique = bottleneck
`master/db/database.py:14`

Tous les endpoints API, handlers WebSocket, et le heartbeat monitor partagent la même connexion.
SQLite WAL permet les lectures concurrentes mais sérialise les écritures.

**Impact :** un `verify_chain` sur 1M entrées bloque tout.
**Solution court terme :** pool de connexions aiosqlite.
**Solution long terme :** migration vers PostgreSQL (post-Sprint 5).

### ~~Aucune pagination sur `list_nodes` et `verify_chain`~~ ✅ Corrigé dans Sprint 4.5
`master/api/nodes.py` | `master/core/audit.py`

`list_nodes` accepte les paramètres `limit` et `offset` avec des valeurs par défaut et maximales de sécurité. Le journal d'audit est exposé de façon paginée via `/api/audit` et la fonction `verify_chain` permet de limiter le nombre d'entrées scannées avec `max_entries`.

### ~~Aucun système de version de migration DB~~ ✅ Corrigé dans Sprint 4.5
`master/db/migrations.py`

Mise en place d'Alembic pour gérer les versions du schéma de la base de données SQLite. Les migrations successives de création de schéma initial, ajout de la table `refresh_tokens`, et ajout de la colonne `must_change_password` sont désormais scriptées et appliquées automatiquement.

### Plugin hooks async ignorés silencieusement (devenu WARNING)
`master/core/plugin_manager.py:92-97`

Un hook `async def` appelé via `call()` (sync) est ignoré avec un `logger.warning`.
Le plugin apparaît dans `loaded_plugins` mais ses hooks ne s'exécutent jamais.

**Solution documentaire :** toujours utiliser `async_call()` pour les hooks asynchrones.

### ~~Aucune isolation d'erreur dans la boucle heartbeat (LOST→STALE)~~ ✅ Corrigé
`master/core/node_manager.py:424-436`

**Résolu dans Sprint 2.6** — le try/except par nœud est déjà présent dans la deuxième boucle.
Le code était correct avant la détection dans l'audit. La doc LIMITS.md était obsolète.

---

## 🟢 Surveillance à long terme

| Problème | Fichier | Risque |
|----------|---------|--------|
| UUID TEXT PKs = index 9x plus gros qu'un integer | db/models.py:29-32 | Compare last_heartbeat avec time.time() peut donner des off-by-one |
| UUID TEXT PKs = index 9x plus gros qu'un integer | db/models.py:18-92 | Cache inefficace pour l'audit_log à grande échelle |
| Clé Ed25519 auto-générée si MASTER_KEY_PATH inexistant | config.py:72-77 | Un redémarrage avec le fichier manquant = nouvelle clé = tous les Workers rejetés |
| ~~_pending_intents non nettoyé après timeout~~ ✅ Corrigé | node_manager.py | Tracké via _intent_created_at + cleanup par âge |
| Pas de vérification que le Worker Go reçoit le bon type d'intent | node_manager.py:363 | {**intent, "type": "INTENT"} corrige mais dépend du Worker qui parse |
| aiosqlite.execute async peut être appelé après fermeture DB | node_manager.py:406 | Heartbeat monitor peut appeler get_db_conn() pendant un shutdown |
| Pas de limite sur le nombre de connexions WebSocket | node_manager.py:118 | Un Worker malveillant peut ouvrir des connexions illimitées |
| ~~Plugin deduplication absente (reload = double registration)~~ ✅ Corrigé | plugin_manager.py:64 | Les plugins se désinscrivent automatiquement ou évitent la double-inscription. |
| _send() pas protégé contre WebSocketDisconnect | worker_handler.py:441-443 | Exception remonte et peut court-circuiter resolve_intent |

---

## 🧪 Tests manquants documentés

| double enrollment simultané | Nécessite un mock avancé du WebSocket + DB |
| Concurrence : audit sequence collision | Nécessite 2 coroutines appelant `log_action` en parallèle |
| Concurrence : heartbeat + unregister race | Nécessite un timing précis entre 2 coroutines |
| Worker Go : protocole heartbeat/intent | Pas encore de Worker à tester |
| ~~Intégration : API complète sous charge~~ ✅ Corrigé | Mise en place d'un test d'intégration complet `test_api_integration_flow` exécuté via pytest. |

---

## 📐 Décisions architecturales révisées en Sprint 4.5

1. **Passage à un système de migrations versionné** (Alembic) ✅ Fait
2. **Ajout de la rotation de famille des refresh tokens** et détection de vol ✅ Fait
3. **Application de la pagination** sur les nœuds et l'audit ✅ Fait
4. **Correction des violations de Dependency Injection** de la configuration système ✅ Fait
5. **Nettoyage automatique du rate-limiter** via tâche asyncio de lifespan ✅ Fait
6. **Force-change du mot de passe** administrateur par défaut ✅ Fait

---

## 📐 Décisions architecturales et corrections du Sprint 5 (Dette technique)

1. **Passage à des opérations de fichiers asynchrones** ✅ Fait (Phase 1)
   Les lectures/écritures synchrones dans `admin.py` et `main.py` sont déportées sur des threads dédiés via `anyio.to_thread.run_sync` pour ne plus bloquer l'event loop FastAPI.
2. **Optimisation des requêtes SQL et transactions** ✅ Fait (Phase 2)
   Les requêtes N+1 et commits répétés dans `node_manager.py` ont été regroupés dans des transactions uniques. Les requêtes SQL dynamiques ont été paramétrées de manière sécurisée.
3. **Traçabilité totale des mutations** ✅ Fait (Phase 3)
   Les mutations et suppressions orphelines sont désormais journalisées via `log_action`.
4. **Centralisation du Polling UI** ✅ Fait (Phase 4)
   Les `setInterval` multiples ont été remplacés par le hook unifié `usePolling.ts`.
5. **Typage strict Frontend** ✅ Fait (Phase 5)
   Suppression des types `any` injustifiés et renforcement du typage statique TypeScript.
6. **Découpage des composants God** ✅ Fait (Phase 6 & 7)
   Les composants géants (`NodeDetail.tsx`, `LoginPage.tsx`, etc.) ont été découpés en sous-composants, et le code mort a été nettoyé.
7. **Timeout et Paramétrage centralisé (X-03, P-02, B-01, B-02)** ✅ Fait (Phase 11)
   Exposition de tous les timeouts, paramètres LLM et variables d'environnement dans les `Settings` globaux et exclusion des imports de `settings` au niveau module.
8. **Séparation des Prompts Système** ✅ Fait (Phase 11)
   Les prompts du LLM sont externalisés dans des fichiers `.md` sous `master/core/prompts/`.
9. **Contraintes et Defaults DB (S-02, S-03)** ✅ Fait (Phase 11)
   Sécurisation avec contraintes CHECK sur les statuts et valeurs par défaut robustes dans la migration de base de données.

10. **Registre de Plugins (Sprint 5 — Étape 1)** ✅ Fait
    Ajout d'un système de registre d'extensions officiel dynamique (`/api/admin/plugins/registry`) permettant de lister les plugins disponibles, de les télécharger en un clic de manière asynchrone, d'effectuer des vérifications de syntaxe et de contrat AST (fonction `register(pm)`), et de basculer automatiquement sur un registre local résilient (fallback hors-ligne) en cas d'absence d'accès à Internet.

---

## Security Deployment Notes

Vigile must be exposed in production behind an external TLS reverse proxy. The Master is prepared for that deployment model through `ENFORCE_HTTPS`, `TRUSTED_PROXIES`, `COOKIE_SECURE`, `COOKIE_SAMESITE`, and `COOKIE_DOMAIN`; Workers should use a `wss://` master URL once the TLS proxy is in place.

Never commit `.env` files. If `LLM_API_KEY`, `SERVER_SECRET_KEY`, or `JWT_SECRET_KEY` was written to a shared or exposed `.env`, treat it as compromised: revoke the provider key, generate a new value, redeploy, and verify that only `.env.example` is tracked.

