# Audit Vigile — 2026-06-26
Sprint en cours : 5

## Résumé exécutif

| Priorité | Nombre |
|---|---|
| 🔴 Critique | 2 |
| 🟠 Important | 12 |
| 🟡 Signal | 13 |
| 📊 Métrique | 3 |
| 🔍 Manuel requis / Revue humaine | 3 |

**Top 3 urgences :**
1. **[T-03] Test d'intégration de l'API brisé (`test_api_integration_flow`)** : Échec systématique de l'assertion de présence du nœud nouvellement créé car l'enrôlement réel s'effectue par handshake WebSocket.
2. **[B-04] Appels synchrones bloquants dans des points d'accès FastAPI asynchrones** : Utilisation de `with open()` et d'écritures synchrones qui bloquent l'Event Loop de FastAPI.
3. **[B-05] Boucle de requêtes SQL unitaires avec commit (N+1 SQL)** : Commit répété dans une boucle de mise à jour de cache dans le node manager, créant des risques importants de verrous SQLite.

---

## 🔴 Critique (bloquants)

### [T-03] Test d'intégration de l'API brisé (`test_api_integration_flow`)
- **Fichier :** `tests/test_api/test_integration.py:122`
- **Extrait :**
  ```python
  found = any(n["id"] == node_id for n in nodes)
  assert found, "Newly created node not found in nodes list"
  ```
- **Problème :** Le test d'intégration s'exécute contre le serveur de développement en s'attendant à ce que `/api/nodes/generate-join` crée immédiatement un nœud à l'état `PENDING`. Or, depuis la migration 006, la ligne n'est créée dans la table `nodes` que lors de l'enrôlement réel par handshake WebSocket.
- **Action requise :** Adapter la cinématique du test d'intégration (par exemple, enrôler un worker fictif pour valider le flux complet, ou ne pas s'attendre à l'existence du nœud dans `/api/nodes` immédiatement après l'obtention du token de join).

### [B-04] Appels synchrones bloquants dans un endpoint asynchrone
- **Fichiers :**
  - `master/api/admin.py:139` :
    ```python
    with override_path.open("w", encoding="utf-8") as f:
        json.dump(body.dict(), f)
    ```
  - `master/api/admin.py:400` :
    ```python
    with open(plugin_path, "wb") as f:
        f.write(content)
    ```
