# Sprint 4 — Frontend Vigile

## Stack technique

```
FastAPI + Jinja2Templates (SSR)
HTMX (interactivité sans JS custom)
Tailwind CSS v4 (build npm + css-cli)
JetBrains Mono + Inter (Google Fonts)
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

## Direction visuelle — Terminal Brutalism

### Palette (monochrome stricte + un seul accent)

```
Background  #0a0a0a   (noir quasi-total, pas gris)
Surface     #111111   (cartes, panels)
Border      #1f1f1f   (séparateurs discrets)
Text        #e4e4e4   (primaire)
Text muted  #555555   (secondaire)
Accent      #00ff87   (vert terminal — UNIQUEMENT états actifs, CTAs, badges CONNECTED)
Danger      #ff4444   (FAILED, erreurs critiques)
Warning     #f5a623   (LOST, dégradés)
```

Pas de bleu. Pas de violet. Pas de gradient. Zéro.

### Typographie

| Usage | Font |
|---|---|
| Données (IP, metrics, logs, timestamps, statuts) | `JetBrains Mono` 13px |
| Prose (descriptions, chat, labels) | `Inter` 13px |

Pas d'icônes dans des cercles colorés. Icônes en `text-muted` 14px max, sans fond.

### Layout

- Sidebar fixe gauche 220px — logo + 4 liens max, pas de catégories
- Pas de header (logo dans la sidebar)
- Contenu `#main` : grille dense, `gap-2` à `gap-4` max
- Pas de padding excessif
- HTMX swap dans `#main` pour toute navigation
- Un seul squelette HTML (`base.html`) avec blocks Jinja2

---

## Pages & Routing (FastAPI + HTMX)

Toutes les routes sont servies par le master. Les templates Jinja2 sont rendus côté serveur.
HTMX injecte le contenu dans `#main` sans rechargement complet.

| Route | Méthode | Template | Description | Auth |
|---|---|---|---|---|
| `GET /login` | GET | `login.html` | Page de login | Public |
| `POST /login` | POST | — | Soumission login (redirect) | Public |
| `GET /` | GET | `dashboard.html` | Dashboard, liste nœuds | Auth |
| `GET /nodes/{id}` | GET | `node.html` | Détail nœud | Auth |
| `GET /nodes/{id}/services` | GET | `_services.html` | Liste services (HTMX swap) | Auth |
| `GET /nodes/{id}/logs` | GET | `_logs.html` | Logs panel (HTMX swap) | Auth |
| `GET /chat` | GET | `chat.html` | Page chat IA | Operator+ |
| `GET /chat/stream` | GET | — | SSE streaming (EventSource JS) | Operator+ |
| `GET /proposals` | GET | `proposals.html` | Propositions | Operator+ |
| `GET /audit` | GET | `audit.html` | Audit log | Admin |
| `GET /plugins` | GET | `plugins.html` | Catalogue plugins | Admin |
| `GET /settings` | GET | `settings.html` | Configuration | Admin |

Les templates préfixés par `_` sont des fragments HTML partiels (pas de `<html>`/`<body>`)
destinés à être injectés par HTMX dans le layout principal.

---

## Maquettes

### Barre latérale

```
┌──────────┬──────────────────────────────────────────────┐
│          │                                              │
│  Vigile  │         CONTENU PRINCIPAL                    │
│  (logo)  │                                              │
│          │                                              │
│  ■       │                                              │
│  Nodes   │                                              │
│          │                                              │
│  💬      │                                              │
│  Chat    │                                              │
│          │                                              │
│  □       │                                              │
│  Actions │                                              │
│          │                                              │
│  ...     │                                              │
│  Audit   │                                              │
│          │                                              │
└──────────┴──────────────────────────────────────────────┘
```

Sidebar 220px, fond `#0a0a0a`. Liens sans fond au hover — uniquement `text-muted` → `text`. Aucune catégorie.

---

### Login

```
╔══════════════════════════════════════════════╗
║                                              ║
║                    Vigile                     ║
║            Server fleet guardian              ║
║                                              ║
║  ┌────────────────────────────────────────┐  ║
║  │  Username                              │  ║
║  │  ┌──────────────────────────────────┐  │  ║
║  │  │                                  │  │  ║
║  │  └──────────────────────────────────┘  │  ║
║  │                                        │  ║
║  │  Password                              │  ║
║  │  ┌──────────────────────────────────┐  │  ║
║  │  │                                  │  │  ║
║  │  └──────────────────────────────────┘  │  ║
║  │                                        │  ║
║  │  ┌──────────────────────────────────┐  │  ║
║  │  │         Sign in                  │  │  ║
║  │  └──────────────────────────────────┘  │  ║
║  └────────────────────────────────────────┘  ║
║                                              ║
╚══════════════════════════════════════════════╝
```

