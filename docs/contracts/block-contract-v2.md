# Block Contract v2 — J1 SIGN-OFF

**Document de référence unique** pour le catalogue de blocs déclaratifs V2. Ce contrat est la source de vérité pour J2 (catalogue de blocs), J3a (loader backend), J3b (BlockRenderer + SWR) et J4 (migration par plugin).

**Vérité terrain vérifiée** : chaque affirmation est traçable à `docs/plans/migration_master_plugins.md` (Parties 1-4) ou au code source réel (liens fournis dans chaque section). Les écarts entre le plan et le code sont notés et signalés.

---

## 1. Spécification du MetaSchemaV2

Le meta-schéma V2 est implémenté dans `master/core/plugin_manifest.py` (lignes 217-374). Il s'agit d'un contrat déclaratif strict, fail-closed à deux couches.

### 1.1 Pré-pass fail-closed (couche 1)

Avant toute analyse Pydantic, la fonction `validate_manifest_v2_raw(json_bytes: bytes) -> dict` (ligne 235) applique trois garde-fous sur le JSON brut :

| Garde-fou | Constante | Valeur | Code |
|-----------|-----------|--------|------|
| Taille maximale | `MAX_MANIFEST_V2_BYTES` | 64 KB (65 536 octets) | Ligne 217 |
| Profondeur maximale | `MAX_MANIFEST_V2_DEPTH` | 5 niveaux (racine = niveau 1) | Ligne 218 |
| Parseabilité | — | `json.loads` avec `RecursionError` capturé | Lignes 250-253 |

La fonction `_max_json_depth(value, level=1)` (ligne 221) calcule la profondeur maximale de tout sous-arbre. La racine est le niveau 1 ; chaque conteneur dict/list imbriqué ajoute un niveau. Une profondeur de 5 signifie racine + 4 niveaux de conteneurs.

**Comportement** : si la taille dépasse 64 KB, si le JSON ne parse pas, ou si la profondeur dépasse 5, une `ValueError` est levée. Le manifeste est rejeté (fail-closed).

### 1.2 Modèle Pydantic V2 (couche 2)

`PluginManifestV2` (ligne 318) utilise `ConfigDict(extra="forbid", str_strip_whitespace=True)`. Tous les sous-modèles (`RouteV2`, `PageV2`, `PermissionV2`) utilisent également `extra="forbid"`. Aucun champ inconnu n'est accepté à aucun niveau d'imbrication.

| Champ | Type | Obligatoire | Description |
|-------|------|-------------|-------------|
| `schema_version` | `int` | Oui (défaut: 2) | Numéro de version du méta-schéma. La registry oriente sur cette valeur (`{1: V1, 2: V2}`). |
| `id` | `str` | Oui | Identifiant stable du plugin. Pattern : `^[a-z][a-z0-9_]+$`. |
| `version` | `str` | Oui | Version sémantique. Pattern : `^\d+\.\d+\.\d+$`. |
| `hooks` | `list[str]` | Non (défaut: `[]`) | Noms des hooks souscrits, ex. `on_node_connect`. |
| `pages` | `list[PageV2]` | Non (défaut: `[]`) | Pages UI déclaratives contribuées par le plugin. |
| `routes` | `list[RouteV2]` | Non (défaut: `[]`) | Routes HTTP déclaratives. |
| `config_schema` | `dict \| None` | Non (défaut: `None`) | Schéma de configuration consommé par le formulaire de config frontend. |
| `permissions` | `list[PermissionV2] \| None` | Non (défaut: `None`) | Entrées de permission demandées depuis le catalogue fermé core-owned. |
| `external_auth_domains` | `list[str] \| None` | Non (défaut: `None`) | Domaines externes autorisés pour les popups d'authentification (ex. `["plex.tv"]`). Validé contre la liste blanche core. |

### 1.3 Sous-modèles

**RouteV2** (ligne 263) — `extra="forbid"` :
| Champ | Type | Obligatoire | Description |
|-------|------|-------------|-------------|
| `path` | `str` | Oui | Chemin URL, ex. `/api/widgets/foo`. |
| `method` | `str` | Oui | Méthode HTTP, ex. `GET`. |
| `handler` | `str` | Oui | Chemin d'import pointé du callable handler. |
| `roles` | `list[str]` | Non (défaut: `[]`) | Rôles autorisés. Liste vide = public. |

