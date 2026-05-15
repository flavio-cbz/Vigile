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

### Refresh token sans invalidation
`master/api/auth.py:147-171`

Un nouveau refresh token est émis à chaque appel de `/auth/refresh`, mais l'ancien reste valide
jusqu'à son expiration (24h par défaut). Fenêtre de vulnérabilité où deux tokens coexistent.

**Quand ça deviendra un problème :** vol de refresh token détecté mais impossible à révoquer.
**Solution :** table `refresh_tokens` avec `revoked` flag (Sprint 5).

### Pas de force-change du mot de passe admin par défaut
`master/db/migrations.py:72-75`

Le compte `admin/admin` est créé avec un simple warning log. Aucune contrainte technique
pour forcer le changement au premier login.

**Quand ça deviendra un problème :** déploiement en prod sans lecture des logs de démarrage.
**Solution :** ajouter un flag `must_change_password` dans la table `users`.

### Rate limiter : buckets mémoire sans nettoyage
`master/core/rate_limiter.py:30`

La méthode `cleanup_expired()` existe mais n'est jamais appelée. Chaque combinaison
`(IP, route)` stocke ses timestamps indéfiniment.

**Quand ça deviendra un problème :** après des semaines de production avec trafic varié.
**Solution :** appeler `cleanup_expired()` périodiquement (tâche asyncio dans le lifespan).

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

### Aucune pagination sur `list_nodes` et `verify_chain`
`master/api/nodes.py:332-343` | `master/core/audit.py:162-169`

`list_nodes` retourne TOUS les nœuds sans limite. `verify_chain` scanne toute la table audit_log.

**Impact :** avec 10 000 nœuds ou 1M entrées audit, ces endpoints deviennent inutilisables.
**Solution :** ajouter `limit`/`offset` sur les endpoints REST, et un `max_entries` optionnel sur `verify_chain`.

### Aucun système de version de migration DB
`master/db/migrations.py:23-43`

`run_migrations()` est un idempotent `CREATE TABLE IF NOT EXISTS`. Pas de version tracking,
pas d'`ALTER TABLE`, pas de rollback.

**Impact :** toute modification de schéma nécessite une intervention manuelle sur chaque base prod.
**Solution :** table `schema_version` + scripts de migration numérotés.

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
| `REAL` timestamps perdent la précision sub-ms | `db/models.py:29-32` | Compare `last_heartbeat` avec `time.time()` peut donner des off-by-one |
| `UUID TEXT` PKs = index 9x plus gros qu'un integer | `db/models.py:18-92` | Cache inefficace pour l'audit_log à grande échelle |
| Clé Ed25519 auto-générée si `MASTER_KEY_PATH` inexistant | `config.py:72-77` | Un redémarrage avec le fichier manquant = nouvelle clé = tous les Workers rejetés |
| `_pending_intents` non nettoyé après timeout | `node_manager.py:370-373` | Stale entries dans le dict si le futur est déjà résolu ailleurs |
| Pas de vérification que le Worker Go reçoit le bon type d'intent | `node_manager.py:363` | `{**intent, "type": "INTENT"}` corrige mais dépend du Worker qui parse |
| `aiosqlite.execute` async peut être appelé après fermeture DB | `node_manager.py:406` | Heartbeat monitor peut appeler `get_db_conn()` pendant un shutdown |
| Pas de limite sur le nombre de connexions WebSocket | `node_manager.py:118` | Un Worker malveillant peut ouvrir des connexions illimitées |
| Plugin deduplication absente (reload = double registration) | `plugin_manager.py:64` | Charger 2x le même plugin exécute ses hooks 2x |
| `_send()` pas protégé contre `WebSocketDisconnect` | `worker_handler.py:441-443` | Exception remonte et peut court-circuiter `resolve_intent` |

---

## 🧪 Tests manquants documentés

| Test | Pourquoi |
|------|----------|
| Concurrence : double enrollment simultané | Nécessite un mock avancé du WebSocket + DB |
| Concurrence : audit sequence collision | Nécessite 2 coroutines appelant `log_action` en parallèle |
| Concurrence : heartbeat + unregister race | Nécessite un timing précis entre 2 coroutines |
| Worker Go : protocole heartbeat/intent | Pas encore de Worker à tester |
| Intégration : API complète sous charge | Pas de fixture pytest pour lancer/arrêter Uvicorn |

---

## 📐 Décisions architecturales à réviser en Sprint 5

1. **Migration du single-connection SQLite** vers PostgreSQL ou pool aiosqlite
2. **Remplacement du rate-limiter mémoire** par Redis ou base de données
3. **Ajout d'une file d'attente LLM** pour éviter de surcharger le provider
4. **Passage à un système de migrations versionné** (Alembic-like)
5. **Ajout de métriques Prometheus** pour surveiller les temps de réponse et les goulots
