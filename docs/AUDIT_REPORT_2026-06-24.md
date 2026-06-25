# Rapport d'Audit de Dette Technique - Projet **Vigile**

**Date :** 2026-06-24
**Sprint Courant :** Sprint 5
**Périmètre :** Backend (`master/`), Frontend (`frontend/src/`), Worker (`worker/`)
**Statut global :** 🟠 Amélioration requise (Dette technique identifiée)

---

## 📌 Résumé de l'Audit

Ce rapport présente une analyse exhaustive et non invasive de la dette technique du projet **Vigile** (Fleet Manager pour homelabs). L'analyse a été menée conformément aux exigences définies dans le catalogue du projet, en exploitant des vérifications automatisées et manuelles.

### Synthèse des Anomalies par Sévérité

| Sévérité | Nombre | Description / Impacts |
| :--- | :--- | :--- |
| 🔴 **Critique** | **2** | Bloquants immédiats, échecs de tests unitaires ou blocage d'I/O critique. |
| 🟠 **Important** | **12** | Anti-patterns majeurs nuisant à la maintenabilité, la robustesse, la modularité ou la sécurité. |
| 🟡 **Signal** | **13** | Écarts stylistiques, magics, imports tardifs, typages manquants ou points d'attention modérés. |
| 🔍 **Manuel requis** | **4** | Éléments nécessitant une investigation manuelle, des tests de concurrence ou de performance. |

---

## 🔴 Critique (bloquants)

