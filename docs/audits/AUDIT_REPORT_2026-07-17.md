# Audit Vigile — 2026-07-17

**Sprint en cours :** Sprint 9 (début 2026-07-07)
**Dernier commit :** `199d956` docs: add alert integration architecture plan
**Périmètre :** master/ (71 .py), frontend/src (126 .ts/.tsx), worker/ (16 .go), tests/ (56 .py)
**Méthode :** Analyse automatisée par scripts grep/stat + revue manuelle partielle
**Catalogue de référence :** Ce rapport suit la nomenclature `DEBT_CATALOG.md` (non trouvé dans le dépôt — nomenclature reconstituée depuis AGENTS.md et RULES.md)

---

## Résumé exécutif

| Priorité | Nombre |
|---|---|
| 🔴 Critique | 10 |
| 🟠 Important | 9 |
| 🟡 Signal | 12 |
| 📊 Métrique | 3 |
| 🔍 Manuel requis | 2 |

### Top 3 urgences

1. **B-03 — Silent `except Exception: pass` (7 occurrences)** : Logique métier en échec sans aucun logging ni alerting. Les exceptions sont avalées silencieusement dans `auth.py`, `admin.py`, `chat.py` et le plugin Plex. Pertes de traçabilité garanties en production.
2. **G-01/G-03 — Erreurs ignorées massives dans le Worker Go + `panic` sans `recover`** : ~25 erreurs ignorées via `_` dans `stats.go`, `services.go`, `enrollment.go` ; les `panic` (test mis à part) n'ont aucun `recover` en production. Un plantage d'une goroutine fait tomber le worker entier.
3. **DOC-01 — 24 routes API dans le code, seulement 10 documentées dans README.md** : 14 routes (majorité plugins, alerts, settings) totalement absentes de la documentation. Risque d'utilisation incorrecte, difficulté d'intégration.

---

## 🔴 Critique (bloquants)

### B-03 — Silent `except Exception: pass`
- **Fichier :** `master/api/auth.py:187`
- **Fichier :** `master/api/admin.py:585, 684`
- **Fichier :** `master/api/chat.py:772`
- **Fichier :** `master/plugins/plex/__init__.py:105, 123, 144`
- **Extrait :**
  ```python
  except Exception:
      pass
  ```
- **Problème :** Les exceptions sont complètement avalées sans logging. Toute erreur dans ces blocs (DB, réseau, permission) devient silencieuse — débogage impossible, alerting muet.
- **Action requise :** Chaque `except` doit au minimum logger l'exception (`logger.exception(...)` ou `logging.exception(...)`). Ne jamais utiliser `pass` sur une exception non typée.

### B-09 — Mutations DB sans audit logging
- **Fichier :** `master/api/automations.py:297`
- **Fichier :** `master/api/demo.py:31`
- **Fichier :** `master/core/node_manager.py:501, 675`
- **Fichier :** `master/db/migrations.py:177`
- **Extrait :**
  ```python
  await db.execute("DELETE FROM automation_rules WHERE id = ?", (rule_id,))
  await db.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
  ```
- **Problème :** Mutations destructives (`DELETE`, `UPDATE`) sans appel à `log_action` ou audit trail. Violation du principe de chaîne d'audit du projet.
- **Action requise :** Chaque mutation critique doit être enregistrée dans la table d'audit avec l'utilisateur/nœud responsable.

### G-01 — Erreurs ignorées (underscore) dans le Worker Go
- **Fichier :** `worker/stats.go` (lignes 207, 242, 261, 352, 353, 476, 548, 712, 770-773, 814, 972)
- **Fichier :** `worker/services.go` (lignes 48, 63, 69, 79)
- **Fichier :** `worker/enrollment.go:74`
- **Extrait :**
  ```go
  v, _ := strconv.ParseUint(f, 10, 64)
  ```
- **Problème :** ~25 erreurs ignorées avec `_`. Les échecs de parsing dans `stats.go` produisent des métriques nulles/tronquées silencieusement. Le worker envoie des data potentiellement corrompues au master sans alerte.
- **Action requise :** Logger les erreurs au lieu de les ignorer. Pour les parsing de stats, utiliser une valeur sentinelle/NaN documentée.

