# Algorithms & Smart Features — Master Node

## 1. Phase 0 — Service Classification (`master/core/insights.py`)

Classifie automatiquement chaque conteneur Docker et service systemd par catégorie, seuil CPU, et label lisible.

- **LLM path** : envoie la liste des conteneurs (nom + image) et services au LLM central avec un schéma structuré (`NodeServiceClassification` avec `ServiceCategory` enum). Le LLM attribue une catégorie, un label et un seuil CPU à chaque entrée.
- **Fallback déclaratif** : tables de regex `(pattern, category, label, threshold)` triées par priorité. La première règle qui match gagne → pas de if/elif, pas de band-aid `_is_llm_related`.
- **Réutilisable** : `classify_node_services()` peut être appelée indépendamment du profil pour d'autres usages (UI, suggestions, runbooks).

## 2. Phase 1 — Profilage de Nœud (`master/core/insights.py`)

Construit un `NodeProfile` avec processus lourds, baseline RAM, et label de contexte.

- Utilise la classification Phase 0 pour remplir `known_heavy_processes`.
- Le LLM peut aussi générer le label de contexte (`context_label`) et la baseline RAM.
- Stocké en DB dans `nodes.insight_profile` ; recalculé tous les 7 jours ou à la détection d'un nouveau conteneur.

## 3. Phase 2 — Insights Temps Réel (`master/core/insights.py`)

Produit des cartes d'insight (CPU, RAM, Disque) pour l'opérateur.

### CPU
- Compare `cpu_percent` actuel contre les seuils des processus lourds classifiés.
- Sélectionne le processus avec le **seuil le plus élevé** dépassé (pas le premier trouvé).
- Seuils : `cpu_percent > 75` → `warning`, `> 40` → `info`, sinon `ok`.
- Coupable identifié → headline "Activité intense · {label}" + détail avec nom du conteneur/service.

### RAM
- Compare `mem_percent` contre la baseline du profil (`baseline_ram_percent`).
- Seuils : `> 90` → `warning` (risque OOM), `> baseline` → `info`, sinon `ok`.
- Swap utilisé signalé si > 50 Mo.

### Disque — Régression Linéaire
- Calcule la pente de croissance du disque (`slope` en Go/jour) via **régression linéaire** sur les 24 dernières heures.
- Formule : `slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x²)`.
- Minimum 5 snapshots et 30 min d'écart pour éviter le bruit.
- Extrapole le nombre de jours restants : `days_left = free_gb / slope`.
- Seuils : `days_left < 14` → `critical`, `< 60` → `warning`, sinon `ok`.
- Croissance négative ignorée (fixée à 0).

## 4. Phase 3 — Diagnostic IA (`master/core/insights.py`)

Analyse d'anomalie à la demande via le LLM central.

- Envoie métriques actuelles + liste des services/conteneurs au LLM.
- Reçoit un `DiagnosticReport` structuré : `headline`, `explanation`, `suggested_action`.
- 2 tentatives (`max_retries=2`) ; si échec, retourne un message d'indisponibilité.

## 5. Audit Trail — Chaîne de Hash SHA256 (`master/core/audit.py`)

Registre d'audit append-only avec chaîne cryptographique.

- Chaque entrée contient `previous_hash`, `entry_hash`, `sequence` (monotonic).
- `entry_hash = SHA256(previous_hash | sequence | timestamp | action | user_id | node_id | details_json)`.
- Entrée genesis : `previous_hash = "0" * 64`.
- Vérification par `verify_chain()` qui rejoue tout le calcul et détecte toute altération.
- Verrou asyncio pour éviter les collisions de séquence en concurrence.
- 40+ types d'actions auditées (login, proposals, intents, automations, nœuds, plugins, etc.).

## 6. Security Manager — Crypto & RBAC (`master/core/security_manager.py`)

### JOIN_TOKEN
- HMAC-SHA256 sur payload base64url : `sig = HMAC(server_secret, payload_b64, SHA256)`.
- Payload : `node_id`, `expires_at` (30 min), `single_use`, `jti` (UUID).
- Comparaison en temps constant (`hmac.compare_digest`) pour prévenir les timing attacks.
- Hashé en DB via `SHA256(token)` — jamais stocké en clair.

### Ed25519 — Challenge/Response
- Challenge : 32 bytes aléatoires (`secrets.token_bytes`), base64url.
- Vérification : `Ed25519PublicKey.verify(signature, challenge)` via `cryptography`.
- Utilisé pendant le handshake d'enrôlement WebSocket.

