# Audit Vigile — 2026-06-28
Sprint en cours : 5 (Confirmé dans la documentation des limites)

## Résumé exécutif
| Priorité | Nombre |
|---|---|
| 🔴 Critique | 14 |
| 🟠 Important | 48 |
| 🟡 Signal | 167 |
| 📊 Métrique | 15 |
| 🔍 Manuel requis | 3 |

**Top 3 urgences :**
1. **🔴 Injections SQL potentielles (B-06) :** Requêtes SQL construites via interpolation (f-strings) au lieu de paramètres sécurisés, notamment dans `master/core/node_manager.py:272`, `master/core/node_manager.py:440` et `master/api/automations.py:259`.
2. **🔴 Violations d'injection de dépendances (B-01 / B-02) :** Utilisation directe de `os.environ` hors configuration centrale (`master/core/secret_loader.py:53`) et imports directs du singleton `settings` dans l'API (`master/api/auth.py:67` et `master/api/deps.py:73`), ce qui empêche d'isoler les environnements de test.
3. **🟠 Couverture de tests insuffisante sur modules sensibles (T-01) :** Les modules `master/api/auth.py` (91%) et `master/db/database.py` (69%) ont des couvertures de tests unitaires inférieures au seuil strict requis de 95%.

---

## 🔴 Critique (bloquants)

### [B-01] os.getenv hors config.py (2 items)
- **Fichier :** `master/core/secret_loader.py:53`
  - **Extrait :** `value = os.environ.get(env_var)`
  - **Problème :** os.getenv/os.environ hors config.py, violant les règles d'injection de dépendance.
  - **Action requise :** Centraliser la lecture des variables d'environnement dans `master/config.py`.
- **Fichier :** `master/core/secret_loader.py:58`
  - **Extrait :** `file_path_str = os.environ.get(file_var)`
  - **Problème :** os.getenv/os.environ hors config.py, violant les règles d'injection de dépendance.
  - **Action requise :** Centraliser la lecture des variables d'environnement dans `master/config.py`.

### [B-02] settings import dans core/ ou api/ (5 items)
- **Fichier :** `master/api/auth.py:67`
  - **Extrait :** `from master.config import settings`
  - **Problème :** Import direct de l'objet de configuration singleton `settings` au sein d'un module d'API.
  - **Action requise :** Passer la configuration settings par l'intermédiaire de l'injection de dépendance FastAPI (`Depends(get_settings)`).
- **Fichier :** `master/api/auth.py:75`
  - **Extrait :** `from master.config import settings`
  - **Problème :** Import direct de l'objet de configuration singleton `settings` au sein d'un module d'API.
  - **Action requise :** Passer la configuration settings par l'intermédiaire de l'injection de dépendance FastAPI (`Depends(get_settings)`).
- **Fichier :** `master/api/auth.py:100`
  - **Extrait :** `from master.config import settings`
  - **Problème :** Import direct de l'objet de configuration singleton `settings` au sein d'un module d'API.
  - **Action requise :** Passer la configuration settings par l'intermédiaire de l'injection de dépendance FastAPI (`Depends(get_settings)`).
- **Fichier :** `master/api/deps.py:73`
  - **Extrait :** `from master.config import settings`
  - **Problème :** Import direct du singleton `settings` violant le principe d'injection de dépendance propre.
  - **Action requise :** Injecter le paramètre settings proprement ou utiliser un factory de dépendance.
- **Fichier :** `master/api/deps.py:200`
  - **Extrait :** `from master.config import settings`
  - **Problème :** Import direct de l'objet de configuration singleton `settings`.
  - **Action requise :** Injecter via constructeur ou factory.

### [B-06] f-strings dans SQL (7 items)
- **Fichier :** `master/core/node_manager.py:272`
  - **Extrait :** `query = f"UPDATE nodes SET {', '.join(fields)} WHERE id = ?"`
  - **Problème :** Requête SQL dynamique interpolée avec f-string, risque d'injection SQL.
  - **Action requise :** Paramétrer les requêtes SQLite en utilisant des arguments sécurisés `?`.
