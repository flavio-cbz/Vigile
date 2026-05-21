# Sprint 4 — Frontend Vigile

## Stack technique

```
FastAPI + Jinja2Templates (SSR)
HTMX (interactivité sans JS custom)
Tailwind CSS v4 (CDN @tailwindcss/browser — pas de build npm)
Inter (Google Fonts)
Tabler Icons (SVG inline, text-muted, 14px max)
EventSource JS (SSE streaming chat — le seul JS custom)
```

## Architecture de déploiement

```
Navigateur ── HTTPS ── Nginx Proxy Manager ──→ master:8002
```

Tout est servi par le master FastAPI lui-même :

- Les templates Jinja2 sont rendus par FastAPI
- HTMX gère les mises à jour dynamiques (polling, navigation, formulaires)
- SSE pour le streaming chat (EventSource JS)
- Pas de build séparé, pas de CORS, pas de port supplémentaire

---

### Principe HTMX

- **Navigation** : liens `<a hx-get="/nodes/..." hx-target="#main" hx-push-url="true">`
- **Polling statuts** : `<div hx-get="/api/nodes/..." hx-trigger="every 10s" hx-swap="outerHTML">`
- **Formulaires** : `<form hx-post="/api/..." hx-target="#result" hx-swap="innerHTML">`
- **Chat SSE** : `<div hx-sse="connect:/api/chat?stream=true" hx-trigger="sse:token">`
- **Pagination logs** : `hx-get="/api/nodes/{id}/logs?offset=..." hx-trigger="revealed"`
- **Aucun JS custom** sauf un EventSource pour le streaming chat (pas gérable en HTMX pur)

---

## Direction visuelle — Glass Dark Ops (basé sur la maquette)

La maquette de référence est `mockup_directions.html` à la racine du projet.
Toute décision visuelle non couverte ici doit s'inspirer des patterns de cette maquette.

### Palette

```
Background  #050505   (noir profond)
Surface     #0a0a0c   (panels, sidebar)
Surface-2   #111114   (cartes secondaires, inputs)
Border      white/5 à white/10  (via Tailwind opacity)
Text        white      (primaire)
Text muted  neutral-400 / #a3a3a3
Accent      teal-400 / #14b8a6  (UNIQUE accent — badges, CTAs, états actifs)
Danger      red-400 / #f87171   (FAILED, erreurs)
Warning     amber-500 / #f59e0b  (LOST, dégradés)
Info        blue-600 / #1d4ed8  (auto-discovery, info)
```

Teal = seul vrai accent. Le bleu est toléré pour les sections "info/découverte" (héro).
Gradients autorisés : `bg-gradient-to-br`, `bg-gradient-to-r`, overlays.

### Glassmorphism

Toutes les cartes, panels, inputs utilisent le pattern :
```css
bg-white/[0.02] border border-white/[0.05] backdrop-blur-xl
```
Ou selon l'importance :
- **Surface active** (cartes cliquables) : `bg-[#111114] border border-white/5 hover:border-teal-500/40`
- **Surface passive** (statiques) : `glass-panel` = `bg-white/[0.02] border border-white/[0.05] backdrop-blur-xl`
- **Inputs/barres** : `bg-white/5 border border-white/10`

### Typographie

| Usage | Font |
|---|---|
| Tout le texte | `Inter` (Google Fonts) via Tailwind `font-sans` |

Pas de JetBrains Mono. Inter uniquement, en `text-[13px]` à `text-[15px]` selon le contexte.

### Icônes

- **Tabler Icons** : SVG inline, `text-neutral-500`, 14px max pour les icônes de texte
- **Cercles colorés** : Autorisés dans les cards de stats (cf. maquette) : `w-10 h-10 rounded-xl bg-{color}-500/10 flex items-center justify-center border border-{color}-500/20`
- **Émojis** : Autorisés dans la nav (🐳, ▶️, ⚙️) comme dans la maquette

### Glows & Ombres