### WORKER_TOKEN (JWT HS256)
- JWT avec `sub`=node_id, `type`="worker", `rotation_due`, `exp`, `jti`.
- Secrets isolés par type de token via HMAC dérivé (`_jwt_worker_secret`, `_jwt_access_secret`, `_jwt_refresh_secret`).
- Vérification asynchrone avec contrôle de révocation en DB.

### User JWT (Access + Refresh)
- Access token : 1h TTL, contient `role` pour RBAC.
- Refresh token : 24h TTL, avec `family_id` pour la détection de vol.
- `REFRESH_THEFT_DETECTED` : si un refresh token est réutilisé après rotation → famille entière révoquée + audit.

### Mots de passe
- Bcrypt via `passlib` (`CryptContext`).

### Clé Maître Ed25519
- Générée ou chargée depuis le disque au démarrage.
- Permissions vérifiées (doit être `600`).
- Utilisée pour l'identité cryptographique du Master.

## 7. Node Manager — Machine à États (`master/core/node_manager.py`)

### State Machine
```
PENDING → ENROLLING → UNCONFIGURED → CONNECTED → LOST → STALE
                                    ↘ DISABLED
```
- 18 transitions valides définies dans `VALID_TRANSITIONS`.
- Chaque transition persistée en DB, notifiée via `event_bus` + callbacks (automation engine).
- `transition_state()` valide la transition avant exécution ; `ValueError` si invalide.

### Heartbeat Monitor
- Tâche fond qui vérifie les heartbeats toutes les 30s.
- `lost_threshold` (300s = 5 min) sans heartbeat → `LOST`.
- `stale_threshold` (86400s = 24h) en LOST → `STALE`.
- Nettoyage des intents en attente toutes les ~10 cycles.

### Cache Updater
- Met à jour le cache services/conteneurs toutes les 300s pour les nœuds connectés.
- Détection de nouveaux conteneurs → régénération automatique du profil (avec cooldown de 24h).
- Profil expiré après 7 jours → régénération forcée.

### Intent Dispatch
- Envoi d'intent via WebSocket avec Future-based pattern.
- Timeout configurable (30s par défaut).
- Max age des intents en attente : 300s (configurable), nettoyage automatique.
- Résolu via `resolve_intent()` quand le Worker répond.

### Lockdown
- Fermeture de toutes les connexions WebSocket en cas de compromission.
- Code close `4433` (SECURITY_COMPROMISE).

## 8. Automation Engine — Moteur de Règles (`master/core/automation_engine.py`)

Système Trigger → Condition → Action évalué en temps réel.

### Triggers
- `metric_threshold` : se déclenche quand une métrique (cpu_percent, mem_percent, disk_percent, etc.) dépasse un seuil avec opérateur (gt/lt/gte/lte/eq).
- `node_state` : se déclenche quand un nœud transite vers un état spécifique.

### Conditions
- `always` : pas de condition (défaut).
- `time_window` : exécution uniquement dans une plage HH:MM-HH:MM.
- Filtrage par `target_node_id` et `target_group` (vérifié en DB).

### Actions
- `send_intent` : envoie une commande au Worker (ex: `RESTART_CONTAINER`, `RESTART_SERVICE`).
- `call_webhook` : POST HTTP vers une URL externe avec template de body.
- `log_message` : écrit dans `automation_logs` (sans effet de bord).

### Safeguards
- Cooldown par règle+nœud (300s par défaut) pour éviter les boucles.
- Audit log sur chaque déclenchement (`AUTOMATION_TRIGGERED`).
- Échec d'action → `FAILED` (les autres actions continuent).

## 9. Rate Limiter — Fenêtre Glissante (`master/core/rate_limiter.py`)

Limitation de requêtes par IP + endpoint.

- `max_requests` (60) dans une `window_seconds` (60s).
- Implémentation : liste de timestamps par clé, nettoyée à chaque check.
- Middleware FastAPI pour toutes les routes (sauf WebSocket).
- Dependency injectable par endpoint pour des limites spécifiques.
- Support X-Forwarded-For avec whitelist de proxies de confiance (`trusted_proxies`).
- Tâche de nettoyage périodique (toutes les 300s).

## 10. Structured LLM — Génération Structurée (`master/core/structured_llm.py`)

Force le LLM à produire du JSON valide contre un schéma Pydantic.

- Génère le JSON schema du modèle Pydantic.
- Construit un system prompt avec le schéma.
- Boucle de retry : si validation échoue, renvoie l'erreur au LLM avec `max_retries` tentatives.
- Zéro dépendance externe (pattern inspired by Instructor).

## 11. LLM Client — Client OpenAI-Compatibles (`master/core/llm_client.py`)

Client HTTP natif pour API de chat.

