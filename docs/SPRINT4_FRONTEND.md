# Sprint 4 — Frontend Vigile

## Stack technique

```
Vite + React 19 + TypeScript
Tailwind CSS v4
shadcn/ui (primitives Radix uniquement — pas le design par défaut)
JetBrains Mono + Inter (fonts)
Tabler Icons (icônes en text-muted, 14px max, sans fond)
React Router v7
EventSource (SSE natif, zero lib)
```

## Architecture de déploiement

```
Navigateur ── HTTPS ── Nginx Proxy Manager ──┬── /api/* ──→ master:8002
                                              └── /*    ──→ fichiers statiques React
```

Frontend servi par Nginx en statique. Appels `/api/*` proxifiés vers master.
Pas de CORS, pas de port supplémentaire.

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
- Contenu : grille dense, `gap-2` à `gap-4` max
- Pas de padding excessif

---

## Pages & Routing

| Route | Page | Accès |
|---|---|---|
| `/login` | Login | Public |
| `/` | Dashboard (nodes, santé globale) | Auth |
| `/nodes/:id` | Node detail (stats, services, containers, logs) | Auth |
| `/chat` | Chat IA | Operator+ |
| `/proposals` | Propositions d'actions | Operator+ |
| `/audit` | Audit log | Admin |
| `/plugins` | Catalogue de plugins | Admin |
| `/settings` | Configuration (LLM, users) | Admin |

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

## Comportements critiques (prototype)

- **Badge statut nœud** : polling. Se met à jour sans reload
- **Approve button** : désactivé pendant exécution, loading discret (JetBrains Mono + spinner), résultat inline — pas de toast
- **Logs panel** : auto-scroll bas. Bouton "pause" si remonte
- **Chat** : messages IA distingués par `border-left` seulement (pas de bulle). Streaming visible avec curseur clignotant

---

## API utilisée

| Endpoint | Usage |
|---|---|
| `POST /api/auth/login` | Login |
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
frontend/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.ts
├── index.html
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── index.css           # Pal个人化 theme (tailwind config + fonts)
    ├── lib/
    │   ├── api.ts          # Client HTTP (fetch wrapper)
    │   ├── auth.ts         # Gestion token JWT
    │   └── sse.ts          # EventSource SSE
    ├── hooks/
    │   ├── useAuth.ts
    │   ├── useNodes.ts
    │   ├── useChat.ts
    │   └── useProposals.ts
    ├── components/
    │   ├── ui/             # shadcn primitives (reconfigurées)
    │   ├── layout/
    │   │   └── Sidebar.tsx
    │   ├── dashboard/
    │   │   ├── NodeCard.tsx
    │   │   └── NodeStatusBadge.tsx
    │   ├── node/
    │   │   ├── MetricsBar.tsx
    │   │   ├── ServiceList.tsx
    │   │   ├── ContainerList.tsx
    │   │   └── LogViewer.tsx
    │   ├── chat/
    │   │   ├── ChatPanel.tsx
    │   │   ├── ChatMessage.tsx
    │   │   └── ProposalCard.tsx
    │   └── audit/
    │       └── AuditLog.tsx
    └── pages/
        ├── LoginPage.tsx
        ├── DashboardPage.tsx
        ├── NodeDetailPage.tsx
        ├── ChatPage.tsx
        ├── ProposalsPage.tsx
        ├── AuditPage.tsx
        ├── PluginsPage.tsx
        └── SettingsPage.tsx
```

---

## Ordre d'implémentation

| Étape | Composant | Dépend de |
|---|---|---|
| 1 | Setup Vite + Tailwind + shadcn/ui custom theme | Rien |
| 2 | Layout (Sidebar) + Router | Rien |
| 3 | LoginPage + auth | Layout |
| 4 | DashboardPage + NodeCard | Layout, auth |
| 5 | NodeDetailPage + MetricsBar + ServiceList | Dashboard |
| 6 | LogViewer | NodeDetail |
| 7 | ChatPage + SSE streaming + ProposalCard | Layout, auth |
| 8 | ProposalsPage | Chat |
| 9 | AuditLog | Layout, auth |
| 10 | PluginsPage + SettingsPage | Layout, auth |
| 11 | Déploiement (build → Nginx) | Tout |

## Estimation

| Phase | Sessions |
|---|---|
| Setup + Layout + Auth | 1 |
| Dashboard + Node Detail | 1 |
| Logs + Chat + Proposals | 1-2 |
| Audit + Plugins + Settings | 1 |
| Déploiement + polish | 1 |
| **Total** | **5-6** |