- **Glow sur accent** : `shadow-[0_0_15px_rgba(45,212,191,0.2)]` pour teal
- **Glow sur statut** : `shadow-[0_0_8px_rgba(16,185,129,0.8)]` pour les points verts
- **Glow bleu** : `shadow-[0_0_20px_rgba(37,99,235,0.4)]` pour les CTAs info
- **Ombre panel** : `shadow-2xl`, `shadow-[0_4px_20px_rgba(0,0,0,0.5)]`
- **Ombre sidebar** : `shadow-[10px_0_30px_rgba(0,0,0,0.5)]`

### Layout

```
┌──────────┬───────────────────────────────┬──────────────┐
│ Sidebar  │         #main                  │  Copilot     │
│ 80-240px │  (contenu principal)           │  340-400px   │
│          │                               │  (sidebar    │
│          │                               │   droite)    │
│          │                               │              │
│──────────│  scrollable, overflow-y-auto   │──────────────│
│ expand   │                               │  chat +      │
│ on hover │                               │  proposals   │
└──────────┴───────────────────────────────┴──────────────┘
```

- **Sidebar gauche** : 80px fixe, s'expand à 240px au hover (transition 300ms). Overlay `z-50`.
- **Header** : Présent dans `#main` — titre de page + sélecteur de nœud (optionnel).
- **Contenu `#main`** : Carrousels horizontaux (Netflix-style) avec `overflow-x-auto netflix-row snap-x`.
- **Copilot droite** : Sidebar droite permanente 340-400px, glassmorphic, avec `backdrop-blur-3xl`.
- **HTMX swap** : Dans `#main-content` (sous le header) pour les changements de page/onglet.
- **Un seul squelette HTML** (`base.html`) avec blocks Jinja2.

---

## Pages & Routing (FastAPI + HTMX)

Toutes les routes sont servies par le master. Les templates Jinja2 sont rendus côté serveur.
HTMX injecte le contenu dans `#main` sans rechargement complet.

| Route | Méthode | Template | Description | Auth |
|---|---|---|---|---|---|
| `GET /login` | GET | `login.html` | Page de login | Public |
| `POST /login` | POST | — | Soumission login (redirect) | Public |
| `POST /logout` | POST | — | Déconnexion (redirect → /login) | Auth |
| `GET /` | GET | `dashboard.html` | Dashboard avec carrousels | Auth |
| `GET /nodes/{id}` | GET | `node.html` | Détail nœud (tabs) | Auth |
| `GET /nodes/{id}/services` | GET | `_services.html` | Fragment services (HTMX) | Auth |
| `GET /nodes/{id}/containers` | GET | `_containers.html` | Fragment containers (HTMX) | Auth |
| `GET /nodes/{id}/logs` | GET | `_logs.html` | Fragment logs (HTMX) | Auth |
| `GET /nodes/{id}/metrics` | GET | `_metrics.html` | Fragment stats (HTMX poll 15s) | Auth |
| `GET /chat/stream` | GET | — | SSE streaming (EventSource JS) | Operator+ |
| `GET /proposals` | GET | `proposals.html` | Propositions d'actions | Operator+ |
| `GET /audit` | GET | `audit.html` | Audit trail | Admin |
| `GET /plugins` | GET | `plugins.html` | Catalogue plugins | Admin |

Les templates préfixés par `_` sont des fragments HTML partiels (pas de `<html>`/`<body>`)
destinés à être injectés par HTMX dans le layout principal.

---

## Référence visuelle — Maquette unique

L'**unique référence graphique** est `mockup_directions.html` à la racine du projet.
Tous les templates doivent reproduire le design, les proportions et l'ambiance de cette maquette.

### Principes généraux (extrapolés de la maquette)

- **Dark glassmorphism** : fond `#050505`, surfaces en `backdrop-blur`, bordures discrètes `white/5`
- **Teal accent** : tout ce qui est "actif", "connecté", "action principale" → teal-400
- **Densité élégante** : les infos sont là, au premier coup d'œil — pas besoin d'apprendre l'interface
- **Carrousels horizontaux** : pattern Netflix pour les sections du dashboard (vitals, docker, etc.)
- **Header + sidebar gauche + copilot droite** : layout en 3 colonnes
- **Gradients et glows** : assumés, pas excessifs — un glow teal pour attirer l'attention

### Pages

#### Login (non couvert par la maquette)

Page centrée, fond `#050505`. Card glassmorphic centrée avec logo Vigile (V dans cercle teal), formulaire username/password, bouton Sign in avec fond teal-400/hover teal-500. La même ambiance sombre et propre que le reste.

