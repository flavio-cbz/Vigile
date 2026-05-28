# 🔍 Audit Technique Senior — Vigile

**Auditeur** : IA Senior (Architecture, Backend, UI/UX)
**Date** : 26 mai 2026
**Scope** : Backend Python (master/), Frontend React (frontend/), Worker Go (worker/), BDD SQLite
**Méthode** : Analyse statique complète du code source, confrontation à l'état de l'art

---

## Verdict Global (3 phrases, sans filtre)

**Le backend est solide sur les fondations cryptographiques mais structurellement fragile dès qu'on pense charge, concurrence ou résilience — le verrou global sur l'audit et la connexion SQLite unique sont des bombes à retardement.** Le frontend est un monolithe JSX de 271 KB réparti sur 8 fichiers-pages géants (Dashboard.tsx fait 1021 lignes) où la logique métier, le fetching, le parsing et le rendu sont fusionnés dans le même composant — c'est l'antithèse de React idiomatique et c'est intenable passé un sprint. **Le Worker Go est la meilleure partie du projet : sobre, correct, stdlib-only, bien scopé — ne le touchez pas.**

---

## 🔴 Bloquant

### B1. Fichiers-pages monolithiques frontend (💣 à refaire)

| Fichier | Lignes | Octets |
|---------|--------|--------|
| [Dashboard.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Dashboard.tsx) | 1021 | 52 KB |
| [NodeDetail.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/NodeDetail.tsx) | ~950 | 48 KB |
| [Plugins.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Plugins.tsx) | ~900 | 44 KB |
| [Settings.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Settings.tsx) | ~700 | 34 KB |
| [VigilInsights.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/components/ui/VigilInsights.tsx) | 665 | 31 KB |
| [Chat.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Chat.tsx) | 699 | 26 KB |

**Le problème** : Chaque page contient *tout* — définitions de types, fetching brut via `fetch()`, logique de transformation de données, calculs dérivés, state local, modals inline, rendering conditionnel massif. `Dashboard.tsx` fait 1021 lignes dont 650+ de JSX pur. C'est un fichier impossible à tester unitairement, à refactorer partiellement, et à debug efficacement.

**Symptômes concrets** :
- Duplication massive du code de fetching (headers `Authorization`, gestion 401, JSON parsing) — répété identiquement dans Dashboard, Chat, VigilInsights, NodeDetail
- Le hook `useApi.ts` existe (61 lignes, bien fait) mais **n'est utilisé nulle part** — les pages utilisent `fetch()` brut directement
- Les types `Proposal`, `ChatSession`, `MetricsMap` sont définis localement dans chaque fichier au lieu d'un barrel `types/`
- Les modals sont rendues conditionnellement dans le corps de la page au lieu d'être gérées par un système centralisé

> [!CAUTION]
> Un fichier React de 1021 lignes n'est pas un composant, c'est un script PHP déguisé. Ce n'est pas un problème de style — c'est structurellement incompatible avec la maintenabilité, le testing, et la collaboration.

---

### B2. Connexion SQLite unique = point de défaillance unique