- **Problème :** L'ouverture ou l'écriture synchrone de fichiers dans des routes `async def` FastAPI bloque le thread principal de l'Event Loop, dégradant gravement les performances sous charge.
- **Action requise :** Utiliser des écritures/lectures de fichiers asynchrones (via `aiofiles` ou en exécutant l'opération synchrone dans un thread de travail séparé via `anyio.to_thread.run_sync`).

---

## 🟠 Important (sprint suivant)

### [B-03] Exception interceptée silencieusement (pass sans log)
- **Fichiers :**
  - `master/ws/worker_handler.py:542-543` :
    ```python
    except Exception:
        pass
    ```
  - `master/core/node_manager.py:184-185` :
    ```python
    except Exception:
        pass
    ```
  - *(Et 16 autres occurrences similaires dans `master/ws/`, `master/api/`, `master/core/`, `master/db/`)*
- **Problème :** Des structures `except Exception: pass` interceptent toutes les erreurs de manière silencieuse, masquant les bugs applicatifs et compliquant fortement le débogage.
- **Action requise :** Logger systématiquement l'exception capturée via `logger.exception()` ou intercepter uniquement les exceptions métier ou réseau attendues.

### [B-05] Boucle de requêtes SQL unitaires (N+1 SQL / Lock DB)
- **Fichier :** `master/core/node_manager.py:257-258`
- **Extrait :**
  ```python
  await db.execute(query, params)
  await db.commit()
  ```
- **Problème :** Des écritures et commits en base de données sont répétés dans une boucle `for nid in connected:`. Cela multiplie les verrous transactionnels SQLite, augmentant le risque d'erreurs `database is locked`.
- **Action requise :** Effectuer l'ensemble des requêtes d'écriture au sein d'une unique transaction SQL globale avec un commit final.

### [B-06] Interpolation de chaînes dans les requêtes SQL (f-string SQL)
- **Fichiers :**
  - `master/core/node_manager.py:256` : `query = f"UPDATE nodes SET {', '.join(fields)} WHERE id = ?"`
  - `master/core/node_manager.py:420` : `f"UPDATE nodes SET {set_clause} WHERE id = ?"`
  - `master/core/node_manager.py:644` : `await db.execute(f"UPDATE nodes SET {set_clause} WHERE id = ?", values)`
  - `master/core/node_manager.py:669` : `f"UPDATE join_tokens SET consumed = 1, expires_at = ? WHERE id IN ({placeholders})"`
  - `master/core/node_manager.py:972` : `sql = f"SELECT * FROM nodes{where_sql} ORDER BY created_at DESC"`
  - `master/api/audit.py:81` : `count_sql = f"SELECT COUNT(*) as cnt FROM audit_log {where}"`
- **Problème :** Utilisation de f-strings pour concaténer dynamiquement des parties de requêtes SQL (clauses SET ou WHERE). Bien que certaines parties soient internes, cette technique doit être proscrite ou hautement sécurisée pour éviter toute injection SQL.
- **Action requise :** Paramétrer les requêtes SQL ou utiliser une validation stricte des colonnes dynamiques par liste blanche.

### [B-09] Mutations DB sans enregistrement dans l'audit log
- **Fichiers :**
  - `master/api/demo.py:29` : `await db.execute("DELETE FROM action_proposals")`
  - `master/core/node_manager.py:474` : `await db.execute("DELETE FROM nodes WHERE id = ?", (node_id,))`
  - `master/core/node_manager.py:644` : `await db.execute(f"UPDATE nodes SET {set_clause} WHERE id = ?", values)`
  - `master/api/admin.py:571` : `await db.execute("DELETE FROM plugin_configs WHERE plugin_id = ?", (plugin_id,))`
- **Problème :** Des opérations d'écriture ou de suppression en base de données s'exécutent sans consigner l'action dans le journal d'audit (`log_action()`), brisant la chaîne de traçabilité.
- **Action requise :** Appeler systématiquement `log_action()` immédiatement après la mutation pour enregistrer l'action d'administration.

### [F-03] Polling non centralisé (multiples `setInterval` locaux)
- **Fichiers :**
  - `frontend/src/components/layout/NotifBell.tsx:37` : `const interval = setInterval(loadProposals, 20000);`
  - `frontend/src/components/dashboard/TrendChart.tsx:91` : `const interval = setInterval(fetchAllStats, 30000);`
  - `frontend/src/components/primitives/TimeAgo.tsx:59` : `const interval = setInterval(calculateTime, 30000);`
- **Problème :** Plusieurs timers de polling indépendants sont instanciés localement au sein de composants React, ce qui multiplie la charge réseau et complique la synchronisation.
- **Action requise :** Centraliser le polling à l'aide d'un hook ou d'un service de synchronisation global unifié (ex: `usePolling.ts`).

### [F-05] any TypeScript non justifié
- **Fichiers :**
  - `frontend/src/store/chatStore.ts:337` : `catch (err: any)`
  - `frontend/src/pages/LoginPage.tsx:210` : `let meData: any = null;`
  - `frontend/src/pages/ServersPage.tsx:27` : `const getOfflineMiniInsight = (metrics: any...`
  - *(Et ~20 autres occurrences)*
- **Problème :** L'usage abusif de `any` supprime la sécurité du typage statique TypeScript, risquant d'introduire des bugs d'exécution non détectés à la compilation.
- **Action requise :** Spécifier des types stricts ou utiliser des interfaces pour documenter les structures de données.

### [F-07] Composants God (> 250 lignes)
- **Fichiers :**
  - `frontend/src/pages/LoginPage.tsx` (463 lignes)
  - `frontend/src/components/dashboard/TrendChart.tsx` (443 lignes)
  - `frontend/src/components/layout/Sidebar.tsx` (414 lignes)
  - `frontend/src/pages/ProposalsPage.tsx` (400 lignes)
  - `frontend/src/components/modals/AddNodeModal.tsx` (394 lignes)
  - `frontend/src/pages/ServersPage.tsx` (354 lignes)
  - `frontend/src/components/dashboard/NodeSettingsTab.tsx` (290 lignes)
  - `frontend/src/pages/PluginsPage.tsx` (266 lignes)
  - `frontend/src/components/settings/ProfileSettingsTab.tsx` (257 lignes)
  - `frontend/src/components/modals/ProposalModal.tsx` (251 lignes)
- **Problème :** Composants React volumineux combinant la logique d'état complexe, la mise en page et les styles, ce qui nuit à la lisibilité et à la réutilisabilité.
- **Action requise :** Extraire des composants fonctionnels enfants et découper la logique dans des hooks personnalisés.

### [S-02] Colonne state dans nodes sans contrainte CHECK
- **Fichier :** `master/db/models.py:27`
- **Extrait :**
  ```sql
  state TEXT NOT NULL DEFAULT 'PENDING',
  ```
- **Problème :** La colonne `state` de la table `nodes` est de type `TEXT` sans contrainte SQL `CHECK` pour valider l'ensemble des états autorisés décrits en commentaire.
- **Action requise :** Ajouter une contrainte `CHECK(state IN ('PENDING', 'ENROLLING', 'CONNECTED', 'RECONNECTING', 'LOST', 'STALE', 'REVOKED'))`.

### [T-01] Couverture insuffisante sur module critique
- **Fichier :** `master/db/database.py` (90% de couverture de test)
- **Problème :** Le module `master/db/database.py` présente une couverture de 90%, ce qui est inférieur au seuil critique de 95% exigé pour les modules système clés.
- **Action requise :** Écrire des tests unitaires additionnels pour couvrir le pool de connexions (notamment la gestion des fermetures et des exceptions).

### [P-01] Prompts non versionnés (prompts système en dur)
- **Fichier :** `master/api/chat.py:796-801`
- **Extrait :**
  ```python
  "content": (
      "Based on the conversation, determine if a server action is needed. ..."
  )
  ```
- **Problème :** Le prompt système d'extraction des propositions d'actions est codé en dur inline dans l'API de chat.
- **Action requise :** Déplacer le prompt système dans un fichier Markdown distinct sous `master/core/prompts/` à l'instar des autres prompts.

### [P-02] Paramètres modèle hardcodés
- **Fichiers :**
  - `master/api/chat.py:167` (`temperature=0.3`)
  - `master/api/chat.py:812` (`temperature=0.1`)
  - `master/api/admin.py:234` (`max_tokens=5`)
- **Problème :** Paramètres d'appels LLM (`temperature` et `max_tokens`) configurés statiquement dans le code API.
- **Action requise :** Rendre ces paramètres configurables via la classe `Settings` de `master/config.py`.

### [X-03] Config hardcodée (timeouts et constantes)
- **Fichiers :**
  - `worker/connection.go:23` : `heartbeatTimeout = 90 * time.Second`
  - `master/ws/worker_handler.py:50` : `ENROLLMENT_STEP_TIMEOUT = 30.0`
  - `master/ws/worker_handler.py:59` : `WS_CLOSE_TIMEOUT = 4408`
  - `worker/logs.go:14` : `commandTimeout = 30 * time.Second`
  - `worker/wsclient.go:106` : `dialer.Timeout = 10 * time.Second`
  - `worker/containers.go:26` : `Timeout: 30 * time.Second`
  - `master/api/nodes.py:1008` : `timeout=15.0`
- **Problème :** Plusieurs valeurs de timeout sont spécifiées en dur dans les couches Master et Worker.
- **Action requise :** Centraliser l'ensemble de ces valeurs dans la configuration du projet (Master settings / Worker config).

---

## 🟡 Signaux (à surveiller)

### [F-01] Styles inline et Tailwind arbitraires
- **Fichiers :**
  - `frontend/src/components/ui/CardSkeleton.tsx:12` : `style={{ width, height }}`
  - `frontend/src/components/settings/ProfileSettingsTab.tsx:124` : `style={{ backgroundColor: themes[t]['--bg'] }}`
  - `frontend/src/pages/LoginPage.tsx:301` : `bg-[#0a0a0f]`
  - `frontend/src/components/layout/Sidebar.tsx:289` : `border-[#2dd4bf]`
- **Problème :** Usage de styles inline et de valeurs arbitraires Tailwind (`#0a0a0f`, `#2dd4bf`), ce qui nuit à l'homogénéité visuelle.
- **Action requise :** Centraliser ces valeurs dans la configuration du thème CSS de Tailwind CSS v4.

### [F-02] Valeurs magiques dans les timers d'UI
- **Fichiers :**
  - `frontend/src/components/layout/NotifBell.tsx:37` (polling 20000ms)
  - `frontend/src/components/dashboard/TrendChart.tsx:91` (polling 30000ms)
  - `frontend/src/store/chatStore.ts:186` (timeout 30000ms)
- **Problème :** Les temps de polling et de timeout de requêtes sont codés en dur sous forme de valeurs magiques.
- **Action requise :** Déclarer ces variables dans une configuration globale du frontend.

### [G-01] Erreurs ignorées (underscore) en Go
- **Fichiers :**
  - `worker/containers.go:88` : `portsRaw, _ := c["Ports"].([]interface{})`
  - `worker/connection.go:118` : `wc.workerToken, _ = success["worker_token"].(string)`
  - `worker/services.go:48` : `outJSON, _ := json.Marshal(services)`
  - `worker/stats.go:80` : `v, _ := strconv.ParseUint(f, 10, 64)`
- **Problème :** De nombreuses assertions de type, désérialisations JSON ou conversions de types ignorent l'erreur avec `_`, risquant des pannes silencieuses.
- **Action requise :** Implémenter des vérifications strictes des erreurs ou logger les anomalies.

### [G-02] Goroutines lancées sans signal de shutdown
- **Fichiers :**
  - `worker/main.go:115` : `go func() { ... }`
  - `worker/connection.go:212` : `go func() { ... }`
- **Problème :** Des goroutines d'arrière-plan s'exécutent sans mécanisme de fermeture coordonné, ce qui peut créer des fuites de threads lors du redémarrage du Worker.
- **Action requise :** Propager un `context.Context` ou utiliser un canal d'arrêt pour notifier la fin des goroutines.

### [G-04] Magic numbers dans l'allocation de buffers
- **Fichiers :**
  - `worker/wsclient.go:89` : `key := make([]byte, 16)`
  - `worker/wsclient.go:180` : `maskKey := make([]byte, 4)`
  - `worker/wsclient.go:236` : `header := make([]byte, 2)`
- **Problème :** Tailles de buffers codées en dur pour le protocole WebSocket.
- **Action requise :** Définir ces longueurs via des constantes nommées explicites.

### [G-06] Fonctions sans context.Context en Go
- **Fichiers :**
  - `worker/logs.go:19` : `func handleReadLogs(intent Intent)`
  - `worker/containers.go:53` : `func handleListContainers(intent Intent)`
- **Problème :** L'absence de paramètre `context.Context` empêche l'annulation propre des appels Docker/Systemd ou des timeouts d'I/O.
- **Action requise :** Adapter la signature des fonctions pour accepter `ctx context.Context`.

### [B-01] os.getenv hors de config.py
- **Fichiers :**
  - `master/core/secret_loader.py:53` : `value = os.environ.get(env_var)`
  - `master/core/secret_loader.py:58` : `file_path_str = os.environ.get(file_var)`
- **Problème :** Lecture directe des variables d'environnement en dehors du point de configuration centralisé.
- **Action requise :** Charger ces variables à l'intérieur de `master/config.py` dans la classe `Settings`.

### [B-02] settings importé dans master/core/ ou master/api/
- **Fichiers :**
  - `master/api/deps.py:73` : `from master.config import settings`
  - `master/api/auth.py:67` : `from master.config import settings`
- **Problème :** Importation directe globale de l'instance `settings`, violant l'injection de dépendances FastAPI.
- **Action requise :** Privilégier l'usage de `Depends(get_settings)`.

### [B-10] Imports locaux différés
- **Fichiers :**
  - `master/main.py:96` : `import json`
  - `master/api/nodes.py:494` : `import json`
  - `master/config.py:131` : `import logging`
- **Problème :** Présence d'imports de modules au sein de fonctions pour éviter des dépendances cycliques.
- **Action requise :** Corriger l'architecture globale pour éliminer les cycles et remonter les imports.

### [B-11] Code commenté mort
- **Fichiers :**
  - `master/api/nodes.py:326` : `# Demo mode: return mock response`
  - `master/api/nodes.py:452` : `# Demo mode: return mock data`
- **Problème :** Présence de lignes commentées de vieux codes de démonstration.
- **Action requise :** Supprimer ces commentaires obsolètes.

### [PERF-02] asyncio.Queue sans maxsize
- **Fichier :** `master/db/database.py:25` : `self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue()`
- **Problème :** Le pool de connexions SQLite utilise une file d'attente `asyncio.Queue` sans limite de taille (`maxsize`), désactivant le contrôle de capacité du pool.
- **Action requise :** Instancier la file avec `maxsize=size` pour assurer un contrôle de capacité strict.

### [S-01] Migrations non idempotentes
- **Fichier :** `master/db/migrations.py:106` : `CREATE TABLE join_tokens_new (`
- **Problème :** Création de table temporaire dans la migration SQLite sans la clause `IF NOT EXISTS`.
- **Action requise :** Ajouter `IF NOT EXISTS` pour prémunir le schéma de conflits d'idempotence.

### [X-06] Dépendances non whitelistées
- **Fichier :** `requirements.txt`
- **Problème :** Présence des dépendances `bcrypt==4.0.1`, `itsdangerous==2.2.0` et `python-multipart==0.0.20` non whitelistées dans la liste des dépendances autorisées de l'audit.
- **Action requise :** Ajouter ces packages à la liste blanche d'audit ou les retirer.

---

## 📊 Métriques Git

### M-01 : Hot spots (fichiers les plus modifiés)
Les 10 fichiers ayant subi le plus grand nombre de modifications historiques :
- `8` : `master/api/worker_binary.py`
- `5` : `frontend/src/i18n/fr.ts`
- `5` : `frontend/src/i18n/en.ts`
- `5` : `frontend/src/components/modals/AddNodeModal.tsx`
- `4` : `master/config.py`
- `3` : `tests/test_api/test_nodes.py`
- `3` : `master/db/migrations.py`
- `3` : `master/core/node_manager.py`
- `3` : `master/api/nodes.py`
- `3` : `frontend/src/pages/ServersPage.tsx`

### M-02 : Ratio ajout/suppression (dernier sprint)
- **Modifications globales :** `113` fichiers modifiés, `9304` insertions (+), `4366` suppressions (-).
- Le ratio d'insertion/suppression est de ~2.13 (très sain, inférieur au seuil d'alerte de 10).