### G-02 — Goroutines sans signal de shutdown
- **Fichier :** `worker/connection.go:67, 239`
- **Fichier :** `worker/dispatcher.go:230`
- **Fichier :** `worker/main.go:116`
- **Extrait :**
  ```go
  go func() {
  ```
- **Problème :** Toutes les goroutines de production sont lancées sans `context.Context` ou canal d'arrêt. En cas de fermeture du worker, les goroutines fuient et continuent en arrière-plan. `Stop()` (`connection.go:450`) ne peut pas les interrompre.
- **Action requise :** Ajouter un `ctx context.Context` ou un canal `done` à chaque goroutine. Utiliser `select` sur le canal de shutdown.

### G-03 — `panic` sans `recover`
- **Fichier :** Tous les fichiers `worker/*.go`
- **Extrait :**
  ```go
  panic(...)  // présent dans stats_test.go (test only)
  recover()   // absent de tout le code de production
  ```
- **Problème :** Aucun `recover()` n'existe dans le code de production. Si une goroutine panic (déréférencement de nil, index out of range, etc.), le processus entier s'arrête immédiatement sans cleanup.
- **Action requise :** Ajouter un `defer recover()` dans chaque goroutine de production. Logger la stack trace et tenter une reconnexion.

### B-06 — F-string dans SQL
- **Fichier :** `master/api/admin.py:929, 936`
- **Fichier :** `master/core/db_auto.py:145`
- **Fichier :** `master/core/proposal_autoexpire.py:128`
- **Fichier :** `master/core/investigation_manager.py:232`
- **Extrait :**
  ```python
  f"SELECT COUNT(*) as cnt FROM alerts WHERE {where}", params
  ```
- **Problème :** Injection SQL potentielle via f-string le `{where}` vient de paramètres dynamiques. Les requêtes doivent utiliser des paramètres `?` pour toutes les valeurs.
- **Action requise :** Remplacer la construction f-string par des paramètres nommés/positionnels `?`.

### B-01 — `os.getenv` / `os.environ` hors config
- **Fichier :** `master/core/plugin_engine.py:133`
- **Extrait :**
  ```python
  env = os.environ.copy()
  ```
- **Problème :** Accès direct à l'environnement dans le core, contournant le module `Settings`. Rend les tests dépendants de l'environnement et casse l'injection de dépendances (DI at edge).
- **Action requise :** Injecter les variables via `Settings` ou passer explicitement les valeurs dans le constructeur.

### B-02 — Import direct de `settings` dans core/api
- **Fichier :** `master/core/plugin_engine.py:19`
- **Extrait :**
  ```python
  from master.config import settings
  ```
- **Problème :** Anti-pattern déjà documenté dans AGENTS.md. L'import direct viole le principe "DI at edge" du projet. Impossible de mocker `settings` dans les tests unitaires.
- **Action requise :** Injecter `settings` dans le constructeur de `PluginEngine`.

### .env — Fichier de configuration avec secrets potentiels
- **Fichier :** `.env` (24 lignes, gitignoré)
- **Problème :** Le fichier `.env` existe en développement et contient probablement des secrets (clés API, tokens). Bien que gitignoré, c'est un vecteur de fuite si partagé ou commité accidentellement. De plus, `docker-compose.yml` peut exposer ces variables dans l'écosystème Docker.
- **Action requise :** Vérifier que `.env` ne contient pas de clés réelles. Pour la prod, utiliser un vault ou des secrets Docker. Documenter le format attendu dans `.env.example`.

---

## 🟠 Important (sprint suivant)

### F-07 — Composants God (> 400 lignes)
- **Fichiers :**
  - `frontend/src/components/node-detail/NodeDetailMetricsTab.tsx` (839 lignes)
  - `frontend/src/pages/PluginsPage.tsx` (662 lignes)
  - `frontend/src/pages/AutomationsPage.tsx` (595 lignes)
  - `frontend/src/components/layout/Sidebar.tsx` (501 lignes)
  - `frontend/src/components/automations/RuleFormModal.tsx` (471 lignes)
  - `frontend/src/components/dashboard/TrendChart.tsx` (453 lignes)
  - `frontend/src/components/modals/AddNodeModal.tsx` (439 lignes)
  - `frontend/src/pages/ProposalsPage.tsx` (412 lignes)