**PageV2** (ligne 280) — `extra="forbid"` :
| Champ | Type | Obligatoire | Description |
|-------|------|-------------|-------------|
| `id` | `str` | Oui | Identifiant de la page, utilisé pour le slug de route. |
| `title` | `str` | Oui (min_length=1) | Titre humain. |
| `component` | `str` | Oui | Nom du composant React à rendre. |
| `sidebar` | `bool` | Non (défaut: `False`) | Afficher dans la sidebar. |
| `params` | `list[str]` | Non (défaut: `[]`) | Paramètres de route dynamiques, ex. `['containerId']`. |
| `roles` | `list[str]` | Non (défaut: `[]`) | Rôles autorisés à voir la page. |

**PermissionV2** (ligne 299) — `extra="forbid"` :
| Champ | Type | Obligatoire | Description |
|-------|------|-------------|-------------|
| `name` | `str` | Oui | Identifiant de permission du catalogue, ex. `restart_service`. |
| `description` | `str \| None` | Non | Description humaine optionnelle. |

### 1.4 Projection legacy `pages[]`

Le loader dérive la projection legacy `pages[]` (id/title/icon/roles/route) depuis V2 pour alimenter `GET /api/plugins/pages` (API V1) et le `PluginRouter` legacy pendant la strangler fig. **Un seul registre canonique, zéro drift.** Le champ `trusted` n'apparaît pas dans le contrat UI V2 — il reste dans le manifest d'exécution (backend-only, in-process vs subprocess isolé).

---

## 2. Matrice des variantes d'état par bloc

Chaque bloc déclare cinq variantes d'état : `idle | busy | error | empty | data`. Ces variantes sont la clé de voûte de l'invisibilité du frontend — les états vides en français et le spinner orange garantissent que le catalogue V2 ne casse aucun état existant.

### 2.1 Variantes d'état

| Variante | Déclencheur | Rendu |
|----------|-------------|-------|
| `idle` | Avant le premier fetch | Skeleton ou placeholder minimal. |
| `busy` | Fetch en cours, aucune donnée précédente | Spinner orange `border-t-2 border-orange-500` sur fond `bg-zinc-800` (ou `border-zinc-800`). |
| `error` | Fetch échoué | ErrorBoundary par bloc + message d'erreur. |
| `empty` | Fetch réussi, résultat vide | Carte vide avec icône `AlertCircle` et texte français. |
| `data` | Fetch réussi, données présentes | Rendu normal du contenu. |

### 2.2 Chaînes de caractères vides (français, vérifiées)

| Plugin | Fichier | Chaîne exacte | Ligne |
|--------|---------|---------------|-------|
| Docker | `frontend/src/plugins/docker/pages/DockerContainers.tsx` | `Aucun conteneur trouvé` | Ligne 174 |
| Systemd | `frontend/src/plugins/systemd/pages/SystemdServices.tsx` | `Aucun service trouvé` | Ligne 166 |
| Metrics | `frontend/src/plugins/metrics/pages/MetricsHistory.tsx` | `Aucune métrique enregistrée` | Ligne 138 |

### 2.3 Token de spinner occupé

Le spinner `busy` utilise le token Tailwind exact :

```
border-t-2 border-orange-500
```

Vérifié dans :
- `DockerContainers.tsx` ligne 168 : `border-t-2 border-orange-500 border-zinc-800`
- `MetricsHistory.tsx` ligne 132 : `border-t-2 border-orange-500 border-zinc-800`
- `PluginRouter.tsx` ligne 68 et 77 : `border-t-2 border-orange-500 border-zinc-800`

### 2.4 ErrorBoundary par bloc

Chaque bloc est enveloppé dans un `ErrorBoundary` (précédent frontend : le wrapper `CopilotPanel` dans `RootLayout.tsx`). Un bloc défaillant ne doit jamais vider la page entière. Le fallback ErrorBoundary reproduit le pattern existant : message d'erreur + option de retry.

---

## 3. Modèle de contexte de bloc

Le contexte de bloc est l'interface par laquelle un bloc déclaratif communique avec le shell Vigile. Il est construit par le `BlockRenderer` (J3b) et injecté dans chaque composant de bloc.

### 3.1 Paramètres (`params`)

