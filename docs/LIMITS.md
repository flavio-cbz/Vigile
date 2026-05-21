# Vigile — Limites Connues et Surveillance

Ce fichier documente les limites actuelles du projet, les bugs potentiels à surveiller,
et les décisions architecturales qui pourraient devenir problématiques en évoluant.

---

## 🔴 Sécurité — À surveiller

### Clé Ed25519 : permissions non vérifiées à la lecture
`master/core/security_manager.py:113-117`

La clé est écrite avec `0o600` si elle est générée, mais les permissions d'une clé existante
ne sont jamais vérifiées. Une restauration de backup avec `0o644` expose la clé sans warning.

**Quand ça deviendra un problème :** premier déploiement avec backup/restore.
**Solution :** ajouter `os.stat(key_path).st_mode & 0o777` et logger un WARNING si pas `0o600`.

### ~~Refresh token sans invalidation~~ ✅ Corrigé dans Sprint 4.5
`master/api/auth.py:147-171`

Un nouveau refresh token est émis à chaque appel de `/auth/refresh`, mais l'ancien est invalidé. Les refresh tokens sont stockés en base de données et gèrent la rotation par famille et la détection de vol avec révocation de toute la famille de jetons.

### ~~Pas de force-change du mot de passe admin par défaut~~ ✅ Corrigé dans Sprint 4.5
`master/db/migrations.py:72-75`

Le compte `admin/admin` initial est créé avec le flag `must_change_password = 1`. L'accès aux endpoints de l'API est restreint (erreur 403 `MUST_CHANGE_PASSWORD`) tant que l'utilisateur n'a pas changé son mot de passe via `/api/auth/change-password`.

### ~~Rate limiter : buckets mémoire sans nettoyage~~ ✅ Corrigé dans Sprint 4.5
`master/core/rate_limiter.py:30`

La tâche en arrière-plan périodique `cleanup_expired()` est lancée lors du lifespan de l'application FastAPI pour vider régulièrement les buckets mémoire expirés.

### CORS : `allow_credentials=True` incompatible avec wildcard
`master/main.py:142-148`

Si `CORS_ORIGINS=*` est défini, le navigateur bloque les credentials (Authorization header)
car `Access-Control-Allow-Origin: *` avec `Access-Control-Allow-Credentials: true` est interdit par la spec.

**Quand ça deviendra un problème :** premier déploiement avec frontend.
**Solution :** ajouter une validation dans `config.py` qui refuse le wildcard si `allow_credentials=True`.

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
| _pending_intents` non nettoyé après timeout | node_manager.py:370-373 | Stale entries dans le dict si le futur est déjà résolu ailleurs |
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