- Bouton Sign in : bordure `#1f1f1f`, text `#e4e4e4`, pas de fond coloré
- L'input focus a une bordure `#00ff87` (seul endroit où le vert apparaît sur cette page)

---

### Dashboard

```
┌──────────┬─────────────────────────────────────────────────────┐
│          │                                                     │
│  Vigile  │  Nodes                       (3)                    │
│          │                                                     │
│  ■  Nodes│  ┌──────────────────────────────────────────────┐   │
│  💬  Chat│  │  sim-prod  ● CONNECTED     Debian 12  x86_64 │   │
│  □  Actns│  │  CPU 72%  ████████░░  RAM 32%  ████░░░░      │   │
│  ...     │  │  DISK 47%  ████████░░  2 failed services     │   │
│  Audit   │  ├──────────────────────────────────────────────┤   │
│          │  │  web-01  ○ LOST     Ubuntu 24.04             │   │
│          │  │  Last contact: 3h ago                        │   │
│          │  └──────────────────────────────────────────────┘   │
│          │                                                     │
│          │  ┌────────────────────────────────────────────┐     │
│          │  │ 💬 Ask AI...                  ▶            │     │
│          │  └────────────────────────────────────────────┘     │
│          │                                                     │
└──────────┴─────────────────────────────────────────────────────┘
```

- Stats cards : pas de cards. Juste le nombre en haut (`Nodes (3)`)
- Node list : cartes denses, bordure `#1f1f1f`, padding `p-3`
- Badge CONNECTED : border `#00ff87`, text `#00ff87`, pas de fond
- Badge LOST : border `#f5a623`, text `#f5a623`
- Mini chat input en bas : barre de recherche simple, pas de card

---

### Node Detail

```
┌──────────┬─────────────────────────────────────────────────────┐
│          │  ← Nodes  /  sim-prod                               │
│          │                                                     │
│          │  ● CONNECTED  sim-prod                              │
│          │  Debian 12  x86_64                                  │
│          │                                                     │
│          │  CPU  72%   RAM  32%   DISK  47%   Uptime  12h     │
│          │  ──────────────────────────────────────────────     │
│          │  [ Stats ]  [ Services ]  [ Containers ]  [ Logs ]  │
│          │                                                     │
│          │  ┌──────────────────────────────────────────────┐   │
│          │  │ ● ssh.service     active  running            │   │
│          │  │ ● nginx.service   active  running            │   │
│          │  │ ● docker.service  active  running            │   │
│          │  │ ● mysql.service   failed  failed    [Restart] │   │
│          │  │ ○ apache2.service inactive dead              │   │
│          │  │ ● prometheus.svc  failed  failed    [Restart] │   │
│          │  └──────────────────────────────────────────────┘   │
│          │                                                     │
└──────────┴─────────────────────────────────────────────────────┘
```

- Metrics en ligne (pas de gauges, pas de graphiques pour le prototype)
- Tabs underline style — pas de fond sur le tab actif, juste bordure bottom `#00ff87`
- Services list : chaque ligne compacte, texte `JetBrains Mono`

#### Logs tab

```
┌──────────┬─────────────────────────────────────────────────────┐
│          │  [ Stats ]  [ Services ]  [ Containers ]  [ Logs ]  │
│          │                                                     │
│          │  Service: [ssh.service ▼]  Lines: [50 ▼]           │
│          │                                                     │
│          │  ┌──────────────────────────────────────────────┐   │
│          │  │ May 15 06:12:01 sshd[1123]: Failed password  │   │
│          │  │ May 15 06:12:05 sshd[1124]: Failed password  │   │
│          │  │ May 15 09:00:00 sshd[1250]: Accepted pubkey │   │
│          │  │ May 15 09:45:10 sshd[1280]: Invalid user    │   │
│          │  │                                          │   │   │
│          │  └──────────────────────────────────────────────┘   │
│          │                                                     │
└──────────┴─────────────────────────────────────────────────────┘
```

