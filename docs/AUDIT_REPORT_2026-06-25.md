# Audit Vigile — 2026-06-25
Sprint en cours : 5

## Résumé exécutif

| Priorité | Nombre |
|---|---|
| 🔴 Critique | 2 |
| 🟠 Important | 13 |
| 🟡 Signal | 13 |
| 📊 Métrique | 3 |
| 🔍 Manuel / Non exécuté | 6 |

**Top 3 urgences :**
1. **[T-03] Échecs systématiques dans les tests unitaires de LLM Client** : Mettre à jour les assertions pour correspondre aux messages traduits en français et corriger les attributs manquants sur les mocks.
2. **[B-04] Appels synchrones bloquants dans des points d'accès FastAPI asynchrones** : Remplacer les lectures/écritures de fichiers synchrones par de l'asynchrone ou via `anyio.to_thread`.
3. **[B-05] Boucle de requêtes SQL unitaires avec commit (N+1)** : Réviser la boucle de mise à jour des états dans le node manager pour utiliser une transaction unique globale.

---

## 🔴 Critique (bloquants)

### [T-03] Échecs systématiques dans la suite de tests de LLM Client
- **Fichier :** [test_llm_client.py](file:///Users/flavio/Documents/Projets/Youcloud-API/tests/test_core/test_llm_client.py#L182)
- **Extrait :**
  ```python
  assert "timed out" in events[0]["detail"]
  # E AssertionError: assert 'timed out' in 'Le service IA a mis trop de temps à répondre...'
  ```
- **Problème :** 6 échecs critiques systématiques lors de l'exécution des tests de `llm_client` en raison d'assertions de chaînes attendues en anglais (mais traduites en français par l'API) et d'attributs de mock manquants (`text`).
- **Action requise :** Ajuster les assertions de test pour valider les messages français de l'API et enrichir la structure des mocks dans [test_llm_client.py](file:///Users/flavio/Documents/Projets/Youcloud-API/tests/test_core/test_llm_client.py).

### [B-04] Appels synchrones bloquants dans un endpoint asynchrone
- **Fichiers :**
  - [admin.py:138](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L138) :
    ```python
    with override_path.open("w", encoding="utf-8") as f:
        json.dump(body.dict(), f)
    ```
  - [admin.py:399](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L399) :
    ```python
    with open(plugin_path, "wb") as f:
        f.write(content)
    ```
  - [main.py:97](file:///Users/flavio/Documents/Projets/Youcloud-API/master/main.py#L97) :
    ```python
    with override_path.open("r", encoding="utf-8") as f:
    ```
- **Problème :** L'ouverture ou l'écriture synchrone de fichiers bloque la boucle d'événements (Event Loop) de FastAPI, ce qui peut saturer le serveur lors de requêtes concurrentes.
- **Action requise :** Utiliser des écritures/lectures de fichiers asynchrones (via `aiofiles`) ou déporter le travail sur un thread dédié avec `anyio.to_thread.run_sync`.

---

## 🟠 Important (sprint suivant)

### [B-03] Exception interceptée silencieusement (pass sans log)
- **Occurrences :** 18 occurrences détectées.
- **Fichiers clés :**
  - [node_manager.py:197](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L197) (`except Exception: pass`)
  - [auth.py:181](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py#L181)
  - [chat.py:767](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L767)
  - [admin.py:313](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L313)
- **Problème :** Des structures `except Exception: pass` interceptent toutes les erreurs silencieusement, masquant d'éventuels bugs et rendant le débogage complexe.
- **Action requise :** Enregistrer les exceptions dans les logs via `logger.exception()` ou filtrer sur les exceptions fonctionnelles précises.

### [B-05] Boucle de requêtes SQL unitaires (N+1 SQL / Lock DB)
- **Fichiers :**
  - [node_manager.py:270-271](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L270-L271) :
    ```python
    await db.execute(query, params)
    await db.commit()
    ```
  - [migrations.py:33](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/migrations.py#L33)
- **Problème :** Des écritures et des commits en base sont répétés dans une boucle. Cela multiplie les transactions et augmente le risque de verrou SQLite (`database is locked`).
- **Action requise :** Réaliser les exécutions au sein d'une transaction globale unique avec un commit final.

### [B-06] Interpolation de chaînes dans les requêtes SQL (f-string SQL)
- **Fichiers :**
  - [node_manager.py:269](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L269) : `query = f"UPDATE nodes SET {', '.join(fields)} WHERE id = ?"`
  - [node_manager.py:418](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L418) : `f"UPDATE nodes SET {set_clause} WHERE id = ?"`
  - [node_manager.py:642](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L642) : `await db.execute(f"UPDATE nodes SET {set_clause} WHERE id = ?", values)`
  - [node_manager.py:667](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L667) : `f"UPDATE join_tokens SET consumed = 1, expires_at = ? WHERE id IN ({placeholders})"`
  - [node_manager.py:970](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L970) : `sql = f"SELECT * FROM nodes{where_sql} ORDER BY created_at DESC"`
  - [audit.py:81](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/audit.py#L81) : `count_sql = f"SELECT COUNT(*) as cnt FROM audit_log {where}"`
- **Problème :** Utilisation de f-strings pour concaténer dynamiquement des requêtes SQL, ce qui peut potentiellement exposer le serveur à des injections SQL si les variables ne sont pas contrôlées.
- **Action requise :** Remplacer par des requêtes entièrement paramétrées ou assurer une validation stricte des colonnes interpolées.

### [B-09] Mutations DB sans enregistrement dans l'audit log
- **Fichiers :**
  - [node_manager.py:472](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L472) : `await db.execute("DELETE FROM nodes WHERE id = ?", (node_id,))`
  - [node_manager.py:642](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L642) : `await db.execute(f"UPDATE nodes SET {set_clause} WHERE id = ?", values)`
  - [admin.py:570](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L570) : `await db.execute("DELETE FROM plugin_configs WHERE plugin_id = ?", (plugin_id,))`
  - [demo.py:29](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/demo.py#L29) : `await db.execute("DELETE FROM action_proposals")`
- **Problème :** Des mutations, mises à jour critiques ou suppressions s'effectuent sans appel immédiat à `log_action()`, brisant la traçabilité des actions d'administration.
- **Action requise :** Consigner systématiquement ces mutations de base de données à l'aide d'un appel immédiat à `log_action()`.

### [F-03] Polling non centralisé (multiples `setInterval` locaux)
- **Fichiers :**
  - [NotifBell.tsx:35](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/layout/NotifBell.tsx#L35) : `const interval = setInterval(loadProposals, 20000);`
  - [TimeAgo.tsx:57](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/primitives/TimeAgo.tsx#L57)
  - [TrendChart.tsx:91](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/dashboard/TrendChart.tsx#L91)
- **Problème :** L'UI lance plusieurs boucles de polling isolées via des `setInterval` locaux, augmentant la charge du serveur et réduisant la fluidité de synchronisation.
- **Action requise :** Refactoriser ces appels pour exploiter le hook centralisé [usePolling.ts](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/hooks/usePolling.ts).

### [F-05] Type any TypeScript non justifié
- **Occurrences :** 19 occurrences détectées.
- **Fichiers concernés :**
  - [formatAudit.ts:7](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/utils/formatAudit.ts#L7) : `details?: any;`
  - [Sidebar.tsx:123](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/layout/Sidebar.tsx#L123) : `const renderLink = (item: any) => {`
  - [useSSE.ts:23](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/hooks/useSSE.ts#L23)
  - [LoginPage.tsx:207](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/LoginPage.tsx#L207)
  - [NodeDetail.tsx:38](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/NodeDetail.tsx#L38)
- **Problème :** Affaiblit le typage statique TypeScript et augmente le risque d'erreurs d'exécution dans le navigateur.
- **Action requise :** Définir des types ou des interfaces stricts pour ces entités.

### [F-07] Composants God (> 250 lignes)
- **Occurrences :** 10 fichiers identifiés.
- **Fichiers clés :**
  - [NodeDetail.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/NodeDetail.tsx) (845 lignes)
  - [SettingsPage.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/SettingsPage.tsx) (657 lignes)
  - [Dashboard.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/Dashboard.tsx) (559 lignes)
  - [LoginPage.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/LoginPage.tsx) (460 lignes)
- **Problème :** Ces fichiers cumulent une logique trop importante et violent la responsabilité unique.
- **Action requise :** Scinder les composants complexes en sous-composants fonctionnels et extraire la logique d'état dans des Hooks React personnalisés.

### [F-10] Exports non utilisés (code mort)
- **Occurrences :** 19 occurrences détectées.
- **Fichiers clés :**
  - [AllChatsModal.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/modals/AllChatsModal.tsx) : `AllChatsModal`
  - [ProposalModal.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/modals/ProposalModal.tsx) : `ProposalModal`
  - [HeroInsight.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/dashboard/HeroInsight.tsx) : `HeroInsight`
  - [NodeCard.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/dashboard/NodeCard.tsx) : `NodeCard`
- **Problème :** Des composants et helpers sont exportés mais jamais importés ailleurs dans le projet.
- **Action requise :** Supprimer le code mort s'il s'avère inutile.

### [G-01] Erreurs Go ignorées via l'opérateur underscore
- **Occurrences :** 20 occurrences.
- **Fichiers clés :**
  - [containers.go:80](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/containers.go#L80) : `status, _ := c["Status"].(string)`
  - [connection.go:118](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/connection.go#L118) : `wc.workerToken, _ = success["worker_token"].(string)`
  - [enrollment.go:52](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/enrollment.go#L52)
- **Problème :** Ignorer les erreurs d'assertion de type ou de traitement JSON masque des échecs d'assertion silencieux en production.
- **Action requise :** Remplacer par des assertions explicites avec vérification (ex: `val, ok := x.(string); if !ok { ... }`).

### [G-02] Goroutines sans signal de shutdown dans le Worker
- **Occurrences :** 2 occurrences en code de production, plus dans les tests.
- **Fichiers concernés :**
  - [connection.go:212](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/connection.go#L212) : `go func()`
  - [main.go:110](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/main.go#L110) : `go func()`
- **Problème :** Des boucles infinies ou des traitements parallèles sans canal d'annulation continuent de tourner indéfiniment même après l'arrêt logique du programme.
- **Action requise :** Intégrer un signal d'arrêt (`ctx.Done()` ou channel) dans la boucle de ces goroutines.

### [G-04] Magic numbers dans l'allocation de buffers (Go)
- **Occurrences :** Plusieurs occurrences.
- **Fichiers concernés :**
  - [wsclient.go:89](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/wsclient.go#L89) (`make([]byte, 16)`)
  - [wsclient.go:180](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/wsclient.go#L180) (`make([]byte, 4)`)
  - [reconnect_test.go:87](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/reconnect_test.go#L87) (`make([]byte, 32)`)
- **Action requise :** Centraliser ces tailles de tampons sous forme de constantes nommées.

### [G-06] Fonctions du worker Go sans propagation de `context.Context`
- **Occurrences :** 15+ occurrences détectées.
- **Fichiers clés :**
  - [connection.go:62](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/connection.go#L62) (`Connect`)
  - [connection.go:102](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/connection.go#L102) (`runEnrollment`)
  - [containers.go:29](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/containers.go#L29) (`dockerAPI`)
- **Problème :** Sans contexte, les appels d'API Docker et réseaux du Worker Go ne peuvent pas être annulés dynamiquement en cas de shutdown du service.
- **Action requise :** Ajouter `ctx context.Context` comme premier paramètre dans ces signatures.

### [X-03] Constantes de configuration SQLite et timeouts en dur
- **Occurrences :** 4 occurrences.
- **Fichiers concernés :**
  - [database.py:37](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/database.py#L37) : `timeout=30.0`
  - [database.py:93](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/database.py#L93) : `timeout=30.0`
  - [llm_client.py:70](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/llm_client.py#L70) : `timeout: int = 30`
  - [node_manager.py:769](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L769) : `timeout: float = 30.0`
- **Problème :** La configuration de timeout SQLite et LLM est codée en dur au lieu de s'aligner sur `config.py`.
- **Action requise :** Exposer et lire ces options via l'objet centralisé de configuration `Settings`.

### [X-06] Dépendances installées non whitelistées
- **Périmètre :**
  - **Python (master) :** `bcrypt==4.0.1`, `itsdangerous==2.2.0`, `python-multipart==0.0.20`
  - **Frontend (npm) :** `react-router`
- **Problème :** Des modules de production tiers sont installés sans faire partie des dépendances whitelistées dans la politique de l'architecture.
- **Action requise :** Conduire une validation de sécurité et enrichir la whitelist de dépendances.

---

## 🟡 Signaux (à surveiller)

### [F-01] Styles inline et classes Tailwind arbitraires
- **Occurrences :** 20+ occurrences détectées.
- **Fichiers concernés :**
  - [TopBar.tsx:152](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/layout/TopBar.tsx#L152) : `'bg-[#6366f1]'`
  - [LoginPage.tsx:298](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/LoginPage.tsx#L298) : `'bg-[#0a0a0f]'`
  - [CopilotMessage.tsx:57](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/copilot/CopilotMessage.tsx#L57) : `style={{ animationDelay: '0ms' }}`
  - [ServersPage.tsx:258](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/ServersPage.tsx#L258)
- **Action requise :** Centraliser ces valeurs dans le fichier CSS ou Design System global.

### [F-02] Magic numbers dans timers/timeouts de l'interface
- **Occurrences :** 5 occurrences.
- **Fichiers concernés :**
  - [CopyableId.tsx:53](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/ui/CopyableId.tsx#L53) : `2000` ms
  - [NotifBell.tsx:35](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/layout/NotifBell.tsx#L35) : `20000` ms
  - [TimeAgo.tsx:57](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/primitives/TimeAgo.tsx#L57) : `30000` ms
- **Action requise :** Centraliser ces durées dans un fichier de constantes UI.

### [F-06] `console.warn` ou `console.log` oublié
- **Fichier :** [useNodeEvents.ts:46](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/hooks/useNodeEvents.ts#L46) : `console.warn('SSE connection error, will retry');`
- **Action requise :** Remplacer par un logger UI structuré ou désactiver en production.

### [B-01] Accès aux variables d'environnement hors de `config.py`
- **Occurrences :** 3 occurrences.
- **Fichiers concernés :**
  - [secret_loader.py:53](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/secret_loader.py#L53) : `os.environ.get(env_var)`
  - [migrations.py:120](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/migrations.py#L120) : `os.getenv("TESTING") == "true"`
- **Action requise :** Centraliser toutes les lectures d'environnement exclusivement dans [config.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/config.py).

### [B-02] Importation de `settings` dans `core/` ou `api/`
- **Occurrences :** 3 occurrences.
- **Fichiers concernés :**
  - [auth.py:21](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py#L21) : `from master.config import settings`
  - [deps.py:73](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/deps.py#L73)
  - [deps.py:200](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/deps.py#L200)
- **Action requise :** Remplacer par l'injection de dépendances standard via FastAPI.

### [B-08] Signature de type de retour manquante dans FastAPI ou Core Python
- **Occurrences :** 20+ occurrences.
- **Fichiers concernés :**
  - [auth.py:396](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py#L396) : `async def logout`
  - [auth.py:437](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py#L437) : `async def change_password`
  - [nodes_events.py:63](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/nodes_events.py#L63) : `async def _next_event`
  - [audit.py:67](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/audit.py#L67) : `def compute_entry_hash`
  - [rate_limiter.py:29](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/rate_limiter.py#L29) : `def __init__`
  - [security_manager.py:488](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/security_manager.py#L488) : `def init_security`
- **Action requise :** Ajouter les signatures de retour `-> Type` sur l'ensemble de ces méthodes pour solidifier l'analyse statique (mypy).

### [B-10] Imports différés au sein des fonctions
- **Occurrences :** 12 occurrences (ex: `main.py:95` `import json`, `admin.py:372` `import ast`, `nodes.py:441` `import json`).
- **Action requise :** Positionner toutes les instructions `import` au début du fichier (PEP 8).

### [P-01] Prompts système LLM codés en dur dans Python
- **Occurrences :** 4 occurrences.
- **Fichiers concernés :**
  - [chat.py:813](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L813) (message système du Copilot)
  - [structured_llm.py:73](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/structured_llm.py#L73)
- **Action requise :** Versionner ces messages dans des fichiers Markdown autonomes (ex: `master/core/prompts/`).

### [P-02] Paramètres d'appel de modèles d'IA en dur
- **Occurrences :** 4 occurrences.
- **Fichiers concernés :**
  - [chat.py:167](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L167) (`temperature=0.3`)
  - [chat.py:830](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L830) (`temperature=0.1`)
  - [admin.py:233](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L233) (`max_tokens=5`)
- **Action requise :** Déplacer ces hyperparamètres d'inférence LLM dans la configuration globale.

### [S-02] Colonne status sans contrainte CHECK au niveau SQL
- **Fichier :** [001_initial_schema.py:145](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/alembic/versions/001_initial_schema.py#L145) : `sa.Column("status", sa.String(), nullable=False, server_default="PENDING")`
- **Action requise :** Intégrer un type Enum SQL ou une clause `CHECK (status IN (...))` pour restreindre la validité des statuts en DB.

### [S-03] Migration de base de données ALTER TABLE sans valeur DEFAULT
- **Occurrences :** 5 occurrences.
- **Fichiers concernés :**
  - [migrations.py:48-60](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/migrations.py#L48) (champs `insight_profile`, `insight_profile_generated_at`, etc. sur la table `nodes`).
- **Action requise :** Spécifier une clause `DEFAULT` lors de l'application de migrations étendant les schémas pour sécuriser le traitement de valeurs par défaut.

### [A-01] Duplication de noms de fonctions
- **Occurrences :** 13 occurrences.
- **Fichiers clés :** `verify_chain` (dans `core/audit.py` et `api/nodes.py`), `get_node`, `list_nodes`, `register`.
- **Action requise :** Homogénéiser ou renommer les fonctions pour éviter toute confusion dans les importations croisées.

---

## 📊 Métriques Git

### M-01 : Hot spots (fichiers les plus modifiés)
*Volume de commits cumulés par fichier source :*
1. [deps.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/deps.py) : **12** modifications
2. [node_manager.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py) : **10** modifications
3. [nodes.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/nodes.py) : **10** modifications
4. [worker_handler.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/ws/worker_handler.py) : **9** modifications
5. [main.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/main.py) : **9** modifications

### M-02 : Ratio ajout/suppression (dernier sprint)
- **Ratio insertions/suppressions (10 derniers commits) :** `17025 insertions / 14091 suppressions` = **1.21**.
Le ratio de modifications reste équilibré, marquant une restructuration saine sans inflation incontrôlée de lignes de code.

### M-03 : Commits récents sans tests associés (Lookback 20)
*Commits introduisant des modifications de code sans modification conjointe des dossiers de tests (`tests/`) :*
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

## 🔍 Nécessite revue humaine / Non exécuté

### [DOC-01] Validation des routes README vs code
- **Statut :** **Partiellement exécuté** (les commandes regex `grep -P` automatiques n'ont pas pu être exécutées sur l'environnement local macOS due aux options non supportées).
- **Description :** L'analyse manuelle montre une concordance parfaite pour l'ensemble des routes documentées dans `README.md` (les routes `POST /api/auth/*`, `GET/DELETE /api/nodes/*`, `GET /api/audit` et `GET /api/admin/audit-verify` sont bien toutes implémentées dans FastAPI).

### [DOC-02] Fichiers déclarés dans SESSION.md mais absents
- **Statut :** **Non exécuté** (le fichier `SESSION.md` est absent de la racine du projet et du répertoire de documentation).

### [DOC-03] Absence de tests de régression pour les scénarios de LIMITS.md
- **Statut :** **Non exécuté** (revue manuelle requise).
- **Description :** Absence de couverture pour les limites critiques documentées dans [LIMITS.md](file:///Users/flavio/Documents/Projets/Youcloud-API/docs/LIMITS.md) :
  - *Double enrôlement simultané concurrent* (exclusion mutuelle SQLite lors de l'enregistrement de jeton).
  - *heartbeat + unregister race condition* (WebSocket coupé au moment même de l'enregistrement d'état).
  - *audit sequence collision* (concurrence lors des appels de `log_action`).

### [D-02] CVE connues (Revue manuelle Python)
- **Statut :** **Non exécuté** (`pip-audit` n'est pas installé sur le système local).
- **Description :** L'analyse des modules de production externes (`bcrypt==4.0.1`, `itsdangerous==2.2.0`, `python-multipart==0.0.20`) doit être effectuée manuellement pour anticiper les CVE connues.

### [PERF-01] Performance de la vérification de la chaîne d'audit
- **Description :** La méthode `verify_chain` effectue un parcours séquentiel complet de la table `audit_log` pour recalculer les empreintes successives. Ce traitement peut saturer les entrées/sorties Master sur une base volumineuse.

### [PERF-02] File d'attente asyncio sans maxsize
- **Fichier :** [database.py:25](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/database.py#L25)
- **Extrait :**
  ```python
  self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue()
  ```
- **Problème :** Le pool de connexions SQL utilise une file d'attente sans taille limite (`maxsize=0`), ce qui peut engendrer une fuite de ressources ou une allocation non contrôlée en cas de dysfonctionnement concurrentiel.

---

## ✅ Points positifs

- **[T-01] Excellente couverture sur les modules critiques (97%) :**
  - **[auth.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py) :** **97%**
  - **[security_manager.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/security_manager.py) :** **97%**
  - **[database.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/database.py) :** **98%**
- **[T-02] Lancement et validation des tests d'intégration :** La marque `@pytest.mark.skip` a été levée sur `test_api_integration_flow` dans [test_integration.py](file:///Users/flavio/Documents/Projets/Youcloud-API/tests/test_api/test_integration.py). Les tests d'intégration s'exécutent avec succès (276 tests passent).
- **[D-01] Dépendances Python épinglées :** Toutes les dépendances listées dans `requirements.txt` ont leurs versions figées de manière stricte (`==`).
- **[D-03] Lockfile frontend présent :** Présence de [package-lock.json](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/package-lock.json) assurant la répétabilité du build côté React.
- **[D-04] Standardisation du Worker Go :** Le Worker ne fait appel qu'à la bibliothèque standard (stdlib only) de Go 1.23, limitant la surface d'attaque logicielle.
- **[S-01] Migrations de base de données idempotentes :** Utilisation systématique de clauses conditionnelles du type `CREATE TABLE IF NOT EXISTS` sur l'ensemble du schéma.
- **[P-03] Robustesse des tests de régression LLM :** Plus de 83 assertions et mocks valident le comportement face aux interactions LLM (structured_llm, rate_limiting, timeouts).
- **[X-09] Absence de TODO/FIXME orphelins :** Aucune directive de développement non attribuée ou temporaire n'a été détectée dans le code.
- **[A-02] Code sans commentaires didactiques :** Aucun commentaire didactique trivial n'a été trouvé.
- **[A-03] Pas d'abstractions superflues :** Aucune architecture YAGNI complexe.
- **[G-03] Pas de panics Go :** Aucune fonction du Worker Go ne fait appel à `panic` ou `recover`.
- **[G-05] Pas de concaténations Go complexes :** Pas de concaténation inefficace de chaînes de caractères dans des boucles.

---
*Rapport généré par la tâche d'audit automatique.*
*Catalogue de référence : DEBT_CATALOG.md*
*Aucune modification n'a été effectuée dans le code source.*