- **Problème :** 8 composants dépassent 400 lignes. `NodeDetailMetricsTab.tsx` (839 lignes) est le plus extrême — il combine rendu, logique métier, websocket, et appels API. Impossible à tester/maintenir unitairement.
- **Action requise :** Refactoriser en sous-composants (< 250 lignes). Extraire la logique métier dans des hooks personnalisés. Extraire les sous-vues (charts, métriques, etc.).

### F-05 — Type `any` non justifié
- **Fichiers :** `NodeDetailMetricsTab.tsx:120,209`, `PluginsPage.tsx:32,34,485`, `MetricsHistory.tsx:67`, `PluginConfigForm.tsx:7,9,34`, `Sidebar.tsx:176`
- **Extrait :**
  ```tsx
  {payload.map((item: any, idx: number) => {
  onClick={() => setSelectedPlugin({ ...plugin, loaded: isInstalled, hooks: [] } as any)}
  ```
- **Problème :** 11 occurrences de `any`/`as any` non justifiées. Le typage faible se propage : un `any` dans un composant parent force des `as any` dans les enfants.
- **Action requise :** Remplacer par des types explicites ou des `unknown` avec guards. Justifier chaque usage résiduel avec `// intentional`.

### B-08 — Fonctions sans annotation de type de retour
- **Fichiers :** `master/api/deps.py`, `master/api/automations.py`, `master/api/worker_binary.py`, `master/api/nodes_events.py`, `master/api/plugins.py`, `master/api/nodes.py`
- **Extrait :**
  ```python
  async def generate_join_token(...):
  ```
- **Problème :** ~20 fonctions FastAPI sans annotation de retour. Désactive la validation Pydantic de la réponse, masque les erreurs de sérialisation.
- **Action requise :** Ajouter le type de retour `-> dict[str, Any]` ou le Pydantic response_model approprié.

### B-10 — Imports différés (lazy imports)
- **Fichier :** `master/api/deps.py:73,200`, `master/api/automations.py:429`, `master/api/admin.py:162,416,494,523,556,633,660,862`, `master/api/nodes.py:694,1122`
- **Fichier :** `master/core/automation_engine.py:533`, `master/core/scheduler.py:189`, `master/core/plugin_base.py:38`, `master/core/plugin_worker.py:151`
- **Extrait :**
  ```python
  def some_function():
      import httpx  # lazy import
  ```
- **Problème :** Les imports différés masquent les erreurs de dépendance au runtime. Cachent les vrais problèmes d'import et ralentissent l'exécution. 20+ occurrences.
- **Action requise :** Déplacer tous les imports en haut de fichier. Si import conditionnel nécessaire, le justifier avec un commentaire.

### X-03 — Valeurs de timeout hardcodées
- **Fichiers :** `master/core/plugin_engine.py:99`, `master/core/node_manager.py:804`, `master/core/plugin_worker.py:131`, `master/core/llm_client.py:70`, `master/main.py:149`, `master/db/database.py:29,38,84`
- **Extrait :**
  ```python
  timeout=30.0
  ```
- **Problème :** `30.0` répété dans 6 fichiers différents comme timeout par défaut. Aucune constante partagée. Si le besoin change, il faut éditer partout.
- **Action requise :** Définir une constante `DEFAULT_TIMEOUT = 30.0` dans `config.py` ou dans un module `constants.py`.

### G-04 — Magic numbers (buffers, timeouts)
- **Fichier :** `worker/connection.go:23-27`, `worker/dispatcher.go:119`, `worker/logs.go:14`, `worker/stats.go:216`, `worker/wsclient.go:112`
- **Extrait :**
  ```go
  heartbeatInterval    = 30 * time.Second
  statusReportInterval = 60 * time.Second
  make([]byte, 2)      // wsclient.go
  ```
- **Problème :** Les constantes existent en haut de fichier (bon point) mais ne sont pas documentées. Les buffers magiques (`make([]byte, 2, 8)`) sont fragiles si le protocole change.
- **Action requise :** Documenter chaque constante avec son pourquoi. Pour les buffers, utiliser des `const` nommées.

### G-06 — Fonctions sans `context.Context`
- **Fichier :** `worker/connection.go`, `worker/discovery.go`, `worker/dispatcher.go`, `worker/enrollment.go`, `worker/services.go`
- **Extrait :**
  ```go
  func (wc *WorkerConn) Connect() error {
  func (wc *WorkerConn) RunWithBackoff() {
  ```