- Support streaming SSE avec yield token-by-token.
- Support tool calling (parse `tool_calls` des réponses).
- Compatible tout fournisseur : OpenAI, Ollama, vLLM, OpenRouter, NVIDIA NIM, etc.
- Timeouts : 30s requête, 120s stream.
- Messages d'erreur en français, pas de fuite d'exceptions.

## 12. Plugin Manager — Hooks & Sandbox (`master/core/plugin_manager.py`)

Système de plugins avec hooks nommés et exécution sandboxée.

- Hooks synchrones (`call`) et asynchrones (`async_call`) dispatchés par nom.
- Sandbox optionnelle via sous-processus isolé (`PluginProcessWrapper`).
- Drain des appels actifs au déchargement.
- GTT : si un plugin asynchrone est appelé via `call()` synchrone → ignoré avec warning.

## 13. Event Bus — Pub/Sub Interne (`master/core/event_bus.py`)

Bus d'événements asynchrone pour la communication in-process.

- Topics : `node.state`, `node.deleted`, etc.
- Files d'attente bornées (200 events max) par abonné.
- Ring buffer de replay (200 derniers événements) pour les nouveaux abonnés.
- SSE endpoint s'abonne pour les mises à jour temps réel.

## 14. Secret Loader — Docker Secrets (`master/core/secret_loader.py`)

Chargement des secrets avec fallback Docker secrets (`{VAR}_FILE`).

## 15. WebSocket Handler — Protocole Deux Phases (`master/ws/worker_handler.py`)

### Phase d'Enrôlement
1. `ENROLLMENT_REQUEST` : Worker envoie join_token + public_key Ed25519.
2. `ENROLLMENT_CHALLENGE` : Master répond avec 32 bytes aléatoires.
3. `ENROLLMENT_RESPONSE` : Worker signe le challenge avec sa clé privée.
4. `ENROLLMENT_SUCCESS` : Master valide la signature, consomme le token, émet un WORKER_TOKEN JWT.

Chaque étape a un timeout strict de 30s.