#### Dashboard (couvert par la maquette — sections #main)

Voir le code HTML de `mockup_directions.html` pour les détails exacts. Structure :

1. **Héro Découverte** (en haut) : bannière avec suggestion de plugin (ex: Nextcloud). Gradient bleu, bouton "Intégrer le Plugin" bleu avec glow.
2. **Ligne "Signes Vitaux"** : carrousel horizontal de cards stats (CPU, RAM, DISK, etc.) avec icônes dans cercles colorés, valeurs en badge, barre de progression colorée avec glow.
3. **Ligne Docker** : carrousel de cartes containers. Header gradient, statut "Up X days" avec point vert, infos image/ports, boutons Logs + Redémarrer. Dernière carte = "Déployer un conteneur" en dashed border.
4. **Ligne Plex (exemple plugin)** : carrousel de cartes média avec cover image, barre de progression.

#### Node Detail (non couvert par la maquette — extrapoler le style)

Breadcrumb ← Nodes / nom-du-noeud. Badge statut (CONNECTED teal, LOST amber). Infos hostname/OS/arch.
Barre de métriques inline (CPU, RAM, DISK, Uptime) avec barres de progression colorées.
Tabs underline : Stats | Services | Containers | Logs — chaque tab charge un fragment HTMX.
Le style des cards suit le glassmorphism de la maquette (bordures white/5, rounded-2xl, etc.).

#### Chat — Copilot Sidebar (couvert par la maquette — sidebar droite)

Le copilot est une **sidebar droite permanente** sur toutes les pages, pas une page séparée.
Voir `mockup_directions.html` → élément `<aside>` :

- Header "Vigile Copilot" avec point vert "Connecté au système"
- Messages IA : bulle glassmorphic `bg-white/5 border border-white/10 rounded-2xl rounded-tl-sm`
- Messages user : bulle `bg-teal-500/10 border border-teal-500/20` alignée à droite
- Propositions d'actions : carte avec bordure bleue/teal, bouton "Lancer" coloré
- Input : `bg-[#111114] rounded-2xl border border-white/10`, avec suggestions rapides
- Gradient subtil en fond : `bg-gradient-to-b from-teal-500/10 to-transparent`

#### Proposals (page dédiée, non couverte par la maquette)

Liste de propositions avec le même style glassmorphic. Filtres Pending/All/History.
Chaque ligne = petite card avec action, raison, statut, boutons Approve (teal) / Reject (muted).
Les propositions approuvées/refusées en opacité réduite avec icône ✓ ou ✗.

#### Audit Trail (page dédiée, non couverte par la maquette)

Timeline verticale inversée. Chaque entrée = petite card glassmorphic avec :
`#42 10:32 PROPOSAL_APPROVED flavio sim-prod → action détail`
Badge de vérification SHA256 en bas de page (vert si intact, rouge si corrompu).
Filtre par type d'action et date.

#### Plugins (page dédiée + entrée sidebar)

Grid de cards plugins. Chaque card = icône + nom + description + statut (● Active en teal, ○ Install en muted).
Style glassmorphic comme les cards Docker de la maquette.

---

## Design Philosophy

### Principe : compréhension immédiate

L'utilisateur doit comprendre l'état de son serveur **en un coup d'œil**,
sans avoir à apprendre une interface. La maquette illustre ce principe :
aucune info détaillée apparente, mais tout est là et parlant.

- Les carrousels rendent l'information explorable naturellement
- Les couleurs (teal = OK, red = attention, amber = warning) sont intuitives
- Les barres de progression avec glow donnent une lecture immédiate des métriques
- Les badges de statut (points verts/rouges) sont universels

### Guidelines pour les écrans non couverts

Quand tu construis une page qui n'est pas dans la maquette :

1. **Reproduis le système visuel** : glassmorphism, teal accent, dark theme
2. **Pense "coup d'œil"** : la valeur principale doit être visible sans scroller
3. **Évite l'abstraction** : pas de jargon technique non nécessaire
4. **Utilise les patterns de la maquette** : les cards vitals, les containers cards, le copilot
5. **Densité mais pas sacrifice** : les infos sont denses mais aérées par le glassmorphism