### [T-03] Échecs systématiques dans la suite de tests de LLM Client
- **Fichier :** [test_llm_client.py](file:///Users/flavio/Documents/Projets/Youcloud-API/tests/test_core/test_llm_client.py)
- **Constat :** **6 échecs critiques** systématiques lors du lancement des tests unitaires :
  - `test_complete_timeout`, `test_complete_connect_error`, `test_complete_text_access_exception`
  - `test_stream_http_error`, `test_stream_timeout_and_connect_errors`, `test_stream_text_access_exception`
- **Problème :** Dysfonctionnements induits par des assertions s'attendant à des messages d'erreur en anglais ("timed out", "connection failed"), alors que le code de production renvoie des messages d'erreur traduits en français, ainsi que des propriétés d'attributs manquantes sur les mocks (`AttributeError: '_MockStreamResponse' object has no attribute 'text'`).
- **Action requise :** Mettre à jour les assertions de test pour correspondre aux messages français de l'API et compléter les structures des mocks de test dans [test_llm_client.py](file:///Users/flavio/Documents/Projets/Youcloud-API/tests/test_core/test_llm_client.py).

### [B-04] Appel synchrone bloquant dans un endpoint asynchrone
- **Fichiers :**
  - [admin.py:138](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L138) :
    ```python
    with override_path.open("w", encoding="utf-8") as f:
        json.dump(...)
    ```
  - [admin.py:399](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L399) :
    ```python
    with open(plugin_path, "wb") as f:
        f.write(content)
    ```
- **Problème :** L'écriture de fichiers sur disque bloque la boucle d'événements (Event Loop) de FastAPI, ce qui peut paralyser l'ensemble du serveur Master en cas de forte concurrence ou de latence disque.
- **Action requise :** Remplacer par des écritures asynchrones avec `aiofiles` ou encapsuler l'exécution synchrone via `anyio.to_thread.run_sync`.

---

## 🟠 Important (maintenabilité, performance)

### [B-03] Exception interceptée silencieusement (pass sans log)
- **Occurrences :** 18 occurrences détectées.
- **Fichiers clés :**
  - [admin.py:313](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L313), [admin.py:416](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L416)
  - [auth.py:182](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py#L182)
  - [chat.py:767](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L767)
  - [insights.py:118](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/insights.py#L118), [insights.py:125](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/insights.py#L125)
  - [node_manager.py:195](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L195)
- **Problème :** Des blocs `except Exception: pass` silencieux cachent des dysfonctionnements système majeurs et empêchent le débogage.
- **Action requise :** Remplacer par des logs explicites (`logger.exception`) ou attraper uniquement des exceptions spécifiques et documentées.

### [B-05] Boucle de requêtes SQL unitaires (N+1 SQL / Lock DB)
- **Fichier :** [node_manager.py:268-269](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L268-L269)
- **Problème :** Mise à jour du cache d'état des conteneurs/services en effectuant une écriture + commit individuel à chaque tour de boucle, risquant de bloquer SQLite (`database is locked`).
- **Action requise :** Exécuter toutes les requêtes de la boucle au sein d'une transaction unique globale avec un seul commit final.

### [B-06] Interpolation de chaînes dans les requêtes SQL
- **Occurrences :** 6 occurrences détectées.
- **Fichiers concernés :**
  - [node_manager.py:269](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L269), [node_manager.py:418](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L418), [node_manager.py:642](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L642), [node_manager.py:667](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L667), [node_manager.py:970](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L970)
  - [audit.py:81](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/audit.py#L81)
- **Problème :** Utilisation de f-strings pour concaténer des morceaux de requêtes SQL, contournant la protection contre les injections.
- **Action requise :** Refactoriser pour utiliser des paramètres nommés SQLite (`?`).

### [B-09] Mutations DB sans enregistrement dans l'audit log
- **Occurrences :** 4 occurrences détectées.
- **Fichiers concernés :**
  - [admin.py:570](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L570) (`DELETE FROM plugin_configs WHERE plugin_id = ?`)
  - [demo.py:29](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/demo.py#L29) (`DELETE FROM action_proposals`)
  - [node_manager.py:472](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L472) (`DELETE FROM nodes WHERE id = ?`)
  - [node_manager.py:642](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L642) (`UPDATE nodes SET ...`)
- **Problème :** Suppression/Modification de configurations en base de données sans log d'audit synchrone.
- **Action requise :** Consigner systématiquement ces mutations en base avec un appel immédiat à `log_action()`.

### [F-03] Polling non centralisé (multiples `setInterval` locaux)
- **Constat :** Bien qu'un hook centralisé [usePolling.ts](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/hooks/usePolling.ts) ait été créé pour mutualiser les timers de polling, plusieurs composants continuent d'utiliser des appels `setInterval` manuels et isolés :
  - [NotifBell.tsx:35](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/layout/NotifBell.tsx#L35)
  - [AddNodeModal.tsx:66](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/modals/AddNodeModal.tsx#L66)
  - [TimeAgo.tsx:57](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/primitives/TimeAgo.tsx#L57)
  - [InsightCard.tsx:26](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/dashboard/InsightCard.tsx#L26)
  - [TrendChart.tsx:91](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/dashboard/TrendChart.tsx#L91)
  - [HeroBanner.tsx:18](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/dashboard/HeroBanner.tsx#L18)
  - [LoginPage.tsx:137](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/LoginPage.tsx#L137)
  - [NodeDetail.tsx:46](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/NodeDetail.tsx#L46)
- **Action requise :** Refactoriser ces composants pour utiliser systématiquement le hook `usePolling`.

### [F-05] Type any TypeScript non justifié
- **Occurrences :** 27 occurrences détectées (ex: dans `formatAudit.ts`, `Sidebar.tsx`, `LoginPage.tsx`, `useSSE.ts`).
- **Problème :** Affaiblit le typage statique TypeScript et augmente le risque d'erreurs d'exécution UI.
- **Action requise :** Définir des types d'API stricts ou utiliser `unknown`/`Record<string, unknown>`.

### [F-07] Composants God (> 250 lignes)
- **Occurrences :** 10 fichiers concernés :
  - [NodeDetail.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/NodeDetail.tsx) (846 lignes)
  - [SettingsPage.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/SettingsPage.tsx) (657 lignes)
  - [Sidebar.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/layout/Sidebar.tsx) (602 lignes)
  - [Dashboard.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/Dashboard.tsx) (530 lignes)
  - [LoginPage.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/LoginPage.tsx) (460 lignes)
  - [TrendChart.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/dashboard/TrendChart.tsx) (443 lignes)
  - [ProposalsPage.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/ProposalsPage.tsx) (397 lignes)
  - [ServersPage.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/ServersPage.tsx) (353 lignes)
  - [NodeSettingsTab.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/dashboard/NodeSettingsTab.tsx) (289 lignes)
  - [PluginsPage.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/PluginsPage.tsx) (268 lignes)
- **Action requise :** Subdiviser en composants fonctionnels plus petits et extraire la logique d'état complexe dans des Hooks React personnalisés.

### [F-10] Exports non utilisés (code mort)
- **Occurrences :** 7 occurrences réparties dans 4 fichiers :
  - `BannerSkeleton`, `RowSkeleton`, `ChatCardSkeleton`, `ProposalCardSkeleton` dans [CardSkeleton.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/ui/CardSkeleton.tsx)
  - `ServerConfigModal` dans [ServerConfigModal.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/modals/ServerConfigModal.tsx)
  - `useSSE` dans [useSSE.ts](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/hooks/useSSE.ts)
  - `useNodeEvents` dans [useNodeEvents.ts](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/hooks/useNodeEvents.ts)
- **Action requise :** Nettoyer et supprimer ces exports orphelins.

### [G-01] Erreurs Go ignorées via l'opérateur underscore
- **Occurrences :** 20 occurrences détectées (ex: dans `connection.go`, `containers.go`, `services.go`, `enrollment.go`).
- **Problème :** Ignorer les retours d'erreurs ou les assertions de type Go peut masquer des échecs d'assertion silencieux en production et aboutir à des crashes inattendus.
- **Action requise :** Remplacer par des vérifications d'assertion explicites (ex: `val, ok := x.(string); if !ok { ... }`).

### [G-06] Fonctions du worker Go sans propagation de context.Context
- **Occurrences :** 15 fonctions clés détectées (ex: `Connect`, `runEnrollment`, `RunOperational`, `dockerAPI`).
- **Problème :** Les opérations réseau bloquantes ou les appels Docker API ne peuvent pas être annulés dynamiquement lors d'un signal de shutdown.
- **Action requise :** Ajouter `ctx context.Context` en premier argument de ces signatures.

### [X-03] Constantes de configuration réseau/I/O en dur
- **Occurrences :** 2 occurrences
  - [database.py:37](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/database.py#L37) (`timeout=30.0`)
  - [database.py:93](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/database.py#L93) (`timeout=30.0`)
- **Action requise :** Paramétrer les timeouts SQLite à travers le fichier de configuration centralisé `config.py`.

### [X-06] Dépendances installées non whitelistées
- **Backend (Python) :** `bcrypt==4.0.1`, `itsdangerous==2.2.0`, `python-multipart==0.0.20`
- **Frontend (npm) :** `react-router`
- **Action requise :** Soumettre ces dépendances tierces à une revue de sécurité et les documenter dans la liste des dépendances autorisées de l'architecture.

---

## 🟡 Signaux (à surveiller)

### [F-01] Styles inline et classes Tailwind arbitraires
- **Occurrences :** 24 occurrences détectées (ex: `bg-[#6366f1]` dans `TopBar.tsx:147`, `LoginPage.tsx:298`, style inline de `animationDelay` dans `CopilotMessage.tsx:57-59`, style de barre de progression dans `ServersPage.tsx:258`).
- **Action requise :** Remplacer par des classes thématiques ou des tokens CSS du Design System.

### [F-02] Magic numbers dans timers/timeouts de l'interface
- **Occurrences :** 3 occurrences détectées (`NotifBell.tsx:35` à 20s, `TimeAgo.tsx:57` à 30s, `TrendChart.tsx:91` à 30s).
- **Action requise :** Déclarer ces durées dans un fichier de constantes centralisé.

### [F-06] console.log / console.warn oublié
- **Fichier :** [useNodeEvents.ts:46](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/hooks/useNodeEvents.ts#L46) (`console.warn('SSE connection error, will retry');`)
- **Action requise :** Remplacer par une journalisation appropriée en production ou désactiver en build final.

### [B-01] Accès aux variables d'environnement hors de config.py
- **Occurrences :** 3 occurrences
  - [secret_loader.py:53](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/secret_loader.py#L53) (`os.environ.get(env_var)`) et ligne 58.
  - [migrations.py:120](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/migrations.py#L120) (`os.getenv("TESTING") == "true"`)
- **Action requise :** Exposer et lire ces variables d'environnement exclusivement dans `master/config.py`.

### [B-02] Importation de settings dans core/ ou api/
- **Occurrences :** 3 occurrences
  - [auth.py:21](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py#L21) (`from master.config import settings`)
  - [deps.py:73](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/deps.py#L73) et ligne 200.
- **Action requise :** Utiliser l'injection de dépendances de FastAPI pour injecter la configuration dans la route ou la logique métier.

### [B-08] Saisie de types de retour manquants sur les fonctions de routage
- **Occurrences :** 4 fonctions détectées dans la couche API FastAPI sans annotation `-> Type` sur leur type de retour :
  - [auth.py:396](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py#L396) (`async def logout`)
  - [auth.py:437](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py#L437) (`async def change_password`)
  - [nodes_events.py:63](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/nodes_events.py#L63) (`def _next_event`)
  - [chat.py:101](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L101) (`def _demo_event_stream`)
- **Action requise :** Ajouter des types de retour clairs et explicites pour toutes les signatures de fonctions.

### [B-10] Imports différés au sein des fonctions
- **Occurrences :** 12 occurrences (ex: `admin.py:372`, `nodes.py:441`, `config.py:89`, `config.py:109`, `plugin_manager.py:318`, `main.py:95`).
- **Action requise :** Remonter toutes les déclarations d'imports en en-tête des fichiers sources.

### [G-02] Goroutines sans signal de shutdown dans le Worker
- **Occurrences :** 2 occurrences
  - [connection.go:212](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/connection.go#L212) (`go func()`)
  - [main.go:110](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/main.go#L110) (`go func()`)
- **Action requise :** Associer ces lancements de goroutines à un cycle d'annulation via `context.Context` ou un channel de notification de fermeture.

### [G-04] Magic numbers dans l'allocation de tampons / timeouts (Go)
- **Occurrences :** 7 occurrences (ex: `reconnect_test.go:87`, `wsclient.go:89`, `wsclient.go:180`, `wsclient.go:236`, `wsclient.go:254`, `wsclient.go:260`).
- **Action requise :** Utiliser des constantes typées au lieu de buffers alloués dynamiquement en dur (ex: `make([]byte, 16)`).

### [P-01] Prompts système LLM codés en dur dans Python
- **Occurrences :** 5 occurrences
  - [chat.py:155](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L155), ligne 158 et ligne 813.
  - [structured_llm.py:73](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/structured_llm.py#L73) et ligne 80.
- **Action requise :** Déporter les chaînes de texte système LLM dans des fichiers Markdown autonomes dans un sous-dossier `prompts/`.

### [P-02] Paramètres d'appel de modèles d'IA en dur
- **Occurrences :** 4 occurrences
  - [admin.py:233](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L233) (`max_tokens=5`)
  - [chat.py:167](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L167) (`temperature=0.3`) et [chat.py:830](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L830) (`temperature=0.1`)
  - [llm_client.py:203](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/llm_client.py#L203) (`"model": self.model`)
- **Action requise :** Exposer ces variables d'inférence (température, max_tokens, etc.) dans `Settings`.

### [S-02] Colonne status sans contrainte CHECK au niveau de la DB
- **Fichier :** [001_initial_schema.py:145](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/alembic/versions/001_initial_schema.py#L145)
- **Extrait :** `sa.Column("status", sa.String(), nullable=False, server_default="PENDING")`
- **Action requise :** Remplacer le type `String` simple par une contrainte de validation de valeurs (Enum / CHECK constraint) au niveau SQL.

### [S-03] Migration de base de données ALTER TABLE sans valeur DEFAULT
- **Occurrences :** 5 occurrences dans [migrations.py:48-60](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/migrations.py#L48) (ajout des colonnes `insight_profile`, `insight_profile_generated_at`, `cached_services_json`, `cached_containers_json`, `node_group`).
- **Action requise :** Définir une valeur de repli (DEFAULT) lors de l'extension de schéma pour garantir l'absence de valeurs `NULL` indésirables.

### [A-01] Duplication de noms de fonctions
- **Occurrences :** 13 occurrences de noms de fonctions identiques partagés entre différents modules (ex: `verify_chain` dans `core/audit.py` et `api/nodes.py`, `get_node`, `list_nodes`, `register`).
- **Action requise :** Renommer les fonctions (surtout dans la couche API) pour clarifier la sémantique de l'application.

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
- **Ratio insertions/suppressions (20 derniers commits) :** `27082 insertions / 23654 suppressions = 1.14`.
Le ratio est équilibré, indiquant une maintenance saine et des nettoyages rigoureux dans l'historique récent.

### M-03 : Commits récents sans tests associés
Commits récents impactant le code source de production sans intégrer de modifications dans le dossier des tests (`tests/`) :
- `52fa731` feat(dashboard): insight-first loading + FleetGrid component
- `40c19a1` fix(dashboard): CSS variables, preference persistence, kill auto-open, ProposalCard badge
- `d0b66ef` refactor: remove AI-generated slop, clean comments/docstrings, and refactor Go worker connection/stats/enrollment helpers
- `0e79e48` docs: add screenshots to README.md and set dashboard as cover image
- `0bc41c2` chore(docker): remove Caddy proxy and expose Master directly on port 8000
- `f8e79c7` fix(ci/worker): resolve Go test compilation error and eliminate redundant CI formatting checks
- `a4ed73a` chore(frontend/build): compile production build files and update master/static/
- `8ee37bd` feat(frontend/ui): implement premium layouts, refactor pages and custom UI controls
- `d7bfcef` feat(frontend/core): clean up styles, update store states and translation files
- `70dd9d7` fix(worker): clean up container handling and add WebSocket client unit tests

---

## 🔍 Nécessite revue humaine

### DOC-03 : Tests de régression pour les scénarios limites de LIMITS.md
Vérifier manuellement l'intégration de tests couvrant les limites listées dans [LIMITS.md](file:///Users/flavio/Documents/Projets/Youcloud-API/docs/LIMITS.md) :
- *Double enrôlement simultané concurrent* (exclusion mutuelle SQLite lors de l'enregistrement de jeton).
- *heartbeat + unregister race condition* (WebSocket coupé au moment même de l'enregistrement d'état).

### D-02 : Audit manuel des CVEs (Vulnérabilités de sécurité Python)
- `pip-audit` n'étant pas disponible au sein de l'environnement d'exécution de l'audit technique, une revue de sécurité manuelle des versions déclarées (telles que `bcrypt==4.0.1`, `itsdangerous==2.2.0`, `python-multipart==0.0.20`) doit être initiée par l'équipe.

### [PERF-01] Performance de la vérification de la chaîne d'audit
- La fonction `verify_chain` parcourt la table `audit_log` pour recalculer les empreintes cryptographiques successives. Sur une base de données de production volumineuse, ce scan séquentiel peut saturer l'I/O et le processeur du Master.

### [PERF-02] Queue asyncio sans maxsize
- **Fichier :** [database.py:25](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/database.py#L25)
- **Extrait :**
  ```python
  self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue()
  ```
- **Problème :** La file d'attente pour le pool de connexions n'a pas de taille maximale définie (`maxsize=0`), ce qui la rend potentiellement illimitée et peut causer une fuite de ressources.
- **Action requise :** Définir une taille limite (ex: `maxsize=size`) dans le constructeur de `asyncio.Queue`.

---

## ✅ Points positifs

- **[T-01] Couverture sur les modules critiques conforme (>= 95%) :** La suite de tests unitaires atteint une couverture excellente et conforme sur l'ensemble des modules critiques ciblés :
  - **[database.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/database.py) :** **98.0%** de couverture de code (résolution de la dette de couverture sur le gestionnaire de transaction et les rollbacks).
  - **[security_manager.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/security_manager.py) :** **97.0%** de couverture.
  - **[auth.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py) :** **97.0%** de couverture.
- **[T-02] Réactivation réussie des tests d'intégration :** La marque `@pytest.mark.skip` a été supprimée avec succès sur le test d'intégration global `test_api_integration_flow` ([test_integration.py](file:///Users/flavio/Documents/Projets/Youcloud-API/tests/test_api/test_integration.py#L9)). Les tests d'intégration s'exécutent désormais correctement et passent à **100%**.
- **[D-01] Versions strictes :** Les dépendances Python déclarées dans `requirements.txt` sont toutes épinglées avec des versions strictes (`==`).
- **[D-03] Lockfile frontend présent :** Présence de [package-lock.json](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/package-lock.json) qui garantit le verrouillage strict des versions de dépendances côté React.
- **[S-01] Idempotence DB :** Toutes les créations de tables possèdent la clause `CREATE TABLE IF NOT EXISTS`.
- **[D-04] Worker standardisé :** Le worker de Vigile repose uniquement sur le compilateur Go 1.23 standard et sa bibliothèque standard (stdlib only), réduisant la surface d'attaque logicielle.
- **[P-03] Robustesse des tests de régression LLM :** Plus de 83 assertions et appels LLM de test sont présents au sein de la suite de tests pour valider le comportement du client IA.
- **[X-09] Code sans TODO/FIXME orphelins :** Aucune occurrence de TODO ou FIXME sans responsable n'a été détectée dans le périmètre audité.

---
*Rapport généré par la tâche d'audit automatique.*
*Catalogue de référence : DEBT_CATALOG.md*
*Aucune modification n'a été effectuée dans le code source.*