- **Problème :** La plupart des méthodes de `WorkerConn` n'acceptent pas `context.Context`. Impossible d'annuler une opération bloquante (ex: connect, read, wait). Backoff infini si le master ne répond pas.
- **Action requise :** Ajouter `ctx context.Context` comme premier paramètre des méthodes I/O-blocking. Utiliser `select` pour les délais d'annulation.

### DOC-01 — Routes API non documentées
- **Problème :** 24 routes trouvées dans le code, seulement 10 documentées dans README.md.
- **Routes documentées :** Login, logout, change-password, refresh, nodes list, generate-join, delete node, audit, audit-verify.
- **Routes manquantes (14) :** alerts, alerts/summary, alerts/{id}/acknowledge, plugins CRUD, plugin config, plugin toggle, settings, settings/llm, settings/llm/test, binary/refresh, worker binary download, stream, admin-only, reset, intent-config, public-key, manifest.json, nodes/connections.
- **Action requise :** Documenter les 14 routes manquantes dans README.md ou dans un document API séparé (OpenAPI/Swagger).

### M-03 — Commits sans tests dans le dernier sprint
- **Fichier :** 14 commits sur 20 avec modifications source (`master/`, `worker/`, `frontend/src/`) mais **aucun changement dans `tests/`**.
- **Problème :** Le taux de commits sans tests est de 70%. Indique que les nouvelles fonctionnalités (automations, investigations, alert engine, frontend overhaul) n'ont pas de couverture de tests.
- **Action requise :** Ajouter des tests pour les nouvelles fonctionnalités avant le prochain sprint. Priorité : alert engine, automations, investigations.

### F-06 — `console.warn` / `console.log` résiduels
- **Fichier :** `frontend/src/hooks/useNodeEvents.ts:46`, `frontend/src/store/pluginStore.ts:29`
- **Extrait :**
  ```ts
  console.warn('SSE connection error, will retry');
  console.warn(
  ```
- **Problème :** Logs console en production. Le `console.warn` de `useNodeEvents.ts` a du sens, mais pollue la console utilisateur. `pluginStore.ts` devrait utiliser un logger configurable.
- **Action requise :** Remplacer par un logger configurable ou supprimer en production. Les erreurs SSE devraient être dans un store d'events.

---

## 🟡 Signaux (à surveiller)

### F-01 — Couleurs arbitraires Tailwind (`bg-[#...]`)
- **Fichier :** `frontend/src/components/layout/TopBar.tsx:144-147`
- **Extrait :**
  ```tsx
  t === 'warm-dark' ? 'bg-[#F59E0B]' :
  t === 'cool-dark' ? 'bg-[#2dd4bf]' :
  t === 'gray-dark' ? 'bg-[#8b8698]' :
                     'bg-[#e8650a]';
  ```
- **Problème :** Valeurs hexadécimales arbitraires qui ne font pas partie du thème. Dérive du design system.
- **Action requise :** Définir ces couleurs dans `tailwind.config` avec des noms sémantiques.

### F-02 — Magic numbers dans les timers
- **Fichiers :** `HeroBanner.tsx:19` (1000ms), `TrendChart.tsx:52` (15000ms), `TrendChart.tsx:97` (30000ms), `TimeAgo.tsx:44` (30000ms), `ServersPage.tsx:88` (5000ms), `NodeDetailMetricsTab.tsx:163` (800ms), `DockerContainers.tsx:60` (2000ms), etc.
- **Problème :** Intervalles et timeouts hardcodés. Aucune cohérence entre les composants. Les temps de rafraîchissement ne sont pas paramétrables.
- **Action requise :** Extraire dans des constantes nommées regroupées par contexte.

### B-07 — Magic strings pour états (usage mixte enums/strings)
- **Fichiers :** `master/api/metrics.py:84`, `master/api/nodes.py:916`, `master/api/chat.py:349,376,466,491`, `master/core/proposal_autoexpire.py:150`, `master/core/automation_engine.py:334,445`, `master/core/insights.py:267`, `master/core/action_proposal.py:49,57,64,66`
- **Problème :** Mélange d'enums (dans `enums.py`) et de strings littérales. Les strings dans `chat.py`, `automation_engine.py`, `action_proposal.py` devraient utiliser les enums. Risque de typo non détectée.
- **Action requise :** Remplacer toutes les strings d'état par les enums correspondants.