[database.py](file:///f:/Youcloud/Documents/Projets/Youcloud-API/master/db/database.py) — Documenté dans LIMITS.md mais jamais corrigé.

Tout le système — API REST, WebSocket enrollment, heartbeat monitor, audit trail, métriques — partage **une seule connexion aiosqlite**. Un `verify_chain` sur un audit de 100K entrées bloque littéralement tout le serveur.

**Ce que j'aurais fait** : Un pool de 3-5 connexions en lecture avec une connexion dédiée en écriture (WAL le permet nativement). aiosqlite supporte ça via plusieurs instances. Pas besoin de PostgreSQL, juste d'un wrapper `ConnectionPool` de 40 lignes.

---

### B3. Verrou global sur l'audit (`_audit_lock`) = sérialisation de toutes les mutations

[audit.py](file:///f:/Youcloud/Documents/Projets/Youcloud-API/master/core/audit.py) — Un `asyncio.Lock()` global sérialise *toutes* les écritures d'audit.

C'est correct du point de vue de l'intégrité de la chaîne de hachage, mais c'est un goulot d'étranglement architectural. Chaque mutation DB (création de nœud, approbation de proposal, login, changement de mot de passe) attend son tour derrière ce lock.

**Ce que j'aurais fait** : Écriture en batch avec un buffer asynchrone. Les événements d'audit sont mis en file (asyncio.Queue), un worker dédié les dépile par lots de N toutes les 100ms, calcule la chaîne de hash séquentiellement dans le worker, et insère en une seule transaction. Latence perçue : ~0ms (feu et oublie). Intégrité : identique. Débit : ×50.

---

### B4. Pas de refresh token automatique côté frontend

[authStore.ts](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/store/authStore.ts) — Le store stocke `refreshToken` mais ne l'utilise **jamais**.

Quand le JWT expire, [useApi.ts](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/hooks/useApi.ts) (L31-37) fait juste `logout()`. L'utilisateur est éjecté à chaque expiration de token. Le backend a un endpoint `/api/auth/refresh` complet avec rotation de famille et détection de vol — mais le frontend l'ignore.

**Impact** : Si `jwt_access_token_ttl` est court (15 min comme recommandé), l'utilisateur est déconnecté toutes les 15 minutes. Si long (24h pour compenser), la fenêtre d'exposition du token est inacceptable.

---

### B5. `main.py` est un God File de 906 lignes

[main.py](file:///f:/Youcloud/Documents/Projets/Youcloud-API/master/main.py) — Contient l'app FastAPI, le lifespan, les middlewares, 8 endpoints admin inline, la gestion des plugins, le upload de fichiers, la configuration LLM, le toggle de plugins, la suppression de plugins, le kickstart script...

**Ce que j'aurais fait** : `main.py` ≤ 80 lignes. Un router `admin.py` dédié. Les endpoints admin sont dans `master/api/admin.py`. Le lifespan est dans `master/lifecycle.py`. Les middlewares sont dans `master/middleware.py`.

---

### B6. 🔴 BUG CRITIQUE : Re-enrollment des nœuds LOST/STALE/RECONNECTING impossible

[worker_handler.py L194+202](file:///f:/Youcloud/Documents/Projets/Youcloud-API/master/ws/worker_handler.py#L194-L202) — Le code autorise l'enrollment depuis les états `LOST`, `STALE`, `RECONNECTING` (L194), puis appelle `transition_state(db, node_id, NodeState.ENROLLING)` (L202). **Mais `VALID_TRANSITIONS` dans `node_manager.py` ne contient PAS** les transitions `(LOST → ENROLLING)`, `(STALE → ENROLLING)`, ni `(RECONNECTING → ENROLLING)`. Seul `(PENDING → ENROLLING)` existe.

**Impact** : Un Worker qui se déconnecte et tente de se réenrôler lèvera un `ValueError` silencieux. Le Worker est bloqué à jamais — il faut supprimer le nœud et en recréer un. C'est un bug en production.

**Fix** : Ajouter `(LOST, ENROLLING)`, `(STALE, ENROLLING)`, `(RECONNECTING, ENROLLING)` dans `VALID_TRANSITIONS`.

---

### B7. Secret JWT unique pour tous les types de tokens

[security_manager.py L277, L335, L365](file:///f:/Youcloud/Documents/Projets/Youcloud-API/master/core/security_manager.py) — Les worker tokens, user access tokens, et user refresh tokens utilisent tous le **même `_jwt_secret`**. Si un worker token est compromis (leak du token dans un log, capture réseau), l'attaquant peut forger des access tokens utilisateur.

**Ce que j'aurais fait** : 3 secrets distincts dérivés d'un master secret via HKDF (ou simplement 3 env vars séparées `JWT_ACCESS_SECRET`, `JWT_REFRESH_SECRET`, `JWT_WORKER_SECRET`).

---

## 🟡 Important

### I1. Pattern Netflix "carrousels" — mauvaise métaphore pour le monitoring

Le Dashboard utilise des `PluginRow` horizontaux scrollables (carrousels) pour afficher les proposals et les conversations. **C'est une métaphore de découverte (Netflix : "tu ne sais pas ce que tu veux") appliquée à un outil d'action (monitoring : "montre-moi ce qui brûle").** 

Un opérateur homelab veut :
1. **En 2 secondes** : est-ce que tout va bien ? (→ HealthBanner ✅ bien fait)
2. **En 5 secondes** : qu'est-ce qui nécessite mon attention ? (→ devrait être une liste triée par priorité, pas un carrousel)
3. **En 10 secondes** : agir (→ approuver/rejeter directement, pas ouvrir un modal)

Les carrousels horizontaux cachent l'information. Un carrousel de 10 proposals dont 3 sont PENDING force un scroll horizontal pour trouver les urgences. Une table triée par statut + risque avec action inline serait 10× plus efficace.

**Alternative** : Remplacer les PluginRow par un composant `ActionFeed` vertical, trié par priorité (PENDING HIGH en haut), avec boutons approve/reject inline sans modal.

---

### I2. Audit trail SHA-256 : faux sentiment de sécurité

La chaîne de hachage est intègre **dans le contexte applicatif**, mais :

- Si un attaquant a accès au fichier SQLite, il peut recalculer toute la chaîne depuis le genesis. Le hash est calculé avec des données disponibles dans la même DB. Il n'y a pas d'ancrage externe (timestamp signé par un tiers, publication blockchain, etc.).
- Le genesis hash est `"0" * 64` — hardcodé et prédictible.

**Ce que j'aurais fait** : Publier périodiquement (toutes les 100 entrées) un hash de checkpoint sur un canal externe (webhook vers un service tiers, append dans un fichier log signé séparément, ou simple notification Ntfy). Pas besoin de blockchain — juste un témoin externe qui rend la réécriture détectable.

---

### I3. Markdown parser custom dans Chat.tsx — réinvention de la roue

[Chat.tsx L378-468](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Chat.tsx#L378-L468) — Un parser markdown maison qui gère `**bold**`, `` `code` ``, les listes, les blocs de code fencés. 90 lignes de regex fragile.

**Problèmes** :
- Ne gère pas les liens, headers, tableaux, italique, blockquotes
- Les regex sont naïves (splitting sur `\n\n` casse les blocs de code multi-paragraphes)
- Vulnérable aux edge cases du markdown LLM (qui génère du markdown varié)

**Alternative** : `react-markdown` + `rehype-highlight` (2 dépendances, ~15KB gzipped, support complet). Ou si zéro-dépendance : `marked` (5KB) + `DOMPurify` (3KB) avec `dangerouslySetInnerHTML` dans un conteneur sandboxé.

> [!WARNING]
> La whitelist de dépendances backend (RULES.md §12) mentionne seulement les dépendances Python et Go. Le frontend React utilise déjà React, Zustand, Recharts, Tailwind, Lucide, clsx — la contrainte "zéro dépendance" ne s'applique visiblement pas au frontend. Utiliser `react-markdown` est cohérent.

---

### I4. Polling HTTP au lieu de WebSocket pour les mises à jour temps réel

Le frontend utilise `setInterval(poll, 60000)` pour rafraîchir les données ([Dashboard.tsx L166-171](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Dashboard.tsx#L166-L171)). Le Master a déjà une infrastructure WebSocket robuste pour les Workers.

**Ce que j'aurais fait** : Un endpoint WebSocket `/ws/dashboard` qui push les événements en temps réel (node online/offline, proposal créée, métriques mises à jour). Le frontend s'abonne et met à jour le store Zustand via `onmessage`. Latence : sub-seconde au lieu de 60 secondes.

---

### I5. Double duplication de la logique `setNodes` dans nodeStore

[nodeStore.ts](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/store/nodeStore.ts) — La logique de sélection automatique (single node → auto-select, node disparu → fallback to 'all') est **dupliquée identiquement** dans `setNodes` (L37-63) et dans `fetchNodes` (L94-115). C'est un bug en devenir — toute correction dans un endroit sera oubliée dans l'autre.

---

### I6. `_pending_intents` jamais nettoyé après timeout

Documenté dans LIMITS.md mais jamais corrigé. Les `Future` résolus par timeout laissent une entrée fantôme dans le dict. Sur un serveur long-running avec beaucoup d'intents (LLM qui génère des actions), c'est une fuite mémoire lente.

**Fix** : Un `WeakValueDictionary` ou un cleanup dans `send_intent` quand le Future est résolu.

---

### I7. Upload de plugin = exécution de code arbitraire

[main.py L644-738](file:///f:/Youcloud/Documents/Projets/Youcloud-API/master/main.py#L644-L738) — L'endpoint `/api/admin/plugins/upload` vérifie la syntaxe Python et la présence d'une fonction `register`, puis **exécute le code** via `load_plugin()` qui fait un `importlib.import_module()`. 

La validation AST est triviale à contourner. Un plugin peut faire `os.system("rm -rf /")` dans `register()` ou dans un hook. La vérification que `register(pm)` existe ne valide pas le contenu des autres fonctions.

**Ce que j'aurais fait** : Sandbox via `subprocess` + `seccomp` si Linux, ou au minimum : liste blanche des imports autorisés via analyse AST complète (vérifier tous les `Import`/`ImportFrom` nodes), et exécution dans un namespace restreint.

---

### I8. Pas de type-safety sur les réponses API côté frontend

### I9. `SecurityManager` lève `HTTPException` — couplage core → framework

[security_manager.py L370-399](file:///f:/Youcloud/Documents/Projets/Youcloud-API/master/core/security_manager.py#L370-L399) — `verify_access_token()` et `verify_refresh_token()` lèvent `HTTPException` (FastAPI). C'est une violation directe de la règle d'isolation du core : les classes core ne doivent pas dépendre du framework web. Ça rend impossible le test unitaire sans importer FastAPI.

**Fix** : Lever des exceptions domaine (`InvalidTokenError`, `ExpiredTokenError`) et les convertir en `HTTPException` dans `deps.py`.

---

### I10. `transaction()` n'est pas une vraie transaction

[database.py L65-80](file:///f:/Youcloud/Documents/Projets/Youcloud-API/master/db/database.py) — Le context manager `transaction()` fait `yield db` puis `commit()`, mais n'émet pas de `BEGIN IMMEDIATE`. En SQLite WAL, les écritures concurrentes sans `BEGIN IMMEDIATE` peuvent s'entrelacer.

**Fix** : Ajouter `await db.execute("BEGIN IMMEDIATE")` au début du context manager.

---

### I11. `threading.RLock` dans un contexte asyncio

[deps.py L137](file:///f:/Youcloud/Documents/Projets/Youcloud-API/master/api/deps.py#L137) — Le lazy singleton LLM utilise un `threading.RLock()` pour la synchronisation. En asyncio, un lock threading peut bloquer l'event loop si deux requêtes concurrentes tentent de l'acquérir. Devrait être un `asyncio.Lock` avec un pattern `async def get_or_create_llm_client()`.

---

Le frontend fait `await res.json() as T` partout — c'est un cast TypeScript, pas une validation. Si le backend change un champ (`cpu_percent` → `cpu_pct`), le frontend silently affiche `undefined` sans aucune erreur.

**Ce que j'aurais fait** : Un schema de validation runtime léger (Zod, valibot, ou même des type guards manuels) au point d'entrée de chaque réponse API.

---

## 🟢 Cosmétique

### C1. `html { font-size: 90% }` — hack global

[index.css L72-74](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/index.css#L72-L74) — Réduire le `font-size` racine à 90% pour "un layout haute densité professionnel" casse tous les calculs rem des bibliothèques tierces et rend l'interface inaccessible aux personnes avec des paramètres de taille de police système.

**Alternative** : Utiliser les utilities Tailwind `text-xs`, `text-sm` sur les composants spécifiques. Le `rem` doit rester à 16px pour l'interopérabilité.

---

### C2. Grain texture overlay `z-index: 9999`

[index.css L90-98](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/index.css#L90-L98) — Le pseudo-élément `body::before` avec `z-index: 9999` et une texture SVG noise est au-dessus de tout, y compris des modals et des toasts. C'est compensé par `pointer-events: none`, mais c'est une bombe visuelle si un composant a besoin d'un z-index supérieur (dropdown natif, tooltip).

---

### C3. Tailles de police en fractions de rem

Les pages utilisent des tailles comme `text-[0.5625rem]`, `text-[0.6875rem]`, `text-[0.625rem]`. Combiné avec le `font-size: 90%` global, les tailles réelles sont respectivement **8.1px, 9.9px, 9px**. C'est en dessous du seuil de lisibilité WCAG (9px minimum recommandé pour le texte informationnel).

---

### C4. `localStorage` polling via `setInterval` pour sync entre composants

[Dashboard.tsx L89-99](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Dashboard.tsx#L89-L99) — Un `setInterval(500ms)` poll `localStorage` pour détecter les changements de mode avancé. C'est du polling actif pour de la communication inter-composant.

**Alternative** : Mettre `advancedMode` dans le `layoutStore` Zustand (qui existe déjà). Zéro polling, réactivité instantanée.

---

### C5. Version hardcodée `"0.2.0-sprint2"` à 3 endroits

La version est hardcodée dans `main.py` L222, L351, et probablement ailleurs. Un seul endroit de vérité (`__version__` dans un module, ou `pyproject.toml`) éviterait les drifts.

---

## 💣 Recommencer Ici

### 💣1. La couche data-fetching du frontend — JETER et refaire

**Justification technique** : Le frontend n'a pas de couche data. Chaque page fait ses propres `fetch()` avec ses propres headers, sa propre gestion d'erreur, sa propre transformation de données. Le hook `useApi.ts` existe mais est ignoré. Les types sont dupliqués. Il n'y a pas de cache, pas d'invalidation, pas de retry, pas de déduplication de requêtes.

**Alternative concrète** :

```text
frontend/src/
├── api/
│   ├── client.ts          # fetch wrapper avec auth, refresh auto, retry
│   ├── types.ts           # Types centralisés (Proposal, Node, ChatSession, etc.)
│   ├── nodes.ts           # API functions: fetchNodes, fetchNodeStats, etc.
│   ├── chat.ts            # API functions: sendMessage, loadSession, etc.
│   ├── proposals.ts       # API functions: fetchProposals, approve, reject
│   └── insights.ts        # API functions: fetchInsights, analyzeAnomaly
├── hooks/
│   ├── useNodes.ts        # Custom hook wrapping nodeStore + fetching
│   ├── useProposals.ts    # Custom hook for proposals data lifecycle
│   └── useChat.ts         # Custom hook for chat streaming
```

Chaque page devient un assemblage de hooks et de composants de présentation. Dashboard passe de 1021 lignes à ~150.

---

### 💣2. Les composants-pages Dashboard et NodeDetail — JETER et refaire

**Justification technique** : Dashboard.tsx (1021 lignes) et NodeDetail.tsx (~950 lignes) ne sont pas refactorable partiellement car la logique, le state, le fetching et le rendu sont si entremêlés que toucher une partie casse les autres. 

**Alternative concrète** : Découper chaque page en 5-8 composants focalisés :

```text
Dashboard/
├── Dashboard.tsx              # ~80 lignes, orchestration seulement
├── DashboardHeader.tsx        # Titre + boutons d'action
├── ProposalFeed.tsx           # Liste de proposals avec actions inline
├── ChatSessionList.tsx        # Liste des conversations récentes
├── PluginOverview.tsx         # Cartes des 3 plugins
├── FleetMetricsPanel.tsx      # Métriques agrégées (collapsible)
└── ServerCard.tsx             # Carte individuelle de serveur
```

---

## 📋 Plan d'Action (ordonné par priorité)

### Phase 0 — Bugs bloquants (immédiat)

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 0a | **Ajouter les transitions manquantes** (LOST/STALE/RECONNECTING → ENROLLING) | Élimine B6 (bug prod) | 15 min |
| 0b | **Séparer les secrets JWT** (access, refresh, worker) | Élimine B7 | 1h |
| 0c | **Remplacer HTTPException dans SecurityManager** par des exceptions domaine | Élimine I9 | 1h |

### Phase 1 — Fondations critiques (1-2 sprints)

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 1 | **Créer la couche `api/`** frontend avec client HTTP, types centralisés, et refresh token automatique | Élimine B1 + B4 + I8 | 2-3 jours |
| 2 | **Implémenter le pool de connexions SQLite** (3 read + 1 write) | Élimine B2 | 1 jour |
| 3 | **Refactorer Dashboard.tsx** en 6-8 composants + custom hooks | Élimine B1 partiellement | 2-3 jours |
| 4 | **Extraire les endpoints admin** de main.py vers `api/admin.py` | Élimine B5 | 0.5 jour |

### Phase 2 — Robustesse (1 sprint)

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 5 | **Audit trail : buffer asynchrone** (Queue + batch insert) | Élimine B3 | 1 jour |
| 6 | **Remplacer le parser markdown custom** par react-markdown | Élimine I3 | 0.5 jour |
| 7 | **Nettoyer `_pending_intents`** avec TTL + cleanup | Élimine I6 | 0.5 jour |
| 8 | **Sandboxer l'upload de plugins** (AST import whitelist) | Réduit I7 | 1 jour |
| 8b | **Corriger `transaction()`** avec `BEGIN IMMEDIATE` | Élimine I10 | 15 min |
| 8c | **Remplacer `threading.RLock`** par `asyncio.Lock` dans deps.py | Élimine I11 | 30 min |

### Phase 3 — UX (1 sprint)

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 9 | **Remplacer les carrousels proposals** par un ActionFeed vertical | Élimine I1 | 1 jour |
| 10 | **WebSocket dashboard** pour push temps réel | Élimine I4 | 2 jours |
| 11 | **Retirer `html { font-size: 90% }`** et ajuster les composants | Élimine C1 + C3 | 1 jour |
| 12 | **Ancrage externe de l'audit trail** (checkpoint webhook) | Réduit I2 | 1 jour |

### Phase 4 — Polish

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 13 | Refactorer NodeDetail.tsx (même pattern que Dashboard) | Code quality | 2 jours |
| 14 | Refactorer Plugins.tsx et Settings.tsx | Code quality | 2 jours |
| 15 | Centraliser `advancedMode` dans layoutStore | Élimine C4 | 0.5 jour |
| 16 | Version unique (`__version__`) | Élimine C5 | 0.5 jour |

---

## Annexe : Ce qui est BIEN fait (pour ne pas tout casser)

| Composant | Verdict | Détail |
|-----------|---------|--------|
| **Worker Go** | ✅ Excellent | Stdlib-only, RFC 6455 à la main, backoff exponentiel, whitelist hardcodée, 0 dépendance. Le meilleur code du projet. |
| **Ed25519 handshake** | ✅ Excellent | Challenge/response propre, single-use token atomique, vérification de signature correcte. |
| **State machine des nœuds** | ✅ Solide | Transitions validées, matrix explicite, pas de transitions implicites. |
| **Plugin system (hooks)** | ✅ Bien conçu | Pattern Pluggy-like natif, dispatch sync/async, auto-registration. |
| **Design system CSS** | ✅ Cohérent | Palette HSL harmonieuse, design tokens bien organisés, glass-panel réutilisable. |
| **Audit trail concept** | ✅ Bien pensé | SHA-256 chain, séquence monotone, genesis anchor. L'idée est bonne même si l'implémentation a des limites (voir I2). |
| **RULES.md** | ✅ Exemplaire | DI, typing, testing, zéro-dep — des standards stricts qui ont clairement produit du code de meilleure qualité que la moyenne. |
| **Test coverage 93%** | ✅ Remarquable | Pour un projet solo avec 189 tests, c'est sérieux. |
| **usePolling hook** | ✅ Bien fait | Shared interval registry, deduplication, cleanup. Un des rares bons patterns frontend. |

---

> **Résumé en une phrase** : Le backend a les bons instincts (crypto, audit, DI, tests) mais les mauvais patterns d'infrastructure (connexion unique, lock global, god file) ; le frontend a le bon design visuel mais la mauvaise architecture logicielle (monolithes, pas de couche data, fetching dupliqué) ; le Worker Go est irréprochable.