Les paramètres proviennent du manifeste V2 (`PageV2.params` et `RouteV2`). Le `BlockRenderer` extrait les paramètres de route depuis `useParams()` (React Router) et les injecte dans le contexte.

### 3.2 Injection `node_id` via `needs:["node_id"]`

Lorsqu'un bloc déclare `needs: ["node_id"]` dans son manifeste, le contexte injecte `node_id` depuis le **sélecteur global `nodeStore`** (`useNodeStore`). Le bloc ne lit jamais le store directement — c'est le contexte qui le fait.

**Précédent MetricsHistory** : `MetricsHistory.tsx` ligne 28 lit actuellement `const { nodes } = useNodeStore()` directement dans le composant plugin. Le modèle V2 inverse cela : le `BlockRenderer` lit le store et injecte `node_id` dans le contexte, le code plugin ne touche jamais au store. C'est la règle V2 — le code plugin ne lit jamais le store.

**Vérification du store** : `frontend/src/store/nodeStore.ts` expose `useNodeStore` (Zustand) avec `nodes`, `selectedNodeId`, `selectedNode`, `selectNode()`, `fetchNodes()`. Le sélecteur global `useNodeStore((s) => s.nodes)` est le point d'entrée pour la résolution de `node_id`.

### 3.3 API restreinte (`RestrictedPluginAPI`)

Les méthodes `navigate`, `navigateGlobal`, `config`, `toast`, `t` du contexte miroitent l'API existante `RestrictedPluginAPI` (`frontend/src/plugins/PluginAPI.ts` lignes 6-53), qui préfixe toutes les requêtes à `/api/plugins/{plugin_id}/` :

| Méthode | Comportement | Code |
|---------|-------------|------|
| `fetch(path, options)` | Préfixe `/api/plugins/{pluginId}{path}` | Ligne 27 |
| `navigate(path)` | Navigation relative : `/plugins/{pluginId}{path}` | Ligne 37 |
| `navigateGlobal(path)` | Navigation absolue dans l'app Vigile | Ligne 42 |
| `config` | Configuration du plugin (lecture seule, `Object.freeze`) | Ligne 20 |
| `t(key, params)` | Traduction scope plugin (fallback global `t()`) | Ligne 47 |
| `toast(message, type)` | Notification toast via `useToastStore` | Ligne 51 |