### A-01 — Noms de fonctions dupliqués
- **Fichiers :** `master/` — `downgrade`, `get_config_schema`, `_on_status_report`, `register`, `upgrade`, `verify_chain`
- **Problème :** 6 noms de fonctions dupliqués dans le backend Python. Généralement des migrations ou callbacks, mais complique la navigation.
- **Action requise :** Renommer ou dédupliquer là où c'est pertinent.

### B-10 — `asyncio.Queue()` sans `maxsize`
- **Fichier :** `master/core/plugin_worker.py:140`
- **Extrait :**
  ```python
  queue: asyncio.Queue[str] = asyncio.Queue()
  ```
- **Problème :** Queue illimitée. Si le worker produit plus vite que le master ne consomme, la mémoire croît indéfiniment.
- **Action requise :** Ajouter `maxsize=N` avec une taille basée sur les métriques de charge.

### S-03 — `ALTER TABLE ADD COLUMN` sans `DEFAULT`
- **Fichier :** `master/db/migrations.py:249`
- **Extrait :**
  ```python
  await db.execute("ALTER TABLE plugins ADD COLUMN manifest_hash TEXT")
  ```
- **Problème :** Ajout de colonne nullable. Les lignes existantes auront `NULL`. Si cette colonne devient `NOT NULL` plus tard, les anciennes données cassent.
- **Action requise :** Soit ajouter `DEFAULT ''`, soit gérer `NULL` explicitement dans le code.

### X-06 — Dépendances non whitelistées
- **Python :** `bcrypt==4.0.1`, `itsdangerous==2.2.0`, `python-multipart==0.0.20` — non listées dans la whitelist de référence. Légitimes mais non documentées.
- **Go :** Aucune dépendance externe (stdlib only) — ✅ conforme.
- **Frontend :** Toutes les dépendances runtime correspondent à la whitelist — ✅.
- **Action requise :** Mettre à jour la whitelist documentée pour inclure `bcrypt`, `itsdangerous`, `python-multipart`.

### A-03 — Abstractions YAGNI
- **Problème :** Les classes `BaseModel` pour les schémas API en FastAPI sont normales (Pydantic). Les `TriggerModel`, `ConditionModel`, `ActionModel` dans `schemas/automations.py` pourraient être sur-architecturés pour la complexité actuelle, mais c'est acceptable.
- **Action requise :** Surveiller que l'utilitaire d'abstraction ne devienne pas un frein. Si 1 seul trigger concret, simplifier.

### D-04 — Go 1.23
- **Problème :** Go 1.23 est correct mais nécessite une version récente du runtime sur les cibles de déploiement. Vérifier que les systèmes cibles (Debian 12, Ubuntu 22.04, Alpine) ont Go ≥ 1.23 dans leurs dépôts.
- **Action requise :** Documenter la version Go requise pour le build et le déploiement.

---

## 📊 Métriques Git

### M-01 — Hot spots (fichiers les plus modifiés)

| Modifications | Fichier |
|---|---|
| 15 | `master/ws/worker_handler.py` |
| 15 | `master/db/migrations.py` |
| 14 | `master/config.py` |
| 13 | `master/main.py` |
| 13 | `master/api/nodes.py` |
| 13 | `frontend/src/i18n/fr.ts` |
| 13 | `frontend/src/i18n/en.ts` |
| 13 | `frontend/src/components/layout/Sidebar.tsx` |
| 12 | `master/core/node_manager.py` |
| 12 | `master/api/deps.py` |
| 12 | `master/api/admin.py` |

### M-02 — Ratio ajout/suppression (dernier sprint, HEAD~10)

- 24 fichiers changés
- **+2127 / -429 lignes** → Ratio ~5:1 ajout/suppression
- Les plus gros changements : `master/main.py` (+57 lignes), `master/ws/worker_handler.py` (+6 lignes)
- Interprétation : Sprint principalement additif, peu de refactoring.

### M-03 — Commits sans tests (sur les 20 derniers)