---

## Comportements critiques (prototype)

- **Badge statut nœud** : polling HTMX `every 15s`. Se met à jour sans reload.
- **Carrousels stats** : polling HTMX `every 15s` pour les métriques (metrics fragment).
- **Approve button** : désactivé pendant exécution. Résultat inline (pas de toast).
- **Logs panel** : chargement manuel via click. Pas de polling automatique.
- **Copilot sidebar** : présente sur toutes les pages. Contexte adaptatif (la page courante influence les prompts/suggestions).
- **Chat streaming** : EventSource JS. Curseur clignotant pendant génération. Messages IA en bulle glassmorphic.
- **Navigation** : HTMX swaps dans `#main-content`. La sidebar et le copilot ne sont pas re-rendus.

---

## API + Routes frontend

L'API REST existante (`/api/*`) reste inchangée. Les pages frontend sont servies
par de nouvelles routes Jinja2 dans un routeur dédié `master/api/frontend.py`.

### Routes frontend (nouvelles)

Voir tableau plus haut dans § Pages & Routing.

### API REST (existante, utilisée par templates)

| Endpoint | Usage |
|---|---|
| `POST /api/auth/login` | Login (form action) |
| `GET /api/nodes` | Liste nœuds |
| `GET /api/nodes/{id}` | Détail nœud |
| `GET /api/nodes/{id}/stats` | Métriques |
| `GET /api/nodes/{id}/services` | Services |
| `GET /api/nodes/{id}/containers` | Containers |
| `GET /api/nodes/{id}/logs` | Logs |
| `POST /api/chat` | Chat SSE |
| `GET /api/chat/proposals` | Propositions |
| `POST /api/chat/proposals/{id}/approve` | Approuver |
| `POST /api/chat/proposals/{id}/reject` | Rejeter |
| `GET /api/admin/audit-verify` | Vérifier audit |

---

## Structure fichiers

```
master/
├── main.py
├── config.py
├── core/            # (inchangé)
├── api/             # (inchangé)
├── ws/              # (inchangé)
├── db/              # (inchangé)
├── plugins/         # (inchangé)
└── templates/       # ← NOUVEAU : templates Jinja2
    ├── base.html            # Squelette (sidebar + #main + copilot)
    ├── login.html
    ├── dashboard.html
    ├── node.html            # Détail nœud (tabs)
    ├── _services.html       # Fragment liste services (HTMX)
    ├── _containers.html     # Fragment liste containers (HTMX)
    ├── _logs.html           # Fragment logs (HTMX)
    ├── _metrics.html        # Fragment stats bar (HTMX poll)
    ├── proposals.html
    ├── audit.html
    └── plugins.html

static/             # ← NOUVEAU : fichiers statiques
├── css/
│   └── app.css     # Tailwind custom styles (si besoin, sinon CDN)
├── js/
│   └── chat.js     # EventSource SSE (seul JS custom)
```

**Principe HTMX** : les vues sont des templates Jinja2. Les fragments `_*.html` sont
rendus sans layout, injectés dans `#main` par HTMX. Pas de build React, pas de bundle.

---

## Ordre d'implémentation

| Étape | Composant | Dépend de |
|---|---|---|
| 1 | Setup static dirs + base template + CDN links | Rien |
| 2 | Sidebar + Header + Copilot layout `base.html` | Rien |
| 3 | Login page + auth session cookie + frontend router | Layout |
| 4 | Dashboard template (carrousels, hero, polling HTMX) | Layout, auth |
| 5 | Node detail template + tabs (services, containers, logs) | Dashboard |
| 6 | LogViewer + metrics fragments HTMX | NodeDetail |
| 7 | Chat SSE streaming (EventSource + endpoint) | Layout, auth |
| 8 | Proposals page + approve/reject HTMX | Layout, auth |
| 9 | Audit page | Layout, auth |
| 10 | Plugins page | Layout, auth |

## Estimation

| Phase | Sessions |
|---|---|
| base.html layout + sidebar + copilot | 1 |
| Login + Dashboard | 1 |
| Node Detail + Logs + Metrics | 1 |
| Chat SSE + Proposals | 1 |
| Audit + Plugins | 1 |
| **Total** | **~5** |