### M-03 : Commits récents sans tests associés
Sur les 20 derniers commits, 12 commits ont modifié des fichiers source sans adapter ou ajouter de tests associés :
- `de88318` : `ci: apply black, trailing-whitespace and end-of-file fixes`
- `e6ed336` : `ci: add EventBus dependency and apply black formatting`
- `e3dc5b9` : `i18n: complete French/English translations across frontend`
- `07e18ef` : `feat(worker): add --key-dir flag and env var fallbacks for MASTER_URL/JOIN_TOKEN`
- `039e737` : `fix(worker-binary): pass raw public key to minisign -P`
- `066acff` : `fix(worker-binary): use -p file path instead of -P raw key for minisign`
- `e755a0b` : `fix(worker-binary): correct GitHub release URL regex for versioned assets`
- `ea6647a` : `fix(worker-binary): download private GitHub release assets via API`
- `50034b2` : `feat(worker-binary): support GitHub token for private release assets`
- `122faf9` : `fix(worker): cast stat.Bsize to int64 for 32-bit cross-compilation`
- `76d1adf` : `fix: use minisign CLI instead of py-minisign for signature verification`
- `ae2bc4d` : `i18n: add missing keys for server config, toasts, common labels`

---

## 🔍 Nécessite revue humaine

### [DOC-03] Tests de régression pour les bugs documentés dans LIMITS.md
- **Problème :** `docs/LIMITS.md` liste plusieurs scénarios critiques de concurrence sans tests associés (double enrollment simultané, collisions de séquence d'audit, conflit heartbeat/unregister). Aucun test unitaire ou d'intégration ne couvre ces cas limites.
- **Action requise :** Revue humaine requise pour évaluer le besoin et la faisabilité de mocks avancés ou de coroutines parallèles de test.

### [PERF-01] Risque de starvation de transactions SQLite
- **Problème :** SQLite sérialise toutes les écritures au niveau de la base de données. L'utilisation d'un pool de 5 connexions asynchrones concurrentes avec FastAPI et WebSocket peut engendrer des blocages transactionnels lors d'écritures simultanées massives.
- **Action requise :** Évaluer l'usage concurrent en production et planifier la migration vers un SGBD plus robuste tel que PostgreSQL si nécessaire.

### [T-03] Validation du contrat Master/Worker
- **Problème :** Les communications de messages structurés (`STATUS_REPORT`, `ENROLLMENT_REQUEST`, etc.) sont testées via des dictionnaires Python bruts. Il n'existe pas de schéma de validation formel (ex: JSON Schema ou Protobuf) garantissant la compatibilité du protocole indépendamment des implémentations.
- **Action requise :** Valider l'ajout d'une bibliothèque de schémas partagés pour le protocole Master/Worker.

---

## ✅ Points positifs
- **100% des tests unitaires passent** : 277/277 tests unitaires passent avec succès sur l'ensemble de la suite.
- **Couverture élevée globale** : Les modules critiques `security_manager.py` (97%) et `auth.py` (95%) respectent le seuil de couverture de 95%.
- **Dépendances Python impeccablement épinglées** : Aucune dépendance Python n'est libre de version (`D-01`).
- **Présence d'un lockfile frontend** : Un fichier `package-lock.json` est bien présent et à jour (`D-03`).
- **Absence de marqueurs TODO/FIXME orphelins** : Aucun commentaire `TODO`, `FIXME` ou `HACK` non tracé n'a été découvert dans le code source.

---
*Rapport généré par la tâche d'audit automatique.*
*Catalogue de référence : DEBT_CATALOG.md*
*Aucune modification n'a été effectuée dans le code source.*