- LogViewer = `ScrollArea` avec fond `#0a0a0a`, texte `JetBrains Mono` 12px
- Auto-scroll vers le bas, bouton "pause" si l'utilisateur remonte
- Bordure fine `#1f1f1f`, pas d'ombre

---

### Chat IA

```
┌──────────┬─────────────────────────────────────────────────────┐
│          │  💬 Assistant                       [New chat]      │
│          │                                                     │
│          │  ┌──────────────────────────────────────────────┐   │
│          │  │  Moi                            10:32        │   │
│          │  │  │ Le serveur nginx semble lent             │   │
│          │  ├──────────────────────────────────────────────┤   │
│          │  │  Vigile                         10:33        │   │
│          │  │  │  Je vais vérifier nginx...               │   │
│          │  │  │  STATUT : nginx.service active (running) │   │
│          │  │  │                                           │   │
│          │  │  │  ┌────────────────────────────────────┐  │   │
│          │  │  │  │ 💡 RESTART_SERVICE  risk: LOW     │  │   │
│          │  │  │  │ Redémarrer nginx pour recharger   │  │   │
│          │  │  │  │ la configuration                  │  │   │
│          │  │  │  │ [Approve]       [Reject]          │  │   │
│          │  │  │  └────────────────────────────────────┘  │   │
│          │  ├──────────────────────────────────────────────┤   │
│          │  │  Moi                            10:35        │   │
│          │  │  │ Oui redémarre                            │   │
│          │  ├──────────────────────────────────────────────┤   │
│          │  │  Vigile                         10:36        │   │
│          │  │  │ ✅ nginx.service restarted               │   │
│          │  │  │ Result: Service nginx restarted          │   │
│          │  └──────────────────────────────────────────────┘   │
│          │                                                     │
│          │  ┌──────────────────────────────────────────────┐   │
│          │  │ Ask...                                     ▶ │   │
│          │  └──────────────────────────────────────────────┘   │
│          │                                                     │
└──────────┴─────────────────────────────────────────────────────┘
```

- Messages IA distingués par `border-left: 1px solid #1f1f1f` — pas de bulle colorée
- Messages utilisateur sans bordure
- Proposal card : bordure `#1f1f1f`, pas de fond. Bouton Approve = seul élément `#00ff87` de toute l'interface
- Loading state : spinner discret `JetBrains Mono` + points, pas de skeleton
- Streaming SSE : curseur clignotant pendant la génération

---

### Proposals

```
┌──────────┬─────────────────────────────────────────────────────┐
│          │  Actions                         [Pending] [All]    │
│          │                                                     │
│          │  ● mysql.service  ──  RESTART_SERVICE               │
│          │  MySQL a crashé (OOM). Redémarrage nécessaire.      │
│          │  10:32  ·  sim-prod          [Approve]  [Reject]   │
│          │                                                     │
│          │  ○ LIST_SERVICES                                    │
│          │  Diagnostic de routine.                             │
│          │  10:30  ·  sim-prod          [Approve]  [Reject]   │
│          │                                                     │
│          │  ✓ nginx.service  ──  RESTART_SERVICE               │
│          │  Redémarré avec succès.   09:15  ·  web-01          │
│          │                                                     │
│          │  ✗ READ_LOGS                                        │
│          │  Pas nécessaire.   08:45  ·  sim-prod               │
│          └─────────────────────────────────────────────────────┘
```