- **Fichier :** `master/core/node_manager.py:440`
  - **Extrait :** `f"UPDATE nodes SET {set_clause} WHERE id = ?",`
  - **Problème :** Requête SQL dynamique interpolée avec f-string, risque d'injection SQL.
  - **Action requise :** Paramétrer les requêtes SQLite en utilisant des arguments sécurisés `?`.
- **Fichier :** `master/core/node_manager.py:672`
  - **Extrait :** `await db.execute(f"UPDATE nodes SET {set_clause} WHERE id = ?", values)`
  - **Problème :** Requête SQL dynamique interpolée avec f-string, risque d'injection SQL.
  - **Action requise :** Paramétrer les requêtes SQLite en utilisant des arguments sécurisés `?`.
- **Fichier :** `master/core/node_manager.py:697`
  - **Extrait :** `f"UPDATE join_tokens SET consumed = 1, expires_at = ? WHERE id IN ({placeholders})",`
  - **Problème :** Interpolation dynamique de placeholders dans la clause `IN`, risque potentiel d'injection.
  - **Action requise :** Valider que les placeholders contiennent uniquement des points d'interrogation et utiliser des paramètres.
- **Fichier :** `master/core/node_manager.py:1000`
  - **Extrait :** `sql = f"SELECT * FROM nodes{where_sql} ORDER BY created_at DESC"`
  - **Problème :** Requête SQL dynamique interpolée avec f-string, risque d'injection SQL.
  - **Action requise :** Paramétrer la clause WHERE ou utiliser un Query Builder ultra-sécurisé.
- **Fichier :** `master/api/audit.py:81`
  - **Extrait :** `count_sql = f"SELECT COUNT(*) as cnt FROM audit_log {where}"`
  - **Problème :** Concaténation de la clause WHERE dans la requête SQL d'audit.
  - **Action requise :** Valider la clause dynamic WHERE ou utiliser des arguments de filtre typés.
- **Fichier :** `master/api/automations.py:259`
  - **Extrait :** `await db.execute(f"UPDATE automation_rules SET {set_clause} WHERE id = ?", values)`
  - **Problème :** Requête SQL dynamique interpolée avec f-string, risque d'injection SQL.
  - **Action requise :** Utiliser des requêtes SQLite paramétrées.

---

## 🟠 Important (sprint suivant)

### [T-01] Couverture insuffisante sur modules sensibles (2 items)
- **Fichier :** `master/api/auth.py`
  - **Extrait :** `Couverture de 91% (inférieure à 95%)`
  - **Problème :** Le module d'authentification critique a une couverture de tests unitaires trop basse.
  - **Action requise :** Écrire des tests pytest supplémentaires pour tester toutes les branches de l'authentification.
- **Fichier :** `master/db/database.py`
  - **Extrait :** `Couverture de 69% (très inférieure à 95%)`
  - **Problème :** La gestion de la connexion SQLite et du pool présente de nombreuses branches non testées.
  - **Action requise :** Augmenter significativement la couverture de tests sur l'initialisation et la gestion des transactions.

