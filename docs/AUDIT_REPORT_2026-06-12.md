# Audit Technique & Dette Technique — Projet Vigile (2026-06-12)

Ce rapport présente les résultats de l'audit technique complet du projet **Vigile**, un fleet manager pour homelab, structuré selon le catalogue de dette technique.

---

## 1. Métriques Quantitatives & Vue d'Ensemble

### Statistiques de Code (Layers)
* **Backend (Python / FastAPI)** : 42 fichiers, 10 465 lignes de code
* **Frontend (TS / React 19)** : 77 fichiers, 11 382 lignes de code
* **Worker (Go stdlib)** : 16 fichiers, 2 140 lignes de code
* **Tests (pytest)** : 35 fichiers, 6 574 lignes de code

### Git Hotspots (Fichiers les plus modifiés)
1. `master/api/deps.py` (8 modifications)
2. `master/ws/worker_handler.py` (7 modifications)
3. `master/main.py` (7 modifications)
4. `master/config.py` (7 modifications)
5. `master/core/node_manager.py` (6 modifications)
6. `master/api/nodes.py` (6 modifications)

---

## 2. Findings & Anti-patterns Détectés

### 2.1. Frontend (React 19 / TS / Tailwind v4)

#### **F-05 : Utilisation du type `any`**
* **Fichier + Ligne** : [CommandPalette.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/ui/CommandPalette.tsx#L185-L187)
* **Code** :
  ```typescript
  const [results, setResults] = useState<any[]>([]);
  const [selectedItem, setSelectedItem] = useState<any | null>(null);
  ```
* **Fichier + Ligne** : [Dashboard.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/dashboard/Dashboard.tsx#L44) (ou pages)
* **Fichier + Ligne** : [useStore.ts](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/store/useStore.ts#L50-L55)
* **Action requise** : Remplacer `any` par des interfaces strictes (`Node`, `Notification`, etc.).

#### **F-07 : Composants trop volumineux (God Components)**
* **Fichiers** :
  * [CommandPalette.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/ui/CommandPalette.tsx) (~450 lignes)
  * [Dashboard.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/Dashboard.tsx)
* **Action requise** : Découper les composants en sous-composants réutilisables et externaliser la logique d'état complexe dans des hooks personnalisés (`useCommandPalette`, `useDashboardData`).

---

### 2.2. Backend (Python / FastAPI / aiosqlite)

#### **B-01 : Fuite de configuration (import direct de `settings`)**
* **Fichiers + Lignes** :
  * [auth.py:24](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py#L24) : `from master.config import settings`
  * [worker_handler.py:77](file:///Users/flavio/Documents/Projets/Youcloud-API/master/ws/worker_handler.py#L77) : `from master.config import settings`
* **Action requise** : Injecter la configuration via la route FastAPI (`Depends(get_settings)`) ou à travers l'initialisation de la classe de couche métier supérieure, conformément aux principes de DI-at-edge.

#### **B-02 : Non-respect de l'injection de dépendances (DI-at-edge)**
* **Fichier + Ligne** : [node_manager.py:292](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L292)
* **Code** :
  ```python
  from master.api.deps import get_insights_manager
  ```
* **Action requise** : Ne pas importer des utilitaires ou dépendances de la couche API dans la couche métier Core. Passer `InsightsManager` via le constructeur ou la signature de la méthode.
* **Fichiers + Lignes** : [admin.py:29-30](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L29-L30) importent directement les singletons `node_manager` et `plugin_manager` au lieu d'utiliser les dépendances FastAPI `Depends(get_node_manager)`.

#### **B-04 : Appels I/O bloquants dans des routes asynchrones**
* **Fichier + Ligne** : [admin.py:395](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L395)
* **Code** :
  ```python
  with open(plugin_path, "wb") as f:
      f.write(file.file.read())
  ```
* **Fichier + Ligne** : [admin.py:532](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L532) : `os.remove(plugin_path)`
* **Action requise** : Remplacer par des lectures/écritures asynchrones (`aiofiles`) ou déléguer via `asyncio.to_thread` ou `run_in_executor`.

#### **B-05 : Requêtes N+1 et boucles asynchrones**
* **Fichier + Ligne** : [node_manager.py:237](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L237)
* **Code** :
  ```python
  for row in rows:
      # ...
      await db.execute(query, params)
  ```
* **Action requise** : Remplacer les mises à jour individuelles par des requêtes de mise à jour groupées (Bulk Updates) ou regrouper les appels dans une seule transaction optimisée.

#### **B-06 : Utilisation de f-strings pour requêtes SQL**
* **Fichier + Ligne** : [audit.py:47](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/audit.py#L47)
* **Code** :
  ```python
  query = f"SELECT * FROM audit_log WHERE {where_clause} ORDER BY sequence DESC LIMIT ?"
  ```
* **Action requise** : Utiliser un constructeur de requête paramétré plus robuste ou s'assurer que le filtrage ne concatène aucune valeur utilisateur non validée.

#### **B-07 : Magic strings pour états métier**
* **Fichier + Ligne** : [action_proposal.py:34](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/action_proposal.py#L34)
* **Code** :
  ```python
  status: str = "PENDING"
  ```
* **Action requise** : Utiliser des énumérations Python (`Enum`) pour représenter les différents états d'une proposition d'action (`PENDING`, `APPROVED`, `REJECTED`, `EXECUTED`, `FAILED`).

#### **B-08 : Fonctions sans annotation de type**
* **Fichiers + Lignes** : 19 occurrences trouvées, notamment :
  * [docker_plugin.py:58](file:///Users/flavio/Documents/Projets/Youcloud-API/master/plugins/docker_plugin.py#L58) : `def register(pm)` (pas de type pour `pm`, pas de type de retour)
  * [auth.py:392](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py#L392) : `logout` sans type de retour
  * [admin.py:50](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L50) : `verify_audit_chain(claims)` sans type pour `claims`
* **Action requise** : Compléter toutes les signatures avec des types explicites et `-> None` si la fonction ne retourne rien.

#### **B-09 : Mutations DB sans appel à `log_action`**
* **Fichiers + Lignes** :
  * [admin.py:557](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L557) : `DELETE FROM plugin_configs`
  * [demo.py:31](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/demo.py#L31) : `DELETE FROM action_proposals`
* **Action requise** : Appeler la fonction `log_action` après ces suppressions pour garantir la traçabilité complète requise par la politique d'audit.

#### **B-10 : Imports différés**
* **Fichiers + Lignes** :
  * [node_manager.py:198-199](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L198)
  * [node_manager.py:292](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L292)
  * [deps.py:191-192](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/deps.py#L191)
* **Action requise** : Centraliser les imports en haut de fichier. En cas de dépendances circulaires, découper ou déplacer les types concernés.

---

### 2.3. Go Worker

#### **G-01 : Erreurs et retours d'assertions de type ignorés**
* **Fichiers + Lignes** :
  * [connection.go:118](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/connection.go#L118) : `wc.workerToken, _ = success["worker_token"].(string)`
  * [containers.go:75](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/containers.go#L75) : `id, _ := c["Id"].(string)`
  * [enrollment.go:52](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/enrollment.go#L52) : `pubData, _ := json.Marshal(pub)`
* **Action requise** : Toujours tester le booléen d'assertion (`val, ok := x.(T)`) et traiter les erreurs retournées par `json.Marshal` ou `json.Unmarshal`.

#### **G-04 : Magic numbers dans la configuration des buffers / timeouts**
* **Fichiers + Lignes** :
  * [wsclient.go:89](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/wsclient.go#L89) : `key := make([]byte, 16)`
  * [wsclient.go:106](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/wsclient.go#L106) : `dialer.Timeout = 10 * time.Second`
* **Action requise** : Remplacer par des constantes nommées et documentées.

#### **G-06 : Fonctions sans argument `context.Context`**
* **Fichiers + Lignes** : Presque toutes les fonctions d'E/S (réseau, Docker, processus) du Worker :
  * [connection.go:62](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/connection.go#L62) : `func (wc *WorkerConn) Connect() error`
  * [containers.go:29](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/containers.go#L29) : `func dockerAPI(...)`
* **Action requise** : Passer `ctx context.Context` comme premier argument pour propager les signaux d'annulation et gérer proprement les timeouts.

---

### 2.4. Transversal, Prompts & Tests

#### **X-03 : Config/Timeout hardcodée dans les clients API**
* **Fichiers + Lignes** :
  * [services.py:71](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/services.py#L71) : `timeout=15.0`
  * [chat.py:381](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L381) : `timeout=15.0`
  * [admin.py:223](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L223) : `timeout=10`
* **Action requise** : Déclarer ces valeurs dans `settings` (`config.py`) pour les rendre paramétrables.

#### **X-06 : Dépendances Python non whitelistées**
* **Fichier** : [requirements.txt](file:///Users/flavio/Documents/Projets/Youcloud-API/requirements.txt)
* **Dépendances concernées** : `bcrypt==4.0.1`, `itsdangerous==2.2.0`, `python-multipart==0.0.20`
* **Action requise** : Les ajouter formellement à la whitelist ou justifier leur conservation.

#### **P-01 : Prompts système non versionnés (déclarés en ligne / f-strings)**
* **Fichier + Ligne** : [chat.py:704-767](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L704-L767)
* **Code** : Prompt système construit dynamiquement avec des f-strings complexes.
* **Action requise** : Externaliser ces templates de prompts dans des fichiers YAML ou Markdown indépendants sous un répertoire `/prompts` pour en assurer le suivi de version.

#### **P-02 : Paramètres modèle LLM hardcodés**
* **Fichiers + Lignes** :
  * [chat.py:169](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L169) : `temperature=0.3`
  * [chat.py:806](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L806) : `temperature=0.1`
  * [admin.py:228](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L228) : `max_tokens=5`
* **Action requise** : Exposer ces variables via `settings` (`config.py`).

#### **T-01 : Couverture de test des modules critiques insuffisante (< 95%)**
* **Statut de Couverture** :
  * `master/api/auth.py` : **88%** (Seuil requis: 95%)
  * `master/core/security_manager.py` : **85%** (Seuil requis: 95%)
  * `master/db/database.py` : **83%** (Seuil requis: 95%)
  * **Globale** : **86%**
* **Action requise** : Ajouter des tests unitaires ciblant les branches non couvertes (notamment la gestion d'erreurs d'initialisation de clés Ed25519 et les cas limites de révocation de tokens).

#### **S-02 : Absences de contraintes `CHECK` en base de données**
* **Fichier** : [models.py](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/models.py)
* **Tables concernées** : `nodes` (colonne `state`) et `action_proposals` (colonne `status`).
* **Action requise** : Ajouter des contraintes SQL `CHECK` au niveau du schéma de base de données (ex: `CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXECUTED', 'FAILED'))`).

---

## 3. Synthèse & Actions Immédiates

### Synthèse de la Dette
| Catégorie | Findings Majeurs | Impact | Priorité |
|---|---|---|---|
| **Sécurité & Données** | SQL f-strings (B-06), Absence CHECK (S-02), Mutations sans audit log (B-09) | Critique | Haute |
| **Qualité & Tests** | Couverture critique < 95% (T-01) | Majeur | Haute |
| **Architecture** | Violation DI-at-edge (B-02), Fuite settings (B-01), Imports différés (B-10) | Moyen | Moyenne |
| **Robustesse Worker** | Assertions & erreurs Go ignorées (G-01), Pas de Context (G-06) | Majeur | Haute |
| **IA & Prompts** | Prompts et hyperparamètres LLM en dur (P-01, P-02) | Moyen | Basse |

*Note: Toutes les commandes n'ayant pas pu être exécutées ou n'ayant retourné aucune occurrence ont été documentées conformément aux exigences.*