- Pas de cartes — chaque proposition est une ligne dense
- Filtre Pending/All en haut (Select ou tabs simples)
- Risque pas affiché (c'est dans la carte détaillée du chat)
- Action rapide Approve/Reject inline

---

### Audit Log

```
┌──────────┬─────────────────────────────────────────────────────┐
│          │  Audit Trail                     🔍 Filter         │
│          │                                                     │
│          │  #42  10:32  PROPOSAL_APPROVED  flavio  sim-prod   │
│          │       → RESTART_SERVICE nginx.service              │
│          │  #41  10:30  PROPOSAL_CREATED   ai      sim-prod   │
│          │       → RESTART_SERVICE (LOW)                      │
│          │  #40  10:30  INTENT_RESULT      system  sim-prod   │
│          │       → LIST_SERVICES (45 services)                │
│          │                                                     │
│          │  ✅ SHA256 chain intact — 42 entries                │
│          └─────────────────────────────────────────────────────┘
```

- Liste chronologique inversée
- Badge de vérification d'intégrité en bas
- Police `JetBrains Mono` pour les IDs et timestamps

---

### Plugin Catalogue

```
┌──────────┬─────────────────────────────────────────────────────┐
│          │  Plugins                         🔍 Search         │
│          │                                                     │
│          │  ┌────────────────────┐ ┌────────────────────┐     │
│          │  │ 📊 Metrics         │ │ 🐳 Docker           │     │
│          │  │ CPU/RAM/DISK       │ │ Container mgmt     │     │
│          │  │ ● Active           │ │ ● Active           │     │
│          │  └────────────────────┘ └────────────────────┘     │
│          │                                                     │
│          │  ┌────────────────────┐ ┌────────────────────┐     │
│          │  │ ⚙️ Systemd         │ │ ☁️ Backup           │     │
│          │  │ Service management │ │ Auto backup         │     │
│          │  │ ● Active           │ │ ○ Install           │     │
│          │  └────────────────────┘ └────────────────────┘     │
│          └─────────────────────────────────────────────────────┘
```

- Grille simple de cards sans fioritures
- Statut : `● Active` (text `#00ff87`) ou `○ Install` (text muted)

---

## 6. Philosophie de design — Pourquoi ces choix

Cette section explique le raisonnement derrière la direction visuelle.
Elle est ici pour que tu puisses prendre des décisions cohérentes
quand tu rencontres un cas non couvert par les specs.

### Le problème du "AI aesthetic"

La majorité des interfaces générées par IA aujourd'hui partagent les mêmes
marqueurs visuels : gradients violet-bleu, orbes lumineux en arrière-plan,
cartes avec `shadow-lg` coloré, icônes dans des ronds colorés, grille de
3 features symétrique, boutons en gradient. Ces patterns sont devenus un
signal immédiat de "template SaaS généré". Quand un utilisateur voit cette
esthétique, il ne ressent pas l'outil — il ressent le template.

L'objectif ici est l'inverse : une interface qui ressemble à quelque chose
qu'un ingénieur avec du goût aurait construit pour lui-même.

### Le principe de la contrainte comme identité

Un bon design n'est pas celui qui a le plus d'options visuelles — c'est
celui qui a fait des choix irréversibles assumés.

- **Une seule couleur d'accent** (vert terminal `#00ff87`), jamais utilisée
  de façon décorative — uniquement pour signaler "actif" ou "action principale"
- **Typographie monospace** pour toutes les données machine — parce que
  c'est sémantiquement juste, pas pour faire "hacker"
- **Noir quasi-total** plutôt que gris slate — parce que le gris slate
  c'est le défaut shadcn, et le défaut n'a pas d'identité

Ces contraintes créent une cohérence immédiate : chaque fois que tu vois
du vert, tu sais que c'est important. Chaque fois que tu vois de la
monospace, tu sais que c'est une donnée machine.

### La règle du fond neutre + moment d'accent

L'œil humain est attiré par le contraste. Si tout est coloré, rien n'est
important. Si la quasi-totalité de l'interface est monochrome et dense,
alors un seul élément vert suffit à diriger l'attention vers l'action
critique. C'est la raison pour laquelle le bouton **Approve** est le seul
élément vraiment vert de toute l'interface — quand tu arrives sur la
Dialog de validation, tu n'as aucun doute sur quoi cliquer.

### Densité comme respect de l'utilisateur

Une interface ops n'est pas une landing page. L'utilisateur n'a pas besoin
d'être guidé avec des illustrations et du padding généreux — il sait
pourquoi il est là. La densité signale : cet outil te fait confiance.

De l'espacement excessif sur un dashboard signale l'inverse : on a peur
que tu sois perdu. Espacement serré, typo petite, information maximale
par viewport — c'est un choix de respect, pas une économie de travail.

### Ce qu'il faut éviter à tout prix

Si à un moment tu te demandes "est-ce que ça fait trop générique ?",
applique ce test : est-ce que ce pattern pourrait se retrouver sur
n'importe quel starter template shadcn/ui sur GitHub ? Si oui, c'est
à supprimer ou à tordre.

Les patterns les plus dangereux :
- Icône dans un rond coloré pour illustrer une feature
- Section centrée avec titre + sous-titre + 3 cards symétriques
- Top bar avec avatar, cloche de notification, et barre de recherche
- Sidebar avec accordéon de catégories
- Toast pour signaler un succès important (le feedback doit être inline,
  dans le contexte de l'action)

### La référence mentale à garder

Imagine que **htop** et **Linear.app** ont eu un enfant. La densité de l'un,
le soin typographique de l'autre. Tout ce qui ne serait pas dans l'un ou
l'autre de ces deux outils est probablement superflu.

---

## Comportements critiques (prototype)

- **Badge statut nœud** : polling. Se met à jour sans reload
- **Approve button** : désactivé pendant exécution, loading discret (JetBrains Mono + spinner), résultat inline — pas de toast
- **Logs panel** : auto-scroll bas. Bouton "pause" si remonte
- **Chat** : messages IA distingués par `border-left` seulement (pas de bulle). Streaming visible avec curseur clignotant

---

## API + Routes frontend

L'API REST existante (`/api/*`) reste inchangée. Les pages frontend sont servies
par de nouvelles routes Jinja2 dans un routeur dédié `master/api/frontend.py`.

### Routes frontend (nouvelles)

| Route | Méthode | Template | Rôle |
|---|---|---|---|
| `GET /login` | GET | `login.html` | Page login |
| `POST /login` | POST | — | Submit login → redirect / |
| `GET /` | GET | `dashboard.html` | Dashboard |
| `GET /nodes/{id}` | GET | `node.html` | Détail nœud |
| `GET /nodes/{id}/services` | GET | `_services.html` | Fragment services |
| `GET /nodes/{id}/containers` | GET | `_containers.html` | Fragment containers |
| `GET /nodes/{id}/logs` | GET | `_logs.html` | Fragment logs |
| `GET /nodes/{id}/metrics` | GET | `_metrics.html` | Fragment stats (poll) |
| `GET /chat` | GET | `chat.html` | Page chat |
| `GET /chat/stream` | GET | SSE | Streaming chat (EventSource) |
| `GET /proposals` | GET | `proposals.html` | Propositions |
| `GET /audit` | GET | `audit.html` | Audit |
| `GET /plugins` | GET | `plugins.html` | Plugins |
| `GET /settings` | GET | `settings.html` | Settings |

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
    ├── base.html            # Squelette (sidebar + #main)
    ├── login.html
    ├── dashboard.html
    ├── node.html            # Détail nœud (tabs)
    ├── _services.html       # Fragment liste services (HTMX)
    ├── _containers.html     # Fragment liste containers (HTMX)
    ├── _logs.html           # Fragment logs (HTMX)
    ├── _metrics.html        # Fragment stats bar (HTMX poll)
    ├── chat.html
    ├── _chat_messages.html  # Fragment messages chat (SSE)
    ├── proposals.html
    ├── audit.html
    ├── plugins.html
    └── settings.html

static/             # ← NOUVEAU : fichiers statiques
├── css/
│   └── app.css     # Tailwind build
├── js/
│   └── chat.js     # EventSource SSE (seul JS custom)
└── fonts/          # JetBrains Mono + Inter (woff2)
```

**Principe HTMX** : les vues sont des templates Jinja2. Les fragments `_*.html` sont
rendus sans layout, injectés dans `#main` par HTMX. Pas de build React, pas de bundle.

---

## Ordre d'implémentation

| Étape | Composant | Dépend de |
|---|---|---|
| 1 | Setup Tailwind + static files + base template | Rien |
| 2 | Sidebar + layout `base.html` | Rien |
| 3 | Login page + auth + session cookie | Layout |
| 4 | Dashboard template + node list + polling HTMX | Layout, auth |
| 5 | Node detail template + tabs (services, containers, metrics) | Dashboard |
| 6 | LogViewer template + lazy load HTMX | NodeDetail |
| 7 | Chat page + SSE EventSource (+ chat.js) | Layout, auth |
| 8 | Proposals page + approve/reject HTMX | Chat |
| 9 | Audit page | Layout, auth |
| 10 | Plugins + Settings pages | Layout, auth |
| 11 | Routeur frontend `master/api/frontend.py` + intégration main.py | Tout |

## Estimation

| Phase | Sessions |
|---|---|
| Setup Tailwind + base template | 1 |
| Login + Dashboard + Node Detail | 1 |
| Logs + Chat + Proposals | 1-2 |
| Audit + Plugins + Settings + routage | 1 |
| **Total** | **4-5** |
