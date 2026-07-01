# Audit Vigile — 2026-06-27
Sprint en cours : 5 (Présumé, SESSION.md absente)

## Résumé exécutif
| Priorité | Nombre |
|---|---|
| 🔴 Critique | 14 |
| 🟠 Important | 47 |
| 🟡 Signal | 123 |
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
- **Fichier :** `frontend/src/utils/formatAudit.ts:7`
  - **Extrait :** `details?: any;`
  - **Problème :** Typage lâche `any` affaiblissant le typage statique du frontend.
  - **Action requise :** Remplacer par un type d'objet d'audit strict ou `Record<string, unknown>`.
- **Fichier :** `frontend/src/components/layout/TopBar.tsx:160`
  - **Extrait :** `onClick={() => setTheme(t as any)}`
  - **Problème :** Coercition sauvage de type TypeScript `as any`.
  - **Action requise :** Typé correctement le thème ou utiliser une énumération/union string correspondante.
- **Fichier :** `frontend/src/components/layout/Sidebar.tsx:126`
  - **Extrait :** `const renderLink = (item: any) => {`
  - **Problème :** Argument typé comme `any`.
  - **Action requise :** Définir une interface ou un type `SidebarItem`.
- **Fichier :** `frontend/src/components/modals/AllChatsModal.tsx:14`
  - **Extrait :** `history: any[];`
  - **Problème :** Utilisation d'un tableau générique `any[]`.
  - **Action requise :** Créer un type `ChatMessage` explicite.
- **Fichier :** `frontend/src/components/node-detail/types.ts:40`
  - **Extrait :** `raw?: any;`
  - **Problème :** Champ non typé.
  - **Action requise :** Remplacer par `unknown` ou un type structuré.

### [G-01] Erreurs ignorées (underscore) (20 items)
- **Fichier :** `worker/connection.go:118`
  - **Extrait :** `wc.workerToken, _ = success["worker_token"].(string)`
  - **Problème :** Assertion de type effectuée en ignorant si la conversion a échoué (underscore).
  - **Action requise :** Vérifier le booléen d'assertion pour éviter les paniques ou états incohérents.
- **Fichier :** `worker/connection.go:139`
  - **Extrait :** `challenge, _ := challengeMsg["challenge"].(string)`
  - **Problème :** Échec d'assertion ignoré.
  - **Action requise :** Implémenter une gestion d'erreur robuste.
- **Fichier :** `worker/containers.go:75`
  - **Extrait :** `id, _ := c["Id"].(string)`
  - **Problème :** Assertion de type lâche sans validation.
  - **Action requise :** Valider l'assertion et loguer en cas d'incohérence de l'API Docker.

### [G-02] Goroutines sans signal de shutdown (2 items)
- **Fichier :** `worker/connection.go:212`
  - **Extrait :** `go func() { ...`
  - **Problème :** Démarrage d'une goroutine asynchrone sans mécanisme de propagation du shutdown.
  - **Action requise :** Utiliser `context.Context` pour annuler proprement la tâche asynchrone.
- **Fichier :** `worker/main.go:115`
  - **Extrait :** `go func() { ...`
  - **Problème :** Tâche asynchrone lancée sans contrôle d'arrêt propre.
  - **Action requise :** Contrôler l'event loop via un signal système ou un context de shutdown.

---

## 🟡 Signaux (à surveiller)

### [F-01] Styles inline et couleurs arbitraires (26 items)
- **Fichier :** `frontend/src/components/ui/CardSkeleton.tsx:12`
  - **Extrait :** `style={{ width, height }}`
  - **Problème :** Les styles inline nuisent à la cohérence graphique du design system.
  - **Action requise :** Remplacer par des classes Tailwind ou des variables CSS gérées par le thème.
- **Fichier :** `frontend/src/components/layout/TopBar.tsx:154`
  - **Extrait :** `t === 'warm-dark' ? 'bg-[#6366f1]' : ...`
  - **Problème :** Couleurs de thème codées en dur avec Tailwind arbitraire (`bg-[#6366f1]`).
  - **Action requise :** Intégrer les couleurs au design system global de Tailwind v4.

### [F-02] Magic numbers dans timers frontend (11 items)
- **Fichier :** `frontend/src/components/layout/NotifBell.tsx:24`
  - **Extrait :** `const interval = setInterval(loadProposals, 20000);`
  - **Problème :** Intervalle de rafraîchissement codé en dur (20000ms).
  - **Action requise :** Centraliser sous forme de constante de configuration ou utiliser le hook unifié `usePolling`.

### [B-10] Imports différés (20 items)
- **Fichier :** `master/core/action_proposal.py:289`
  - **Extrait :** `import json`
  - **Problème :** Importation différée de la bibliothèque standard au milieu d'une méthode.
  - **Action requise :** Déplacer les imports en haut du fichier pour respecter les standards PEP 8 et la configuration globale.

### [G-06] Fonctions Go sans context.Context (62 items)
- **Fichier :** `worker/connection.go:62`
  - **Extrait :** `func (wc *WorkerConn) Connect() error`
  - **Problème :** La fonction d'établissement de connexion réseau ne propage pas de contexte d'annulation ou de timeout.
  - **Action requise :** Ajouter `ctx context.Context` en premier paramètre.

### [PERF-02] asyncio.Queue sans maxsize (1 item)
- **Fichier :** `master/db/database.py:25`
  - **Extrait :** `self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue()`
  - **Problème :** Queue asynchrone initialisée sans limite de taille, risque théorique d'OOM sous charge massive.
  - **Action requise :** Définir une taille maximale (ex: `maxsize=5` ou calquée sur `pool_size`).

### [X-06] Dépendances non whitelistées (3 items)
- **Fichier :** `requirements.txt`
  - **Extrait :** `bcrypt==4.0.1`, `itsdangerous==2.2.0`, `python-multipart==0.0.20`
  - **Problème :** Présence de dépendances de runtime tierces non répertoriées dans la whitelist stricte de `RULES.md`.
  - **Action requise :** Vérifier si ces paquets sont des sous-dépendances requises par FastAPI/Jose ou les supprimer.

---

## 📊 Métriques Git

### [M-01] Hot spots (fichiers les plus modifiés)
Les 5 fichiers subissant le plus de modifications récentes sont :
```
 8 master/api/worker_binary.py
 7 frontend/src/i18n/fr.ts
 7 frontend/src/i18n/en.ts
 6 master/config.py
 5 frontend/src/components/modals/AddNodeModal.tsx
```

### [M-02] Ratio ajout/suppression (dernier sprint)
Le diff global montre :
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