**Wiring** : `PluginRouter.tsx` (lignes 34-84) instancie `RestrictedPluginAPI` avec `page.plugin_id`, `page.title`, `config` (vide pour l'instant), et `navigate` (React Router `useNavigate`). Le composant plugin reçoit `api` et `routeParams` en props.

### 3.4 Rôles depuis la session

Les rôles proviennent de la session utilisateur (`useAuthStore`). `PluginRouter.tsx` ligne 89 : `const userRole = user?.role || 'viewer'`. La filtration des pages autorisées (lignes 96-104) utilise un index de rôles `{ viewer: 0, operator: 1, admin: 2 }` et compare `userLevel >= pageLevel`.

### 3.5 Appels de données via `data:{command}`

Les appels de données sont effectués via la syntaxe `data:{command}` qui mappe à une entrée du registre de commandes (section 5). Le `BlockRenderer` (J3b) résout `data:{command}` en appelant le handler backend correspondant via `useBlockData` (hook SWR first-party, J3b).

---

## 4. Règles de non-régression

Les règles de non-régression garantissent que la migration V2 ne casse aucun comportement utilisateur existant. Elles sont définies dans le plan §2.3.1 et vérifiées contre le code.

### 4.1 Routes `ui.pages[].route` identiques (bookmarks survivent)

**Règle** : les valeurs `ui.pages[].route` doivent rester IDENTIQUES après migration. C'est une règle de processus — les signets (bookmarks) survivent si les routes ne sont pas renommées.

**Vérification** : le `PluginRouter.tsx` (ligne 119) dérive `relativePath` de `page.route.replace('/plugins/', '')`. Les routes actuelles sont :
- Docker : `/plugins/docker/containers`
- Systemd : `/plugins/systemd/services`
- Metrics : `/plugins/metrics/history`
- Plex : `/plugins/plex`

Ces routes doivent être préservées dans la projection V2 `pages[]`.

### 4.2 États loading/empty/error répliqués par les variants de bloc

**Règle** : les états `loading`, `empty`, `error` doivent être répliqués par les variantes de bloc (`busy`, `empty`, `error`). Le spinner orange `border-t-2 border-orange-500` et les cartes vides françaises ("Aucun conteneur trouvé") sont les références.

**Vérification** :
- `DockerContainers.tsx` : état `loading` (ligne 166-170), état `empty` (ligne 171-178 avec "Aucun conteneur trouvé"), état `error` (ligne 35-43 via `api.toast`).
- `MetricsHistory.tsx` : état `loading` (ligne 130-134), état `empty` (ligne 135-142 avec "Aucune métrique enregistrée").

### 4.3 Tokens de survol (hover) comme tokens de configuration de bloc

**Règle** : les trois tokens de survol des boutons d'action doivent être des tokens de configuration de bloc.

**Vérification** dans `DockerContainers.tsx` (lignes 256-283) — trois boutons d'action (stop, start, restart) :

| Action | Token de survol | Ligne |
|--------|-----------------|-------|
| Stop | `hover:bg-zinc-800` | Ligne 261 |
| Start | `hover:bg-green-custom/10` | Ligne 270 |
| Restart | `hover:bg-orange-500/10` | Ligne 279 |

Les trois tokens (`zinc-800`, `green-custom/10`, `orange-500/10`) doivent être exprimés comme tokens de configuration de bloc dans le catalogue V2, pas hardcodés dans le composant.

### 4.4 Sidebar dual-path préservée

**Règle** : la sidebar dual-path doit être préservée — `/nodes/{id}?tab=` pour docker/systemd, `/plugins/plex` pour plex.

**Vérification** dans `Sidebar.tsx` :

| Plugin | Chemin | Ligne | Condition |
|--------|--------|-------|-----------|
| Systemd | `/nodes/${activeNodeId}?tab=services` | Ligne 147 | `isSystemdActive` |
| Plex | `/plugins/plex` | Ligne 156 | `isPlexActive` |
| Docker | `/nodes/${activeNodeId}?tab=containers` | Ligne 161 | `isDockerActive` |

La liste `activePlugins` est initialisée en dur à la ligne 29 : `['systemd', 'docker', 'metrics', 'disk_analysis', 'clean_logs', 'plex']`, puis mise à jour dynamiquement depuis `/api/admin/plugins` (lignes 33-47). La migration doit préserver ce dual-path — docker et systemd restent accessibles via `/nodes/{id}?tab=` (onglets NodeDetail) ET via `/plugins/docker/containers` et `/plugins/systemd/services`.

---

## 5. Format du registre de commandes

Le registre de commandes est **code-derived** — il découle du scan des décorateurs `@route` dans le code source des plugins, jamais du manifeste. C'est la vérité terrain pour la migration.

### 5.1 CommandEntry

Défini dans `master/core/command_registry.py` (ligne 40) comme un dataclass `frozen=True` :

| Champ | Type | Description |
|-------|------|-------------|
| `plugin_id` | `str` | Plugin propriétaire de la route (id manifest canonical). |
| `name` | `str` | Nom de commande namespacé `<plugin_id>.<handler>` — format S1 namespace `id + "."`. |
| `method` | `str` | Méthode HTTP, majuscule (GET/POST/PUT/DELETE/PATCH). |
| `path_template` | `str` | Chemin de route tel que déclaré dans `@route` (ex. `/{node_id}/photo`). |
| `mutation` | `bool` | `True` pour POST/PUT/DELETE/PATCH — doit passer par ActionProposal. |
| `roles` | `tuple[str, ...]` | Rôles minimum requis par le décorateur `@route` (défaut `("viewer",)` si omis). |
| `resource_contract` | `str` | Domaine de ressource — le plugin id (code-derived ; un plugin possède exactement un domaine). |

### 5.2 Fonctions de scan

| Fonction | Description | Code |
|----------|-------------|------|
| `scan_all_routes(plugins)` | Scanne tous les plugins pour les handlers `@route`. Prend un mapping `plugin_id → instance|module`. Pure — pas de dépendance engine/DB/fs. | Ligne 124 |
| `scan_loaded_engine(engine)` | Wrapper sur `engine._instances`. | Ligne 164 |
| `_scan_plugin_instance(plugin_id, instance)` | Shape class-based : lit `__plugin_route__` sur les attributs de classe. | Ligne 94 |
| `_scan_plugin_module(plugin_id, module)` | Shape module-level (legacy `register(pm)`) : scanne les fonctions du module. | Ligne 110 |

Le décorateur `@route` (`plugin_base.py` ligne 102) stampe `fn.__plugin_route__ = {"path": path, "method": method, "roles": _roles}` avec `_roles` par défaut `["viewer"]`.

### 5.3 Inventaire des commandes (vérité terrain vérifiée)

| Plugin | `@route` en code | Routes | Mutations |
|--------|-----------------|--------|-----------|
| metrics | 1 | GET `/history` (roles défaut → viewer) | 0 |
| docker | 1 | GET `/containers` (admin, operator) | 0 |
| plex | **15** | 11 GET + 3 POST + 1 DELETE | 5 |
| systemd | 1 | GET `/services` (admin, operator) | 0 |
| **Total** | **18** | | **5** |

**Routes plex (15 en code)** :

| Méthode | Path | Rôles | Mutation |
|---------|------|-------|----------|
| GET | `/{node_id}/detect` | operator, viewer | Non |
| GET | `/{node_id}/sessions` | operator, viewer | Non |
| DELETE | `/{node_id}/sessions/{session_key}` | admin, operator | Oui |
| GET | `/{node_id}/transcodes` | operator, viewer | Non |
| GET | `/{node_id}/files` | operator, viewer | Non |
| POST | `/{node_id}/library/{section_id}/scan` | admin, operator | Oui |
| GET | `/{node_id}/photo` | operator, viewer | Non (MEDIA/BINARY) |
| GET | `/{node_id}/library` | operator, viewer | Non |
| GET | `/{node_id}/users` | operator, viewer | Non |
| GET | `/{node_id}/history` | operator, viewer | Non |
| GET | `/{node_id}/stats` | operator, viewer | Non |
| POST | `/auth/pin` | admin, operator | Oui |
| POST | `/auth/verify` | admin, operator | Oui |
| GET | `/servers` | admin, operator | Non |
| POST | `/config/server` | admin, operator | Oui |

### 5.4 Écarts manifeste vs code (drift documenté)

**Plex** : le manifeste déclare 8 routes, le code en contient 15. Les 7 routes manquantes du manifeste sont : `/{node_id}/sessions/{session_key}` (DELETE), `/{node_id}/transcodes`, `/{node_id}/files`, `/{node_id}/library/{section_id}/scan` (POST), `/{node_id}/photo`, `/{node_id}/history`, `/{node_id}/stats`.

> **Note de discrépance** : le plan §2.1.4 et le fichier `learnings.md` (J1-T4) affirment que plex a **11** `@route` en code. Le code réel et le fichier de test `tests/test_command_registry.py` (ligne 92, assertion `len(entries) == 15`) confirment **15**. Le plan et le learnings.md sont erronés sur ce point. Le test (ligne 101) note que 4 routes sont des ajouts "plex-tabs" (`/{node_id}/transcodes`, `/{node_id}/files`, `/{node_id}/library/{section_id}/scan`, `/{node_id}/sessions/{session_key}`) et que 3 sont manquantes du manifeste (`/photo`, `/history`, `/stats`). La vérité terrain est **15 routes en code, 8 dans le manifeste**.

**Docker** : le manifeste déclare `GET /containers` uniquement. Le code ne déclare qu'une seule route `@route("/containers", method="GET")`. Le frontend POSTe cependant `/containers/${containerId}/${action}` (DockerContainers.tsx ligne 53) — **ce POST est un 404 aujourd'hui**. L'action de redémarrage de conteneur vit dans `master/api/services.py` (`/api/nodes/{node_id}/containers/{container_id}/restart`), pas dans le plugin. Le registre de commandes code-derived ne doit jamais inventorer ce POST — il est code-derived, pas manifest-derived.

### 5.5 `/batch` read-only

Le endpoint `/batch` est **read-only uniquement** (plan §2.1.5). Les mutations restent des POST individuels (préserve le canal ActionProposal + la comptabilité de rate par action). `/batch` rejette les commandes de mutation avec un 403. Chaque sous-requête de `/batch` est débitée contre le budget de son propre type (READS vs MUTATIONS) — voir S5.

---

## 6. Modèle de permissions (S7)

Le modèle de permissions est un catalogue fermé, core-owned. La vérification s'effectue au dispatch par intersection.

### 6.1 Catalogue fermé

Le catalogue est core-owned — un plugin ne peut demander qu'à appartenir à un catalogue existant par nom. L'intersection s'applique au dispatch :

```
role ≥ min_role  ET  p ∈ manifest.permissions  ET  resource_contract  ET  node_scope
```

| Condition | Description |
|-----------|-------------|
| `role ≥ min_role` | Le rôle de l'utilisateur est supérieur ou égal au rôle minimum du catalogue. |
| `p ∈ manifest.permissions` | La permission est déclarée dans le manifeste V2 (`permissions: list[PermissionV2]`). |
| `resource_contract` | Le contrat de ressource est vérifié (le plugin possède exactement un domaine). |
| `node_scope` | Toute injection `needs:[node_id]` re-vérifie l'accès nœud. |

### 6.2 Vérification node_scope

Toute injection `needs:[node_id]` est soumise au **même contrôle d'accès nœud que `/api/nodes`** — le même helper partagé. Le bloc reçoit `node_id` uniquement si l'utilisateur a accès à ce nœud.

Pour `/batch` : chaque sous-requête node-scopée re-vérifie l'accès nœud — pas de vérification globale de lot. Les blocs sans `needs` (stats globales, config) restent sur le modèle plat.

### 6.3 Mutations via ActionProposal

Toutes les mutations passent par `ActionProposal` (PENDING → APPROVED → EXECUTED/FAILED). Vérifié : les actions docker affichent déjà "as approved in design" (DockerContainers.tsx ligne 52 : `// Vigile orchestrates container actions via nodes REST API (as approved in design)`). **Zéro changement d'UX** — seule la marque `mutation=true` dans le registre change.

---

## 7. Bloc `external-auth-popup`

Le bloc `external-auth-popup` est le seul nouveau bloc générique introduit par la Partie 4 (faille 1). Il remplace le wizard-poll client par un flow serveur-owned.

### 7.1 Configuration

```json
{
  "type": "external-auth-popup",
  "title": "Connexion au compte Plex",
  "config": {
    "start_command": "plex.auth.start",
    "cancel_command": "plex.auth.cancel",
    "status_channel": "plex.auth.status",
    "popup_size": { "w": 600, "h": 700 }
  }
}
```

Le bloc ne connaît que 3 choses : quelle commande démarre le flow, quelle commande l'annule, quel canal SSE écouter. **Il ne fabrique aucune URL lui-même.**

### 7.2 Variantes d'état

| Variante | Description |
|----------|-------------|
| `idle` | Avant le clic sur "Connecter". |
| `waiting` | Flow démarré, popup ouverte, bouton "Annuler" actif. |
| `success` | Authentification réussie (config sauvegardée côté serveur). |
| `error` | Erreur serveur ou domaine rejeté. |
| `timeout` | 120 tentatives × 1 s épuisées. |
| `cancelled` | Annulation par l'utilisateur (bouton ou `window.closed`). |

### 7.3 Ouverture de la popup

L'URL provient de la réponse de `start_command`, **déjà vérifiée par le master** (voir §3 du garde-fou, Partie 4). La popup s'ouvre via `window.open(auth_url, 'Plex Auth', width=600, height=700)` — vérifié dans `PlexAdmin.tsx` ligne 183. La détection de fermeture se fait via `window.closed` (vérification locale légitime, pas d'appel réseau) → déclenche `cancel_command`.

### 7.4 Réutilisabilité

Le bloc est **réutilisable tel quel** : GitHub Actions, Nextcloud, tout device flow futur. Rien n'est plex-shaped. Le seul point de confiance nouvelle du modèle est la popup vers un domaine externe — vérifiée par le master (voir S7 + Partie 4 §3).

---

## 8. Résumé des mécanismes de sécurité (S1-S7)

Chaque mécanisme est décrit en un paragraphe, avec son comportement fail-closed.

### S1 — Namespace enforcement

Le check au moment de la décoration (`@route`) est advisory. **L'enforcement est le sweep de registre au load-time** (`plugin_engine._load_inprocess`). L'attribution est par module — le sweep gère les DEUX shapes d'enregistrement de metrics : `register(pm)` module-level ET `PluginBase` class-based. Le préfixe est `id + "."` (pas `id` seul, pour éviter les collisions `docker/docker2`). **Une seule défaillance → rejet du plugin entier.** Le `make_registrar` injection est différé (coût touche les 4 plugins ; 80% de la valeur / 20% du churn).

### S2 — Closed resolver

Le resolver est fermé : `FROZEN.get(key)` sur `MappingProxyType` après load. Une clé inconnue → **404 fail-closed**. Les handlers sont `(context, config) -> JSON`. **Le protocole doit supporter les réponses MEDIA/BINARY** — le proxy d'image Plex `/photo` est un proxy binaire ; un contrat JSON-only casse les posters des sessions. Le resolver est implémenté dans `master/core/block_resolver.py` (nouveau, J3a).

### S3 — Versioned meta-schema registry + migrator + legacy projection

Registry versionné `{1: V1 existant, 2: V2}` + **data migrator** pour les manifests existants. Pas d'extension in-place (la shape duale casse la validation uniforme). Le loader dérive la projection legacy `pages[]` depuis V2 pour alimenter `GET /api/plugins/pages` (API V1) + `PluginRouter` legacy pendant la strangler fig — **un seul registre canonique, zéro drift**. Implémenté dans `plugin_manifest.py` (lignes 217-374).

### S4 — Revision-based hot-reload

**Revision = paire `(boot_id, counter)`** — `boot_id` est un UUID régénéré au démarrage du master (faille 7). Le client stocke la paire ; un `boot_id` différent → **invalidation complète + reload intégral** (drop des caches), jamais de réconciliation partielle. **Build atomique puis swap** (manifest retiré **avant** la mise à jour de l'allowlist, dans le même swap) ; **serve-then-swap** (pas de flicker). SSE `{type:"plugins.invalidated", plugin_id, boot_id, revision, action}` = **nouveau canal** (modélisé sur `nodes_events.py` + `?token=` auth). SWR capture la revision au début de requête, jette le résultat si mismatch. Réconciliation `?since=<revision>` non-négociable (SSE at-most-once). Debounce des tempêtes watchdog. Mount gate + load barrier clé sur la revision. **Les flags gate le ROUTING uniquement, jamais l'état du registre.** Implémenté dans `plugin_engine` + `master/api/plugins_events.py` (nouveau, J3a/J4).

### S5 — Per-plugin rate limiting

Extension du `RateLimiter` existant (`rate_limiter.py`) — pas de réécriture. Clé composite `plugin:{plugin_id}:{user_id}` en tant que **dépendance FastAPI** (contexte d'auth), pas de middleware IP. **Deux budgets par plugin : READS vs MUTATIONS** (faille 8 — ordres de grandeur 60/min vs 10/min, calibration réelle en J3b). Budget depuis le manifeste, override admin en DB. `/batch` **débite chaque sous-requête contre le budget de son type** (pas d'amplification 7×, pas de compteur global de lot). Annulé = quota libéré immédiatement ; timeout = budget complet consommé.

### S6 — Incremental kill switch

**Deux modes** (faille 6) :
- `disable` = **maintenance** : refuse les nouvelles requêtes, laisse les opérations en vol se drainer (grâce bornée — le polling Plex 2s est le seul vrai client concerné), réactivable.
- `disable --hard` = **compromis** : tombstone immédiat, rejet instantané, aucun drain, réactivation explicite avec justification consignée en audit.

API : `POST /api/plugins/{id}/disable` body `{hard: bool}`. Entrée d'audit dans les deux cas. La tombstone est dans la **même gate de dispatch** que namespace + permission (pas de nouvelle architecture). Incrémental sur `unload_plugin()` existant (`plugin_manager.py` — la méthode existe déjà).

### S7 — Permissions catalog + ActionProposal

Catalogue fermé core-owned `{id, resource_contract, mutation flag, min_role}`. Intersection au dispatch : `role ≥ min_role ET p ∈ manifest.permissions ET resource_contract ET node_scope` (faille 4). Toute injection `needs:[node_id]` re-vérifie l'accès nœud via le même helper que `/api/nodes`. `/batch` re-vérifie par sous-requête (jamais au niveau du lot). Les blocs sans `needs` restent sur le modèle plat. Les mutations passent par `ActionProposal`. `/batch` exclut les mutations (rejette avec 403). Implémenté dans `master/core/permissions.py` (nouveau) + dispatch.

---

## 9. Vérifications et écarts

### 9.1 Vérité terrain vérifiée

| Élément | Source | Statut |
|---------|--------|--------|
| MetaSchemaV2 (64 KB, depth ≤5, extra="forbid") | `plugin_manifest.py` lignes 217-374 | Vérifié |
| Spinner `border-t-2 border-orange-500` | `DockerContainers.tsx:168`, `MetricsHistory.tsx:132` | Vérifié |
| "Aucun conteneur trouvé" | `DockerContainers.tsx:174` | Vérifié |
| "Aucun service trouvé" | `SystemdServices.tsx:166` | Vérifié |
| 3 hover tokens (zinc-800, green-custom/10, orange-500/10) | `DockerContainers.tsx:261,270,279` | Vérifié |
| Sidebar dual-path | `Sidebar.tsx:147,156,161` | Vérifié |
| `activePlugins` hardcodé | `Sidebar.tsx:29` | Vérifié |
| `useNodeStore` global selector | `MetricsHistory.tsx:28`, `nodeStore.ts:66` | Vérifié |
| `RestrictedPluginAPI` | `PluginAPI.ts:6-53` | Vérifié |
| `CommandEntry` fields | `command_registry.py:40-72` | Vérifié |
| `@route` decorator | `plugin_base.py:102-110` | Vérifié |
| Plex 15 routes en code | `plex/__init__.py` grep `@route` | Vérifié |
| Plex 8 routes dans manifeste | `plex/manifest.json` | Vérifié |
| Docker GET-only en code | `docker/__init__.py:97` | Vérifié |
| Docker POST 404 aujourd'hui | `DockerContainers.tsx:53` | Vérifié |

### 9.2 Écarts plan vs code

| Élément | Plan | Code | Statut |
|---------|------|------|--------|
| Plex `@route` en code | 11 (§2.1.4, §2.4) | 15 | **Discrépance** — le plan et `learnings.md` (J1-T4) sous-comptent. Le code réel et `test_command_registry.py` (ligne 92) confirment 15. |
| Plex routes manquantes du manifeste | 3 (`/photo`, `/history`, `/stats`) | 7 (ajout : `/{node_id}/transcodes`, `/{node_id}/files`, `/{node_id}/library/{section_id}/scan`, `/{node_id}/sessions/{session_key}`) | **Discrépance** — le plan sous-estime le drift. |
| Docker POST actions | "discovered from code" (§2.1.4) | Aucun POST en code — seulement GET `/containers` | **Discrépance** — le plan affirme que le scan découvre des POST docker, mais le code n'en a aucun. Le frontend POST `/containers/{id}/{action}` est un 404. |
| Total `@route` | 14 (learnings.md) | 18 | **Discrépance** — 1+1+15+1=18, pas 14. |

### 9.3 Notes de contexte

- **Plex** : 15 routes en code vs 8 dans le manifeste. Les 5 routes de mutation (4 POST + 1 DELETE) sont : `/auth/pin`, `/auth/verify`, `/config/server`, `/{node_id}/library/{section_id}/scan`, `/{node_id}/sessions/{session_key}`. La migration plex doit **ré-enregistrer les 3 routes manquantes** (`/photo`, `/{node_id}/history`, `/{node_id}/stats`) dans le manifeste V2, plus les 4 autres routes manquantes. La route `/auth/verify` est **supprimée comme route de transit** (vérification serveur-only, token jamais renvoyé au frontend).
- **Docker** : le manifeste est GET-only et le code est GET-only. Le frontend POST `/containers/{id}/{action}` est un 404 aujourd'hui. L'action de redémarrage de conteneur vit dans `master/api/services.py`, pas dans le plugin. Le registre de commandes code-derived ne doit jamais inventorier ce POST.
- **Token en clair** : `_save_plex_config` (`master/plugins/plex/__init__.py:111`) écrit `plex_token` en clair dans la DB. Aucun chiffrement au repos n'existe pour la config plugin aujourd'hui. Le master key (`security_manager.py:496-539`) est une paire Ed25519 de signature, pas une clé de chiffrement symétrique — une clé AES-256 doit être dérivée via HKDF-SHA256.
- **SSE par-session** : `master/api/nodes_events.py` est un broadcast EventBus (2 topics nœuds). Un canal session-scoped pour les statuts d'auth plugin est un travail nouveau (J3a).
