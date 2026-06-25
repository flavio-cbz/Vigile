# Audit Vigile — 2026-06-23
Sprint en cours : 5

## Résumé exécutif

| Catégorie | Nombre d'occurrences |
|---|---|
| 🔴 Critique | 34 |
| 🟠 Important | 85 |
| 🟡 Signal | 51 |
| 🔍 Manuel requis | 3 |

**Top 3 urgences :**
1. **[T-03] Échecs systématiques dans la suite de tests de LLM Client** ([test_llm_client.py](file:///Users/flavio/Documents/Projets/Youcloud-API/tests/test_core/test_llm_client.py)) : 6 tests unitaires échouent à cause de messages d'erreurs traduits en français non attendus par les assertions d'intégration de langue, et d'appels à l'attribut `.text` sur des objets mocks non implémentés.
2. **[B-04] Appels synchrones bloquants dans des handlers asynchrones** ([admin.py:138](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L138) et [admin.py:399](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L399)) : Écritures de fichiers synchrones (`open()`) directement exécutées dans la boucle d'événements asynchrones du Master, provoquant un blocage de l'I/O concurrent.
3. **[B-05 / B-06] Boucle de mise à jour du cache dans `NodeManager`** ([node_manager.py:268-269](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L268-L269)) : Exécution d'écritures SQL et de validations (`commit()`) dans une boucle `for` avec construction dynamique de requêtes par f-string, posant un fort risque de blocages concurrents, de contention SQLite et d'injection de schéma.

---

## 🔴 Critique (bloquants)

### [T-03] Échecs systématiques dans la suite de tests de LLM Client
- **Fichier :** [test_llm_client.py:71](file:///Users/flavio/Documents/Projets/Youcloud-API/tests/test_core/test_llm_client.py#L71) (et lignes 99, 143, 163, 182, 207)
- **Extrait :**
  ```python
  assert "timed out" in str(exc_info.value).lower()
  ```
- **Problème :** 6 tests unitaires échouent systématiquement dans `test_llm_client.py`. Cela est dû à des assertions sur des chaînes de caractères en anglais alors que les messages d'erreurs réels du module [LLMClient](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/llm_client.py) ont été traduits en français, ainsi qu'à des mocks de réponse de flux HTTP ne possédant pas l'attribut `.text` requis lors de la gestion des erreurs HTTP (provoquant des `AttributeError` et `ValueError` dans les mocks).
- **Action requise :** Mettre à jour les assertions de test pour correspondre aux messages français (ex. `"la requête au service ia a expiré"`) ou adapter les messages renvoyés, et enrichir les objets de simulation (mocks) pour définir l'attribut `.text` afin d'éviter les pannes de validation.

### [B-04] Appel synchrone bloquant dans un endpoint asynchrone
- **Fichier :** [admin.py:138](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L138)
- **Extrait :**
  ```python
  with override_path.open("w", encoding="utf-8") as f:
  ```
- **Problème :** L'ouverture et l'écriture de fichier synchrones s'effectuent directement dans le thread principal de la boucle d'événements asynchrone (`async def`), bloquant l'exécution de toutes les requêtes concurrentes pendant l'I/O disque.
- **Action requise :** Déléguer les écritures/lectures de fichiers à un threadpool via `anyio.to_thread.run_sync` ou utiliser une bibliothèque d'I/O asynchrone comme `aiofiles`.

### [B-04] Appel synchrone bloquant dans un endpoint asynchrone
- **Fichier :** [admin.py:399](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L399)
- **Extrait :**
  ```python
  with open(plugin_path, "wb") as f:
      f.write(content)
  ```
- **Problème :** Écriture de fichier synchrone dans le handler de requête asynchrone `upload_plugin`, entraînant le blocage temporaire du thread de l'application lors du téléversement de fichiers lourds.
- **Action requise :** Remplacer par `aiofiles` ou exécuter le bloc d'écriture via `anyio.to_thread.run_sync`.

### [B-03] Exception interceptée silencieusement (pass sans log)
Il y a **18 occurrences** d'anti-pattern `except Exception: pass` (interceptions génériques et silencieuses) réparties dans les modules critiques. Cela empêche la traçabilité des erreurs système et masque les dysfonctionnements.
- **Fichiers concernés :**
  - [node_manager.py:195](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L195) : Échec de fermeture WebSocket lors de l'arrêt du serveur.
  - [node_manager.py:463](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L463) : Échec de fermeture WebSocket d'un nœud révoqué.
  - [node_manager.py:555](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L555) : Échec de fermeture WebSocket d'un nœud désactivé.
  - [node_manager.py:643](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L643) : Échec de fermeture lors du lockdown.
  - [node_manager.py:663](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L663) : Échec d'enregistrement d'une connexion active.
  - [insights.py:118](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/insights.py#L118) : Échec de parsing du cache JSON des services.
  - [insights.py:125](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/insights.py#L125) : Échec de parsing du cache JSON des conteneurs.
  - [insights.py:569](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/insights.py#L569) : Échec lors du calcul d'alertes CPU/Mem.
  - [insights.py:581](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/insights.py#L581) : Échec lors de la détection de processus.
  - [database.py:56](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/database.py#L56) : Échec lors de la fermeture des connexions SQLite.
  - [env.py:32](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/alembic/env.py#L32) : Échec d'import de configuration de migration.
  - [auth.py:181](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py#L181) : Exception étouffée lors du hachage de sécurité factice.
  - [chat.py:767](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L767) : Échec de chargement de l'historique de chat.
  - [admin.py:313](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L313) : Échec de lecture des manifestes de plugins.
  - [admin.py:416](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L416) : Échec de parsing JSON de configuration plugin.
  - [nodes.py:516](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/nodes.py#L516) : Échec de récupération de métriques de nœuds.
  - [worker_handler.py:494](file:///Users/flavio/Documents/Projets/Youcloud-API/master/ws/worker_handler.py#L494) : Échec de lecture des reconnexions de nœuds.
  - [worker_handler.py:677](file:///Users/flavio/Documents/Projets/Youcloud-API/master/ws/worker_handler.py#L677) : Échec de fermeture de connexion WebSocket.
- **Action requise :** Remplacer les clauses `pass` par un appel de journalisation approprié (`logger.warning` ou `logger.exception`), éventuellement restreindre le type d'exception capturée (ex. `json.JSONDecodeError` au lieu de `Exception`).

### [B-05] Boucle de requêtes SQL unitaires (Risque N+1 et lock DB)
- **Fichier :** [node_manager.py:268-269](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L268-L269)
- **Extrait :**
  ```python
  await db.execute(query, params)
  await db.commit()
  ```
- **Problème :** Mise à jour asynchrone individuelle de chaque nœud en base de données avec validation (`commit()`) immédiate dans une boucle de rafraîchissement périodique du cache. Cela multiplie les écritures disque et bloque les transactions concurrentes sur SQLite.
- **Action requise :** Valider la transaction (`commit`) uniquement en dehors/après la boucle de traitement des nœuds.

### [B-06] Interpolation de chaînes dans les requêtes SQL (Risque d'injection)
- **Fichier :** [node_manager.py:267](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L267) (et `416`, `594`, `619` ; ainsi que [audit.py:81](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/audit.py#L81))
- **Extrait :**
  ```python
  query = f"UPDATE nodes SET {', '.join(fields)} WHERE id = ?"
  ```
- **Problème :** Construction dynamique de requêtes SQL via interpolation f-string. Bien que les valeurs réelles soient passées via des placeholders (`?`), cette pratique de concaténation de colonnes/tables expose le schéma à de futures régressions ou injections.
- **Action requise :** Valider explicitement tous les noms de colonnes via une liste blanche stricte avant interpolation ou utiliser un constructeur de requête structuré.

### [S-02] Colonne status sans contrainte CHECK au niveau de la DB
- **Fichier :** [001_initial_schema.py:145](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/alembic/versions/001_initial_schema.py#L145)
- **Extrait :**
  ```python
  sa.Column("status", sa.String(), nullable=False, server_default="PENDING")
  ```
- **Problème :** Le champ stocke l'état d'avancement des requêtes et propositions d'actions sans validation au niveau de la base de données. Des valeurs erratiques pourraient être insérées en DB si l'ORM ou le validateur d'API est contourné.
- **Action requise :** Ajouter une contrainte CHECK SQLite pour limiter les valeurs acceptées aux états autorisés : `PENDING`, `APPROVED`, `REJECTED`, `EXECUTED`, `FAILED`.

### [PERF-02] asyncio.Queue sans taille maximale (maxsize)
- **Fichier :** [database.py:25](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/database.py#L25)
- **Extrait :**
  ```python
  self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue()
  ```
- **Problème :** Le pool de connexions asynchrone SQLite utilise une file d'attente sans limite de taille, pouvant engendrer une forte consommation mémoire sous haute charge concurrentielle.
- **Action requise :** Fixer une taille maximale au pool en passant un paramètre `maxsize` (ex. `10` ou `20`).

---

## 🟠 Important (maintenabilité, performance)

### [F-05] any TypeScript non justifié dans le Frontend
- **Occurrences :** **27 occurrences** détectées.
- **Fichiers clés :**
  - [formatAudit.ts:7](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/utils/formatAudit.ts#L7) (`details?: any;`)
  - [Sidebar.tsx:297](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/layout/Sidebar.tsx#L297) (`const renderLink = (item: any) => {`)
  - [NodeDetail.tsx:37](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/NodeDetail.tsx#L37) (`const OfflineInsightCard: React.FC<{ insight: any; ... }>`)
- **Problème :** Court-circuite la vérification statique de types de TypeScript, augmentant la probabilité de bugs en production.
- **Action requise :** Définir des interfaces TypeScript strictes ou typer les structures de données génériques avec `unknown` / `Record<string, unknown>`.

### [F-07] Composants God (> 250 lignes)
Il y a **12 composants** dépassant le seuil de 250 lignes de code, réduisant la lisibilité et la testabilité de l'interface.
- **Fichiers concernés :**
  - [NodeDetail.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/NodeDetail.tsx) (832 lignes)
  - [SettingsPage.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/SettingsPage.tsx) (657 lignes)
  - [Sidebar.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/layout/Sidebar.tsx) (587 lignes)
  - [Dashboard.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/Dashboard.tsx) (530 lignes)
  - [LoginPage.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/LoginPage.tsx) (460 lignes)
  - [TrendChart.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/dashboard/TrendChart.tsx) (443 lignes)
  - [ProposalsPage.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/ProposalsPage.tsx) (397 lignes)
  - [NodeSettingsTab.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/dashboard/NodeSettingsTab.tsx) (289 lignes)
  - [ServersPage.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/ServersPage.tsx) (285 lignes)
  - [PluginsPage.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/PluginsPage.tsx) (268 lignes)
- **Action requise :** Découper ces composants en sous-composants réutilisables ou externaliser l'état et les effets de rendu dans des Hooks React personnalisés (Custom Hooks).

### [B-01] Accès aux variables d'environnement hors de config.py
- **Occurrences :**
  - [secret_loader.py:53](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/secret_loader.py#L53) (`value = os.environ.get(env_var)`) et ligne 58.
  - [migrations.py:120](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/migrations.py#L120) (`must_change = 1 if os.getenv("TESTING") == "true" else 0`)
- **Problème :** Contournement du module de configuration centralisé, rendant la configuration globale plus difficile à tracer et à surcharger pour les tests.
- **Action requise :** Importer `settings` de `master.config` et configurer ces options dans la classe globale `Settings`.

### [B-02] Importation de settings dans core/ ou api/
- **Fichier :** [auth.py:21](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py#L21) (`from master.config import settings`)
- **Fichier :** [deps.py:73](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/deps.py#L73) et ligne 200.
- **Problème :** Importation directe de l'instance globale `settings` au sein de la logique métier, couplant le code et empêchant l'injection de dépendances de configuration lors de l'exécution de tests unitaires.
- **Action requise :** Injecter `settings` dans les signatures des routes/fonctions FastAPI via `Depends(get_settings)`.

### [G-01] Erreurs Go ignorées via l'opérateur underscore
- **Occurrences :** **19 occurrences** détectées.
- **Fichiers clés :**
  - [connection.go:118](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/connection.go#L118) (`wc.workerToken, _ = success["worker_token"].(string)`)
  - [connection.go:139](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/connection.go#L139) (`challenge, _ := challengeMsg["challenge"].(string)`)
  - [containers.go:75](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/containers.go#L75) (`id, _ := c["Id"].(string)`)
- **Problème :** Le fait d'ignorer systématiquement les vérifications d'assertions de type ou de parsing JSON en Go peut faire crasher le worker ou injecter des valeurs à zéro (`""`, `0`) sans alerte.
- **Action requise :** Valider l'état `ok` lors des assertions de type Go (ex: `val, ok := val.(string); if !ok { ... }`).

### [G-06] Fonctions du worker sans propagation de context.Context
- **Occurrences :** **14 fonctions** détectées.
- **Fichiers clés :**
  - [connection.go:62](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/connection.go#L62) (`func (wc *WorkerConn) Connect() error`)
  - [connection.go:187](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/connection.go#L187) (`func (wc *WorkerConn) RunOperational() error`)
  - [containers.go:29](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/containers.go#L29) (`func dockerAPI(method, path string, body io.Reader)`)
- **Problème :** Impossible d'annuler ou d'interrompre proprement des opérations bloquantes de socket ou de commandes système en cas de signal d'arrêt (SIGINT/SIGTERM).
- **Action requise :** Ajouter `ctx context.Context` comme premier argument de ces signatures de fonctions et l'utiliser dans les appels réseau/processus.

### [X-03] Constantes de configuration réseau/I/O en dur
- **Occurrences :**
  - [llm_client.py:70](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/llm_client.py#L70) (`timeout: int = 30,`)
  - [node_manager.py:721](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L721) (`timeout: float = 30.0,`)
  - [containers.go:26](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/containers.go#L26) (`Timeout: 30 * time.Second,`)
- **Problème :** Délais d'expiration codés en dur, empêchant l'adaptation fine du comportement sur des homelabs à faible bande passante ou sous forte charge.
- **Action requise :** Exposer ces variables via `config.py` (Master) ou par des variables d'environnement (Worker).

### [X-06] Dépendances installées non whitelistées
- **Fichier :** [requirements.txt](file:///Users/flavio/Documents/Projets/Youcloud-API/requirements.txt)
- **Dépendances :** `itsdangerous`, `python-multipart`, `bcrypt`
- **Fichier :** [package.json](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/package.json)
- **Dépendance :** `react-router`
- **Problème :** Bien que nécessaires, ces librairies ne figurent pas dans la liste officielle des dépendances autorisées de l'architecture Vigile.
- **Action requise :** Soumettre ces dépendances à une validation de sécurité et les ajouter à la liste blanche d'architecture du projet.

---

## 🟡 Signal (style, TODOs, prompts)

### [F-01] Styles inline et classes Tailwind arbitraires
- **Fichiers :** [CardSkeleton.tsx:12](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/ui/CardSkeleton.tsx#L12) (`style={{ width, height }}`), [TopBar.tsx:147](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/layout/TopBar.tsx#L147) (`bg-[#6366f1]`), [Sidebar.tsx:477](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/layout/Sidebar.tsx#L477) (`text-[#2dd4bf]`), [LoginPage.tsx:298](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/LoginPage.tsx#L298) (`bg-[#0a0a0f]`).
- **Problème :** Entrave le support correct du mode sombre et la cohérence visuelle.
- **Action requise :** Migrer ces styles vers des variables ou classes CSS définies dans le système de design globale.

### [F-02] Magic numbers dans timers
- **Occurrences :**
  - [NotifBell.tsx:35](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/layout/NotifBell.tsx#L35) (`20000` ms de rafraîchissement)
  - [TimeAgo.tsx:57](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/primitives/TimeAgo.tsx#L57) (`30000` ms)
- **Action requise :** Centraliser les délais d'actualisation de l'UI dans un fichier de constantes.

### [F-06] console.log / console.warn oublié
- **Fichier :** [useNodeEvents.ts:41](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/hooks/useNodeEvents.ts#L41) (`console.warn('SSE connection error, will retry');`)
- **Action requise :** Remplacer par un logger conditionnel actif uniquement en environnement de développement.

### [B-07] Magic strings pour les états métier du backend
- **Fichier :** [action_proposal.py:34](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/action_proposal.py#L34) (`status: str = "PENDING"`)
- **Fichier :** [node_manager.py:47](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L47) (`PENDING = "PENDING"`)
- **Action requise :** Déclarer ces états métier sous forme d'une classe d'énumération (`enum.Enum` ou `StrEnum`).

### [B-08] Fonctions sans annotation de type
- **Fichiers :** [audit.py:67](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/audit.py#L67) (`def compute_entry_hash(...)`), [security_manager.py:240](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/security_manager.py#L240) (`def verify_ed25519_signature(...)`)
- **Action requise :** Ajouter des annotations de types complètes (paramètres et type de retour).

### [B-09] Mutations DB sans enregistrement dans l'audit log
- **Fichiers :** [node_manager.py:594](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L594) (`UPDATE nodes`), [admin.py:570](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L570) (`DELETE FROM plugin_configs`)
- **Problème :** Actions destructives ou modificatrices de données critiques non enregistrées dans la table `audit_log`.
- **Action requise :** Appeler systématiquement `log_action(...)` pour consigner l'opération.

### [B-10] Imports différés au sein des fonctions
- **Fichiers :** [config.py:89](file:///Users/flavio/Documents/Projets/Youcloud-API/master/config.py#L89) (`import logging`), [main.py:95](file:///Users/flavio/Documents/Projets/Youcloud-API/master/main.py#L95) (`import json`)
- **Action requise :** Déplacer tous les modules standards en haut du fichier source.

### [A-01] Duplication de noms de fonctions entre couches Core et API
- **Occurrences :**
  - `verify_chain` dans [audit.py:177](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/audit.py#L177) vs `nodes.py:412`
  - `generate_join_token` dans [security_manager.py:161](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/security_manager.py#L161) vs `nodes.py:269`
  - `revoke_node` dans [node_manager.py:437](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L437) vs `nodes.py:560`
  - `configure_node` dans [node_manager.py:483](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L483) vs `nodes.py:672`
- **Problème :** Homonymie risquant d'induire en erreur les développeurs lors des imports.
- **Action requise :** Différencier les noms (ex. préfixer par `api_` ou utiliser des noms plus explicites sur l'API).

### [P-01] Prompts système LLM codés en dur dans Python
- **Fichiers :** [chat.py:155](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L155), [chat.py:158](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L158), [chat.py:813](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L813), [structured_llm.py:73](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/structured_llm.py#L73)
- **Problème :** Les invites systèmes de l'IA (prompts) sont écrites en dur dans le code, rendant leur ajustement et versionnage complexe sans déployer le backend.
- **Action requise :** Déporter les prompts dans des fichiers Markdown versionnés dans le dossier `prompts/`.

### [P-02] Paramètres d'appel de modèles d'IA en dur
- **Fichiers :** [llm_client.py:203](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/llm_client.py#L203) (`"model": self.model`), [chat.py:167](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L167) (`temperature=0.3`), [chat.py:830](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L830) (`temperature=0.1`), [admin.py:233](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L233)
- **Action requise :** Configurer et charger ces paramètres via les options de configuration globale (`config.py`).

### [S-03] Migration de base de données ALTER TABLE sans valeur DEFAULT
- **Fichier :** [migrations.py:48](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/migrations.py#L48) (et lignes `51`, `54`, `57`, `60`)
- **Extrait :**
  ```python
  await db.execute("ALTER TABLE nodes ADD COLUMN insight_profile TEXT")
  ```
- **Problème :** L'ajout de colonnes sur des tables existantes sans clause `DEFAULT` peut poser des soucis d'incompatibilité et de manipulation de données `NULL` en production.
- **Action requise :** Configurer une valeur par défaut dans la clause `ALTER TABLE` ou via Alembic.

---

## 📊 Métriques Git

### M-01 : Hot spots (fichiers les plus modifiés)
Liste des fichiers ayant subi le plus grand nombre de commits au sein du dépôt :
- [deps.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/deps.py) : 12 modifications
- [node_manager.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py) : 10 modifications
- [nodes.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/nodes.py) : 10 modifications
- [worker_handler.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/ws/worker_handler.py) : 9 modifications
- [main.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/main.py) : 9 modifications
- [security_manager.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/security_manager.py) : 9 modifications
- [plugin_manager.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/plugin_manager.py) : 9 modifications
- [audit.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/audit.py) : 9 modifications
- [config.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/config.py) : 9 modifications
- [auth.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py) : 9 modifications

### M-02 : Ratio ajout/suppression (dernier sprint)
- **Ratio insertions/suppressions :** `17025 insertions / 14091 suppressions = 1.21` (Seuil d'alerte : 10).
Le ratio est sain, reflétant un refactoring et un nettoyage approfondi du code mort lors des récentes contributions.

### M-03 : Commits récents sans tests associés
Commits récents impactant le code source de production sans intégrer de modifications dans le dossier des tests (`tests/`) :
- `52fa731` feat(dashboard): insight-first loading + FleetGrid component
- `40c19a1` fix(dashboard): CSS variables, preference persistence, kill auto-open, ProposalCard badge
- `d0b66ef` refactor: remove AI-generated slop, clean comments/docstrings, and refactor Go worker connection/stats/enrollment helpers
- `f8e79c7` fix(ci/worker): resolve Go test compilation error and eliminate redundant CI formatting checks
- `a4ed73a` chore(frontend/build): compile production build files and update master/static/
- `8ee37bd` feat(frontend/ui): implement premium layouts, refactor pages and custom UI controls
- `d7bfcef` feat(frontend/core): clean up styles, update store states and translation files
- `70dd9d7` fix(worker): clean up container handling and add WebSocket client unit tests
- `78be01d` chore(repo): clean up codemaps, omo folders, and update CI/pre-commit config
- `71940d8` style(backend): add noqa F821 for intentional lazy LLM type hints

---

## 🔍 Nécessite revue humaine

### DOC-03 : Tests de régression pour les scénarios limites de LIMITS.md
Vérifier manuellement l'intégration de tests couvrant les limites listées dans [LIMITS.md](file:///Users/flavio/Documents/Projets/Youcloud-API/docs/LIMITS.md) :
- *Double enrôlement simultané concurrent* (exclusion mutuelle SQLite lors de l'enregistrement de jeton).
- *heartbeat + unregister race condition* (WebSocket coupé au moment même de l'enregistrement d'état).

### DOC-01 : Écart de documentation des API Routes
- Il y a **48 routes d'API** actives déclarées dans le code (Master).
- Cependant, seulement **9 routes clés** sont mentionnées et décrites dans le [README.md](file:///Users/flavio/Documents/Projets/Youcloud-API/README.md).
- Écart : 39 routes non documentées à intégrer pour la complétude de la documentation d'architecture.

### D-02 : Audit manuel des CVEs (Vulnérabilités de sécurité Python)
- `pip-audit` n'étant pas disponible au sein de l'environnement d'exécution de l'audit technique, une revue de sécurité manuelle des versions déclarées (telles que `bcrypt==4.0.1`, `itsdangerous==2.2.0`, `python-multipart==0.0.20`) doit être initiée par l'équipe.

---

## ✅ Points positifs

- **[T-01] Excellente couverture des modules critiques :** La suite de tests unitaires atteint une couverture de **97%** sur le gestionnaire de sécurité ([security_manager.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/security_manager.py)), **97%** sur l'authentification ([auth.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py)) et **98%** sur le cycle de vie de la DB ([database.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/database.py)), dépassant largement le seuil minimum de 95%.
- **[T-02] Aucun test skip ou xfail permanent :** Aucun test de la suite active n'est éludé ou marqué comme dysfonctionnel de manière statique.
- **[D-01] Versions strictes :** Les dépendances Python déclarées dans `requirements.txt` sont toutes épinglées avec des versions strictes (`==`).
- **[S-01] Idempotence DB :** Toutes les créations de tables initiales possèdent la clause `CREATE TABLE IF NOT EXISTS`.
- **[D-04] Worker standardisé :** Le worker de Vigile repose uniquement sur le compilateur Go 1.23 standard et sa bibliothèque standard (stdlib only), réduisant la surface d'attaque logicielle.