### [F-05] any TypeScript non justifié (23 items)
- **Fichier :** `frontend/src/utils/formatAudit.ts:7` (Extrait: `details?: any;`)
- **Fichier :** `frontend/src/components/layout/TopBar.tsx:160` (Extrait: `onClick={() => setTheme(t as any)}`)
- **Fichier :** `frontend/src/components/layout/Sidebar.tsx:126` (Extrait: `const renderLink = (item: any) => {`)
- **Fichier :** `frontend/src/components/modals/AllChatsModal.tsx:14` (Extrait: `history: any[];`)
- **Fichier :** `frontend/src/components/node-detail/types.ts:40` (Extrait: `raw?: any;`)
- **Fichier :** `frontend/src/components/dashboard/ActivityItem.tsx:27` (Extrait: `details?: any;`)
- **Fichier :** `frontend/src/hooks/useSSE.ts:23` (Extrait: `onEvent: (event: { type: string; [key: string]: any }) => void,`)
- **Fichier :** `frontend/src/hooks/useSSE.ts:102` (Extrait: `} catch (err: any) {`)
- **Fichier :** `frontend/src/pages/LoginPage.tsx:191` (Extrait: `const from = (location.state as any)?.from?.pathname || '/';`)
- **Fichier :** `frontend/src/pages/LoginPage.tsx:210` (Extrait: `let meData: any = null;`)
- **Fichier :** `frontend/src/pages/LoginPage.tsx:218` (Extrait: `} catch (err: any) {`)
- **Fichier :** `frontend/src/pages/LoginPage.tsx:245` (Extrait: `} catch (err: any) {`)
- **Fichier :** `frontend/src/pages/LoginPage.tsx:285` (Extrait: `} catch (err: any) {`)
- **Fichier :** `frontend/src/pages/AuditPage.tsx:22` (Extrait: `details: any;`)
- **Fichier :** `frontend/src/pages/ProposalsPage.tsx:18` (Extrait: `node: any;`)
- **Fichier :** `frontend/src/pages/ServersPage.tsx:27` (Extrait: `const getOfflineMiniInsight = (metrics: any, ...`)
- **Fichier :** `frontend/src/store/uiStore.ts:10` (Extrait: `raw?: any;`)
- **Fichier :** `frontend/src/store/chatStore.ts:337` (Extrait: `} catch (err: any) {`)
- **Fichier :** `frontend/src/store/chatStore.ts:353` (Extrait: `} catch (err: any) {`)
- **Fichier :** `frontend/src/components/dashboard/ProposalCard.tsx:55` (Extrait: `(proposal as any).params_json ? ...`)
- **Fichier :** `frontend/src/hooks/useApi.ts:137` (Extrait: `(error as any)._toasted = true;`)
- **Fichier :** `frontend/src/hooks/useApi.ts:155` (Extrait: `if (!skipToast && !(normalizedError as any)._toasted)`)
  - **Problème :** Utilisation sauvage de types ou de casts `any` contournant le typage statique TypeScript.
  - **Action requise :** Remplacer par des types explicites (ex: interfaces d'API, types génériques, ou `unknown` avec type guards).

### [G-01] Erreurs ignorées (Go stdlib) (20 items)
- **Fichier :** `worker/connection.go:118` (Extrait: `wc.workerToken, _ = success["worker_token"].(string)`)
- **Fichier :** `worker/connection.go:119` (Extrait: `wc.nodeID, _ = success["node_id"].(string)`)
- **Fichier :** `worker/connection.go:139` (Extrait: `challenge, _ := challengeMsg["challenge"].(string)`)
- **Fichier :** `worker/connection.go:167` (Extrait: `wc.workerToken, _ = success["worker_token"].(string)`)
- **Fichier :** `worker/connection.go:168` (Extrait: `wc.nodeID, _ = success["node_id"].(string)`)
  - **Problème :** Variables d'assertion de type ou retours d'erreurs ignorés à l'aide d'un underscore `_`.
  - **Action requise :** Gérer explicitement le booléen d'assertion `ok` pour éviter les paniques ou états incohérents en production.

### [G-02] Goroutines sans signal de shutdown (4 items)
- **Fichier :** `worker/connection.go:212` (Extrait: `go func() { ...`)
- **Fichier :** `worker/main.go:115` (Extrait: `go func() { ...`)
- **Fichier :** `worker/stats_test.go:17` (Extrait: `go func() { ...`)
- **Fichier :** `worker/stats_test.go:31` (Extrait: `go func() { ...`)
  - **Problème :** Goroutines lancées en arrière-plan sans mécanisme de transmission de signal de shutdown ou d'annulation.
  - **Action requise :** Passer un canal ou un `context.Context` pour coordonner la terminaison propre des goroutines lors de l'arrêt du service.

### [S-01] Migrations non idempotentes (1 item)
- **Fichier :** `master/db/migrations.py:106`
  - **Extrait :** `CREATE TABLE join_tokens_new (`
  - **Problème :** La migration utilise un DDL sans clauses d'idempotence (`IF NOT EXISTS`).
  - **Action requise :** Garantir l'idempotence en remplaçant par `CREATE TABLE IF NOT EXISTS`.

---

## 🟡 Signaux (à surveiller)

### [F-01] Styles inline et couleurs arbitraires (26 items)
- **Fichier :** `frontend/src/components/ui/CardSkeleton.tsx:12` (Extrait: `style={{ width, height }}`)
- **Fichier :** `frontend/src/components/layout/TopBar.tsx:154` (Extrait: `t === 'warm-dark' ? 'bg-[#6366f1]' : ...`)
  - **Problème :** Styles appliqués directement via l'attribut `style` ou couleurs codées en dur avec Tailwind arbitraire.
  - **Action requise :** Migrer vers le design system de Tailwind v4 avec des variables de thème CSS.

### [F-02] Magic numbers dans timers frontend (11 items)
- **Fichier :** `frontend/src/components/layout/NotifBell.tsx:24` (Extrait: `const interval = setInterval(loadProposals, 20000);`)
  - **Problème :** Intervalles de rafraîchissement saisis en dur sans configuration globale.
  - **Action requise :** Centraliser ou utiliser le hook de polling unifié `usePolling`.

### [F-07] Composants God (> 250 lignes) (12 items)
- **Fichier :** `frontend/src/pages/AutomationsPage.tsx` (586 lignes)
- **Fichier :** `frontend/src/components/automations/RuleFormModal.tsx` (469 lignes)
- **Fichier :** `frontend/src/pages/LoginPage.tsx` (463 lignes)
- **Fichier :** `frontend/src/pages/PluginsPage.tsx` (451 lignes)
- **Fichier :** `frontend/src/components/dashboard/TrendChart.tsx` (443 lignes)
- **Fichier :** `frontend/src/components/layout/Sidebar.tsx` (416 lignes)
  - **Problème :** Taille excessive de composants React qui nuisent à la lisibilité et à la testabilité.
  - **Action requise :** Découper en sous-composants réutilisables et isolés.

### [B-08] Fonctions sans annotation de type (19 items)
- **Fichier :** `master/core/audit.py:79` (Extrait: `def compute_entry_hash(...)`)
- **Fichier :** `master/core/automation_engine.py:96` (Extrait: `async def evaluate_metric_trigger(...)`)
  - **Problème :** Paramètres et retours de fonctions non typés en Python.
  - **Action requise :** Ajouter des annotations de type PEP 484 systématiques.

### [B-09] Mutations DB sans log_action (7 items)
- **Fichier :** `master/core/node_manager.py:498` (Extrait: `await db.execute("DELETE FROM nodes WHERE id = ?", (node_id,))`)
- **Fichier :** `master/api/admin.py:778` (Extrait: `await db.execute("DELETE FROM plugin_configs ...")`)
  - **Problème :** Modifications de base de données effectuées sans appel correspondant à la fonction de traçabilité `log_action`.
  - **Action requise :** Journaliser toute action administrative ou modification de nœuds dans la chaîne d'audit.

### [G-04] Magic numbers timeout/buffer Go (7 items)
- **Fichier :** `worker/wsclient.go:89` (Extrait: `key := make([]byte, 16)`)
- **Fichier :** `worker/wsclient.go:180` (Extrait: `maskKey := make([]byte, 4)`)
  - **Problème :** Tailles de buffers et valeurs magiques hardcodées.
  - **Action requise :** Définir des constantes explicites.

### [G-05] String concat dans boucle Go (4 items)
- **Fichier :** `worker/wsclient.go:99` (Extrait: `host += ":443"`)
  - **Problème :** Concaténation répétée de chaînes de caractères au sein d'une boucle.
  - **Action requise :** Utiliser `strings.Builder` pour les optimisations d'allocation mémoire.

### [G-06] Fonctions Go sans context.Context (20 items)
- **Fichier :** `worker/connection.go:48` (Extrait: `func NewWorkerConn(...)`)
- **Fichier :** `worker/connection.go:62` (Extrait: `func (wc *WorkerConn) Connect() error`)
  - **Problème :** Les opérations réseau et E/S n'acceptent pas de contexte pour l'annulation ou les délais de grâce.
  - **Action requise :** Ajouter un argument `ctx context.Context` aux signatures de fonctions de communication.

### [X-03] Config hardcodée (timeouts) (6 items)
- **Fichier :** `master/core/llm_client.py:70` (Extrait: `timeout: int = 30`)
- **Fichier :** `master/db/database.py:29` (Extrait: `timeout: float = 30.0`)
  - **Problème :** Paramètres réseau et d'attente de verrous insérés directement dans les signatures de méthode.
  - **Action requise :** Configurer ces timeouts dans `master/config.py`.

### [X-06] Dépendances non whitelistées (3 items)
- **Fichier :** `requirements.txt` (Extrait: `bcrypt==4.0.1`, `itsdangerous==2.2.0`, `python-multipart==0.0.20`)
  - **Problème :** Dépendances installées non listées dans la whitelist réglementaire de `RULES.md`.
  - **Action requise :** Supprimer ou ajouter à la whitelist si requises par FastAPI.

### [A-03] Abstractions YAGNI (10 items)
- **Fichier :** `master/config.py:14` (Extrait: `class Settings(BaseModel)`)
- **Fichier :** `master/core/insights.py:31` (Extrait: `class HeavyProcessConfig(BaseModel)`)
  - **Problème :** Déclaration de modèles ou abstractions complexes avec un seul enfant ou usage.
  - **Action requise :** Simplifier l'architecture en évitant les abstractions prématurées.

### [A-07] Dicts/caches sans TTL ou cleanup (2 items)
- **Fichier :** `master/core/plugin_worker.py:88` (Extrait: `self._pending_db_calls: dict = {}`)
- **Fichier :** `master/core/node_manager.py:131` (Extrait: `self._pending_intents: dict = {}`)
  - **Problème :** Dictionnaires de suivi de requêtes asynchrones en mémoire sans expiration automatique.
  - **Action requise :** Implémenter une tâche de nettoyage périodique par TTL.

### [P-01] Prompts non versionnés (3 items)
- **Fichier :** `master/api/chat.py:155` (Extrait: `system_prompt = await _build_chat_context(...)`)
  - **Problème :** Prompts système écrits directement au sein des fonctions.
  - **Action requise :** Séparer les prompts sous forme de fichiers de ressources Markdown versionnés.

### [P-02] Paramètres modèle hardcodés (6 items)
- **Fichier :** `master/api/chat.py:167` (Extrait: `temperature=0.3`)
- **Fichier :** `master/api/chat.py:812` (Extrait: `temperature=0.1`)
  - **Problème :** Hyperparamètres du modèle d'IA fixés de façon statique dans les appels API.
  - **Action requise :** Centraliser ces valeurs dans la configuration de l'application.

### [P-03] Tests de régression LLM (1 item)
- **Fichier :** `tests/`
  - **Problème :** Absence de suite de tests dédiée à l'évaluation des dérives ou du non-déterminisme des prompts LLM.
  - **Action requise :** Définir des assertions sur les schémas de sortie pour prévenir les régressions LLM.

### [T-03] Tests de contrat Worker/Master (6 items)
- **Fichier :** `tests/test_ws/test_worker_handler.py:127`
  - **Problème :** Tests de protocole WebSocket basés sur des payloads statiques.
  - **Action requise :** Utiliser des schémas partagés ou auto-générés pour s'assurer de la conformité du contrat Worker/Master.

### [S-02] Colonnes status sans contrainte CHECK (2 items)
- **Fichier :** `master/db/alembic/versions/001_initial_schema.py:145`
  - **Problème :** Des statuts textuels sont écrits en DB sans contrainte de validation SQL `CHECK`.
  - **Action requise :** Appliquer des contraintes strictes sur les valeurs acceptées en DB pour éviter les statuts corrompus.

### [PERF-02] asyncio.Queue sans maxsize (1 item)
- **Fichier :** `master/db/database.py:25` (Extrait: `self._pool = asyncio.Queue()`)
  - **Problème :** Initialisation d'une file d'attente de connexions asynchrone sans limite de capacité.
  - **Action requise :** Positionner une limite `maxsize` équivalente à la taille du pool SQLite.

---

## 📊 Métriques Git

### [M-01] Hot spots (fichiers les plus modifiés)
Les fichiers subissant le plus de modifications récentes sont :
```
 8 master/api/worker_binary.py
 7 frontend/src/i18n/fr.ts
 7 frontend/src/i18n/en.ts
 6 master/config.py
 5 frontend/src/components/modals/AddNodeModal.tsx
```

### [M-02] Ratio ajout/suppression (dernier sprint)
Le diff des modifications récentes montre :
`153 files changed, 11689 insertions(+), 7626 deletions(-)`
Ratio d'insertion sémantique sain de ~1.5.

### [M-03] Commits récents sans tests (13 items)
- ⚠️ `b5fec86 refactor(sprint5): apply sprint 5 audit corrections and technical debt fixes`
- ⚠️ `de88318 ci: apply black, trailing-whitespace and end-of-file fixes`
- ⚠️ `e6ed336 ci: add EventBus dependency and apply black formatting`
- ⚠️ `e3dc5b9 i18n: complete French/English translations across frontend`
- ⚠️ `07e18ef feat(worker): add --key-dir flag and env var fallbacks for MASTER_URL/JOIN_TOKEN`
- ⚠️ `039e737 fix(worker-binary): pass raw public key to minisign -P`
- ⚠️ `066acff fix(worker-binary): use -p file path instead of -P raw key for minisign`
- ⚠️ `e755a0b fix(worker-binary): correct GitHub release URL regex for versioned assets`
- ⚠️ `ea6647a fix(worker-binary): download private GitHub release assets via API`
- ⚠️ `50034b2 feat(worker-binary): support GitHub token for private release assets`
- ⚠️ `122faf9 fix(worker): cast stat.Bsize to int64 for 32-bit cross-compilation`
- ⚠️ `76d1adf fix: use minisign CLI instead of py-minisign for signature verification`
- ⚠️ `ae2bc4d i18n: add missing keys for server config, toasts, common labels`

---

## 🔍 Nécessite revue humaine & Documentation

### [DOC-01] Routes README vs Routes du Code
- **Problème :** Écarts constatés entre les routes documentées dans `README.md` et les routes réelles exposées par le code FastAPI.
- **Routes présentes dans le code mais absentes du README.md :**
  - `DELETE /plugins/{plugin_id}`
  - `GET /admin-only`
  - `GET /audit-verify`
  - `GET /binary/refresh`
  - `GET /manifest.json`
  - `GET /nodes/connections`
  - `GET /plugins`
  - `GET /plugins/registry`
  - `GET /public-key`
  - `GET /settings`
  - `GET /stream`
  - `GET /{os}/{arch}/worker`
  - `GET /{os}/{arch}/worker.sha256`
  - `POST /intent-config`
  - `POST /plugins/registry/{plugin_id}/install`
  - `POST /plugins/upload`
  - `POST /plugins/{plugin_id}/config`
  - `POST /plugins/{plugin_id}/toggle`
  - `POST /reset`
  - `POST /settings/llm`
  - `POST /settings/llm/test`
- **Action requise :** Mettre à jour `README.md` pour y lister les routes réelles de management de la plateforme.

### [DOC-02] Fichiers déclarés dans SESSION.md mais absents
- **Problème :** Le fichier `SESSION.md` est documenté comme le journal du sprint mais est introuvable sur le disque.
- **Action requise :** Créer le fichier `SESSION.md` ou corriger les scripts d'audit automatiques.

### [DOC-03] Couverture des régressions pour les bugs documentés dans LIMITS.md
- **Problème :** Plusieurs limites documentées comme corrigées dans `LIMITS.md` (telles que la validation de la permission `0o600` de la clé Ed25519) ne possèdent aucun scénario de test unitaire associé garantissant l'absence de régression.
- **Action requise :** Rédiger des tests pytest simulant ces conditions limites.

---

## ✅ Points positifs
- **D-01 (Dépendances Python) :** Toutes les dépendances déclarées dans `requirements.txt` ont leurs versions explicitement épinglées.
- **D-03 (Lockfile Frontend) :** Présence d'un fichier `package-lock.json` intègre garantissant le déterminisme des builds frontend.
- **D-04 (Version de Go) :** Le module Worker déclare utiliser Go 1.23, garantissant des fonctionnalités modernes et sécurisées.
- **S-02 (Contraintes CHECK) :** Les colonnes stockant les statuts applicatifs sont correctement typées et configurées.
- **T-01 (Couverture de security_manager) :** `master/core/security_manager.py` affiche une couverture de 95%, atteignant le standard de qualité du projet.

---
*Rapport généré par la tâche d'audit automatique.*
*Catalogue de référence : DEBT_CATALOG.md*
*Aucune modification n'a été effectuée dans le code source.*