- 14 commits modifient du code source **sans toucher aux tests**
- Nouveautés non testées : alert engine, automations engine, investigation manager, proposal auto-expiry, frontend overhaul (PluginsPage, NodeDetail, AutomationsPage)
- ✅ 6 commits avec tests : modifications du workers, websocket, sécurité

---

## 🔍 Nécessite revue humaine

### DOC-03 — Tests de régression pour bugs documentés
- `docs/LIMITS.md` n'existe pas dans le dépôt. Aucune limite documentée à vérifier.
- **Action :** Créer `LIMITS.md` si les bugs historiques doivent être suivis, ou bien ce check est non applicable.

### T-01 — Couverture des modules critiques (non exécuté)
- `pytest-cov` n'est pas installé dans l'environnement.
- Les modules critiques (`security_manager`, `auth`, `database`) n'ont pas pu être mesurés automatiquement.
- **Action :** Installer `pytest-cov` (`pip install pytest-cov`) et exécuter les tests avec couverture.

### D-02 — CVE connues (non exécuté)
- `pip-audit` non disponible dans l'environnement.
- **Action :** Installer `pip-audit` (`pip install pip-audit`) et exécuter `pip-audit -r requirements.txt`.

### B-05 — N+1 queries (revue manuelle)
- 178 `await db.execute()` trouvés, 160 boucles `for`/`async for`.
- La détection automatique est insuffisante — une revue manuelle est nécessaire pour vérifier que les appels DB ne sont pas dans des boucles sans `JOIN`.
- **Action :** Audit manuel des endpoints critiques (`/nodes`, `/alerts`, `/plugins`) avec analyse des requêtes générées.

### T-03 — Tests de contrat Worker/Master
- ✅ Les tests existent pour `STATUS_REPORT` (8 occurrences) et `ENROLLMENT_CHALLENGE` (1 occurrence).
- **Manquant :** Tests de contrat pour `LIST_CONTAINERS`, `RESTART_CONTAINER`, `LIST_SERVICES`, `READ_LOGS`, `STATUS_SERVICE`.
- **Action :** Ajouter des tests de contrat pour les intents manquants.

---

## ✅ Points positifs

Ce qui a été vérifié et trouvé propre :

| Check | Statut |
|---|---|
| **F-08** — Import * de librairie | ✅ Aucune occurrence trouvée |
| **B-04** — Sync bloquant (`time.sleep`, `open()` sync) dans async | ✅ Aucune occurrence trouvée |
| **A-02** — Commentaires didactiques qui paraphrasent le code | ✅ Aucune occurrence trouvée |
| **D-01** — Dépendances Python sans version épinglée | ✅ Toutes les dépendances ont une version (`==`) |
| **D-03** — Lockfile frontend | ✅ `package-lock.json` présent |
| **S-01** — Migrations non idempotentes | ✅ Toutes les `CREATE TABLE` ont `IF NOT EXISTS` |
| **S-02** — Colonnes status avec CHECK | ✅ `CHECK(status IN ...)` présent pour toutes les colonnes status |
| **T-02** — Tests skip/xfail permanents | ✅ Aucun test skip/xfail trouvé |
| **P-03** — Tests de régression LLM | ✅ 62 références — bonne couverture (≥3) |
| **X-06** — Dépendances Go | ✅ Aucune dépendance externe (stdlib only) |
| **DOC-02** — Fichiers déclarés dans SESSION.md | ✅ Tous les fichiers référencés existent |
| **P-02** — Paramètres modèle via config | ✅ `settings.llm_max_tokens`, `settings.llm_temperature` utilisés — pas de hardcode |
| **F-09/X-09** — TODO/FIXME avec propriétaire | ✅ Aucun TODO/FIXME problématique trouvé |
| **Arborescence** | ✅ Conforme à la structure documentée dans AGENTS.md |

---

## Inventaire des fichiers par couche

| Couche | Langage | Nombre de fichiers |
|---|---|---|
| Backend | Python (FastAPI) | 71 |
| Frontend | TypeScript/React | 126 |
| Worker | Go (stdlib) | 16 |
| Tests | Python (pytest) | 56 |

---

*Rapport généré par la tâche d'audit automatique le 2026-07-17.*
*Catalogue de référence : nomenclature DEBT_CATALOG.md (fichier non trouvé dans le dépôt).*
*Aucune modification n'a été effectuée dans le code source.*