### Phase Opérationnelle
- HEARTBEAT / HEARTBEAT_ACK toutes les 30s.
- INTENT / INTENT_RESULT (dispatch d'actions).
- STATUS_REPORT (métriques CPU/RAM/Disk).
- Fermeture propre avec codes spécifiques 44xx.

### Sécurité
- Validation HMAC du JOIN_TOKEN avant toute étape.
- Vérification Ed25519 de la signature.
- Détection de duplication de token → révocation des deux connexions.
- Vérification de la révocation en DB.
- Vérification HTTPS si `enforce_https=True`.
- Lockdown en cas de compromission.

## 16. Customisation de la Génération Automatique de Secrets (`master/config.py`)

Si `SERVER_SECRET_KEY` ou `JWT_SECRET_KEY` sont vides en développement, le Master génère automatiquement des secrets via `secrets.token_hex(32)`.

## 17. Human-in-the-Loop — Cycle d'Approbation (`master/core/action_proposal.py`)

Machine à états des propositions d'action :
```
PENDING → APPROVED → EXECUTED | FAILED
PENDING → REJECTED
```
- Chaque transition est validée.
- Persisté en DB avec horodatage, utilisateur approveur, raison du rejet.
- Résultat d'exécution stocké (`result_json`).

## 18. Détection de Nouveaux Conteneurs (`master/core/node_manager.py`)

Dans le `cache_updater` : compare les conteneurs actifs actuels contre les `known_heavy_processes` du profil. Si un nouveau conteneur roulant n'est pas dans le profil, déclenche une régénération (cooldown 24h pour éviter le spam LLM).

## 19. Repérage de Contexte (`_guess_context` dans `master/core/insights.py`)

Heuristique simple basée sur le hostname et les conteneurs pour déterminer le rôle du serveur : "Serveur Web / Applicatif", "Base de Données", "Homelab Médias & Stockage", ou "Serveur général".

## 20. RBAC — Contrôle d'Accès (`master/core/enums.py`, `master/api/deps.py`)

Hiérarchie de rôles : `viewer` (1) < `operator` (2) < `admin` (3).
Chaque endpoint est protégé par `require_role("operator", "admin")` qui compare le niveau de l'utilisateur contre le niveau requis.

## 21. Plugins — Alerting, Cleanup, Parseurs

### Metrics Plugin (`master/plugins/metrics_plugin.py`)
- **Normalisation STATUS_REPORT** : accepte les formats plat et `{"metrics":{...}}`, valide via `MetricsSnapshot` (20+ champs avec contraintes `ge`/`le`).
- **Persistance** : insère les métriques dans `metrics_snapshots` à chaque STATUS_REPORT.

### Systemd Plugin (`master/plugins/systemd_plugin.py`)
- **`parse_service_list()`** : valide et parse la sortie LIST_SERVICES en `list[ServiceInfo]`.
- **`parse_service_status()`** : pareil pour STATUS_SERVICE.

### Docker Plugin (`master/plugins/docker_plugin.py`)
- **`parse_container_list()`** : valide et parse la sortie LIST_CONTAINERS (id, name, image, state, ports).

### Slack Alert (`master/plugins/slack_alert.py`)
- **Seuils CPU/MEM** : si `cpu_percent > 85%` ou `mem_percent > 85%`, envoie un payload Slack Blocks via webhook.
- **Configuration DB** : seuils et URL configurables via `plugin_configs`.

### Discord Alert (`master/plugins/discord_alert.py`)
- Même pattern que Slack Alert, envoie vers Discord webhook (`{"content": ...}`).

### Clean Logs (`master/plugins/clean_logs.py`)
- **Détection disque plein** : si `disk_percent > 85%`, crée une `ActionProposal` (RUN_COMMAND) pour nettoyer `/var/log/*.gz`, etc.
- **Anti-doublon** : vérifie qu'il n'y a pas déjà une proposal PENDING pour ce nœud avant d'en créer une nouvelle.
- **Human-in-the-Loop** : la proposal est risquée `LOW`, en attente d'approbation opérateur.

## 22. Plugin Worker — Sandbox Subprocess (`master/core/plugin_worker.py`)

- **JSON-RPC sur stdin/stdout** : communication entre le processus parent et le plugin sandboxé via lignes JSON.
- **DatabaseProxy** : délègue les appels `execute()`/`commit()` du processus enfant vers le parent via JSON-RPC, avec `CursorProxy` pour simuler un curseur sqlite3.
- **Lecteur stdin thread-safe** : utilise un thread lecteur + `asyncio.Queue` pour ne pas bloquer l'event loop sur stdin.

## 23. LoopBoundLock — Verrou par Boucle d'Événements (`master/core/lock.py`)

- Crée un `asyncio.Lock` par boucle d'événements (clé = objet loop).
- Nettoie les boucles fermées pour éviter les fuites mémoire.
- Empêche l'erreur "attached to a different loop" dans les tests.

## 24. Migrations Idempotentes (`master/db/migrations.py`)

- **Création de tables** : `CREATE TABLE IF NOT EXISTS` pour toutes les tables.
- **Ajout dynamique de colonnes** : vérifie `PRAGMA table_info()` et ajoute les colonnes manquantes (8 colonnes possibles : `insight_profile`, `cached_services_json`, `cached_containers_json`, `node_group`, `disabled`, `version`, `worker_version`, `disks_json`).
- **Migration FK legacy** : détecte et supprime l'ancienne FK `join_tokens.node_id -> nodes.id` via rename+drop pour permettre les tokens indépendants.
- **Migration plugins** : renomme `plugin_configs` → `plugins` avec colonnes version/status/manifest_hash.
- **Genesis audit** : insère l'entrée genesis (sequence=1, previous_hash="0"*64) qui ancre toute la chaîne de hash.
- **Admin par défaut** : crée admin/admin si aucun utilisateur n'existe.
- **Plugins par défaut** : insère metrics, systemd, docker comme activés.
- **Alembic stamping** : crée `alembic_version` et stamp "008".

## 25. Auto-Génération de Secrets (`master/config.py`)

- **Dev mode** : si `SERVER_SECRET_KEY` ou `JWT_SECRET_KEY` sont vides et `allow_insecure=True`, utilise `"dev_secret_key_only"` / `"dev_jwt_key_only"`.
- **Production** : si `allow_insecure=False`, lève `ValueError` → impossible de démarrer sans config.
- **HTTPS enforcement** : `allow_insecure=False` force `enforce_https=True` et `cookie_secure=True`.
- **apply_overrides()** : mutation runtime des paramètres LLM (base_url, api_key, model) sans I/O disque. Masque les clés inchangées avec `"••••••••"`.

## 26. Per-Endpoint Rate Limits (`master/api/rate_limits.py`)

6 constantes de limite par minute par IP :
- `LOGIN_LIMIT=5`, `REFRESH_LIMIT=30`, `KICKSTART_LIMIT=10`, `GENERATE_JOIN_LIMIT=10`, `WORKER_CONTROL_LIMIT=100`, `CHAT_LIMIT=30`, `ADMIN_LIMIT=200`, `GLOBAL_LIMIT=300`.

---

*Document généré le 2026-07-08. ~110+ comportements intelligents catalogués. Mettre à jour lors de l'ajout de nouvelles fonctionnalités.*
