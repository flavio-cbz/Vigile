# Sprint 4 — Frontend Vigile

## Stack technique

```
Vite + React 19 + TypeScript
TailwindCSS v4 + shadcn/ui (Radix primitives)
React Router v7 (routing)
EventSource (SSE natif, zero lib)
Tabler Icons ou Lucide React
```

## Architecture de déploiement

```
Navigateur ── HTTPS ── Nginx Proxy Manager ──┬── /api/* ──→ master:8002
                                              └── /*    ──→ fichiers statiques React
```

Le frontend est servi par Nginx en tant que site statique. Les appels `/api/*`
sont proxifiés vers le master. Pas de CORS, pas de port supplémentaire.

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

## Design System

### Palette (dark theme first — serveur, faut pas se brûler les yeux)

```
Fond principal      #0f172a  (slate-900)
Fond secondaire     #1e293b  (slate-800)
Bordure             #334155  (slate-700)
Texte principal     #f1f5f9  (slate-100)
Texte secondaire    #94a3b8  (slate-400)
Succès              #22c55e  (green-500)
Avertissement       #f59e0b  (amber-500)
Erreur              #ef4444  (red-500)
Info                #3b82f6  (blue-500)
```

### Composants shadcn/ui utilisés

```
Button, Input, Card, Badge, Table, Dialog, Tabs,
DropdownMenu, Sheet, Tooltip, Progress, Select,
Switch, Separator, Skeleton, ScrollArea
```

---

## Maquettes par page

### 1. Login

```
╔══════════════════════════════════════════════════╗
║                                                  ║
║                    Vigile                         ║
║           Your self-hosted server guardian        ║
║                                                  ║
║  ┌──────────────────────────────────────────┐    ║
║  │                                          │    ║
║  │  Nom d'utilisateur                       │    ║
║  │  ┌────────────────────────────────────┐  │    ║
║  │  │ admin                              │  │    ║
║  │  └────────────────────────────────────┘  │    ║
║  │                                          │    ║
║  │  Mot de passe                           │    ║
║  │  ┌────────────────────────────────────┐  │    ║
║  │  │ •••••••••                          │  │    ║
║  │  └────────────────────────────────────┘  │    ║
║  │                                          │    ║
║  │  ┌────────────────────────────────────┐  │    ║
║  │  │        Se connecter                │  │    ║
║  │  └────────────────────────────────────┘  │    ║
║  └──────────────────────────────────────────┘    ║
║                                                  ║
╚══════════════════════════════════════════════════╝
```

- Champs : username + password
- Bouton "Se connecter" avec loading state
- Message d'erreur si credentials invalides
- Stocke le JWT dans localStorage, redirect vers `/`

---

### 2. Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│  🔲 Vigile                               admin  ⚙️  🚪    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📊 Aperçu de la flotte                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │  3       │ │  2       │ │  12h     │ │  0       │      │
│  │  Nœuds   │ │  En ligne│ │  Uptime  │ │  Alertes │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│                                                             │
│  🖥️ Nœuds enregistrés                                       │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  ● sim-prod   🟢 CONNECTED   Debian 12  ▶              │ │
│  │  CPU ████████░░ 72%  RAM ████░░░░ 32%                  │ │
│  │  DISK ████████░░ 47%  2 failed services                 │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │  ● web-01     🔴 LOST        Ubuntu 24.04  ▶           │ │
│  │  Dernier contact : il y a 3h                            │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  💬 Assistant IA                                            │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Bonjour, que puis-je faire pour votre flotte ?        │ │
│  │  ┌──────────────────────────────────┐  ✨              │ │
│  │  │  Posez votre question...         │                  │ │
│  │  └──────────────────────────────────┘                  │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

- Barre latérale (ou header) avec navigation
- Cartes de statistiques globales
- Liste des nœuds avec état en temps réel
- Mini chat IA en bas (ouvre vers /chat)

---

### 3. Node Detail

```
┌─────────────────────────────────────────────────────────────┐
│  ← Dashboard  /  sim-prod                                  │
├─────────────────────────────────────────────────────────────┤
│  🟢 CONNECTED   sim-prod                                    │
│  Debian 12  |  x86_64  |  hostname: debian-01              │
│                                                             │
│  ┌───────┐ ┌───────┐ ┌───────┐ ┌──────┐                   │
│  │ CPU   │ │ RAM   │ │ DISK  │ │UPTIME│                   │
│  │ 72%   │ │ 32%   │ │ 47%   │ │ 12h  │                   │
│  └───────┘ └───────┘ └───────┘ └──────┘                   │
│                                                             │
│  ┌─ Stats ──┬─ Services ──┬─ Containers ─┬─ Logs ─┬─ Chat┐ │
│  │                                                       │ │
│  │  📈 CPU / RAM / DISK (graphique 24h)                 │ │
│  │                                                       │ │
│  │  ▁▃▄▆█▇▆▄▃▁▂▃▅▇█▇▆▅▄▃▂▁▂▃▄▅▆▇█                       │ │
│  │  ▄▆█▇▆▅▄▃▂▁▂▃▄▅▆▇█▇▆▅▄▃▂▁▂▃▄▅▆▇█▇▆                    │ │
│  │                                                       │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Onglet Services :**
```
┌─ Stats ──┬─ Services ─┬─ Containers ─┬─ Logs ─┬─ Chat ┐
│                                                       │
│  🔍 Filtrer...                                        │
│                                                       │
│  Statut  Nom                    ACTIVE   SUB          │
│  ─────── ────────────────────── ──────── ──────       │
│  ●       ssh.service            active   running      │
│  ●       nginx.service          active   running      │
│  ●       docker.service         active   running      │
│  🔴      mysql.service          failed   failed       │
│  🔴      prometheus.service     failed   failed       │
│  ○       apache2.service        inactive dead         │
│  ○       backup.service         inactive dead         │
│                                                       │
│  [Restart] [Start] [Stop]                             │
└───────────────────────────────────────────────────────┘
```

**Onglet Logs :**
```
┌─ Stats ──┬─ Services ─┬─ Containers ─┬─ Logs ─┬─ Chat ┐
│                                                       │
│  Service : [ssh.service ▼]  Lignes : [50 ▼]  🔍      │
│                                                       │
│  ┌──────────────────────────────────────────────────┐ │
│  │ May 15 06:12:01 sshd[1123]: Failed password      │ │
│  │ May 15 06:12:05 sshd[1124]: Failed password      │ │
│  │ May 15 09:00:00 sshd[1250]: Accepted publickey   │ │
│  │ May 15 09:45:10 sshd[1280]: Invalid user admin   │ │
│  │ ...                                               │ │
│  │                                                  │ │
│  └──────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────┘
```

- Terminal-like LogViewer avec police monospace
- ScrollArea illimité
- Service selector pour journalctl
- Refresh automatique

---

### 4. Chat IA

```
┌─────────────────────────────────────────────────────────────┐
│  💬 Assistant IA Vigile                      [Nouveau chat] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 👤 Moi                                   10:32         │ │
│  │ Le serveur nginx semble lent, que faire ?              │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │ 🤖 Vigile                               10:33          │ │
│  │ Je vais vérifier l'état de nginx.                     │ │
│  │                                                        │ │
│  │  📊 STATUT : nginx.service is active (running)        │ │
│  │  📋 LOGS : aucune erreur récente détectée              │ │
│  │                                                        │ │
│  │ 💡 Proposition : RESTART_SERVICE                       │ │
│  │  Action : Redémarrer nginx                             │ │
│  │  Risque : LOW                                          │ │
│  │  Raison : Permet de recharger la configuration         │ │
│  │                                                        │ │
│  │  ┌──────────┐  ┌──────────┐                            │ │
│  │  │ ✓ Valider│  │ ✗ Refuser│                            │ │
│  │  └──────────┘  └──────────┘                            │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │ 👤 Moi                                   10:35         │ │
│  │ Oui redémarre-le.                                      │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │ 🤖 Vigile                               10:36          │ │
│  │ ✅ nginx.service redémarré avec succès.                │ │
│  │ Résultat : Service nginx restarted                     │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Posez votre question...                   📎  🎤  ▶ │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

- SSE streaming en temps réel
- Cartes d'ActionProposal inline
- Historique de conversation
- Boutons Approve/Reject dans les cartes
- Indicateur de streaming (cursor clignotant ou points)

---

### 5. Propositions

```
┌─────────────────────────────────────────────────────────────┐
│  📋 Propositions d'actions              [Tous] [En attente] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🔴 HIGH  Restart mysql.service          sim-prod   10:32  │
│  MySQL a crashé (OOM). Redémarrage nécessaire.             │
│  ┌──────────┐  ┌──────────┐                                │
│  │ ✓ Valider│  │ ✗ Refuser│  💬 Voir contexte              │
│  └──────────┘  └──────────┘                                │
│                                                             │
│  🟡 MEDIUM  LIST_SERVICES                 sim-prod   10:30 │
│  Lister les services pour diagnostic.                      │
│  ┌──────────┐  ┌──────────┐                                │
│  │ ✓ Valider│  │ ✗ Refuser│                                │
│  └──────────┘  └──────────┘                                │
│                                                             │
│  ✅ APPROUVÉ  Restart nginx                web-01   09:15  │
│  Redémarré avec succès. Résultat : OK                     │
│                                                             │
│  ❌ REJETÉ  READ_LOGS                     sim-prod   08:45 │
│  Raison : Pas nécessaire pour le moment                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

- Filtre par statut (PENDING, APPROVED, REJECTED, ALL)
- Tri par date / risque
- Carte de proposition avec risque coloré (LOW/MEDIUM/HIGH/CRITICAL)
- Action rapide Valider/Refuser
- Lien vers le contexte de la conversation

---

### 6. Audit Log

```
┌─────────────────────────────────────────────────────────────┐
│  📜 Audit Trail                            🔍 Filtrer...   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  #   Date       Action              User        Node       │
│  ─── ───────── ──────────────────── ────────── ────────── │
│  42  10:32:15  PROPOSAL_APPROVED   flavio      sim-prod    │
│                → RESTART_SERVICE sur nginx.service          │
│  41  10:30:22  PROPOSAL_CREATED    ai          sim-prod    │
│                → RESTART_SERVICE (risk: LOW)               │
│  40  10:30:10  INTENT_RESULT       system      sim-prod    │
│                → LIST_SERVICES success=true (45 services)  │
│  39  10:29:00  CHAT_MESSAGE        flavio      sim-prod    │
│                → "Liste les services"                      │
│  38  09:15:00  NODE_ENROLLED       system      web-01     │
│  37  08:00:00  LOGIN               admin       -           │
│                                                             │
│  ✅ Chaîne SHA256 intacte — 42 entrées vérifiées           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

- Liste chronologique inversée
- Badge de vérification d'intégrité de la chaîne
- Détail extensible par ligne
- Filtres par type d'action, utilisateur, nœud, date

---

### 7. Plugin Catalogue

```
┌─────────────────────────────────────────────────────────────┐
│  🧩 Catalogue de plugins                                    │
├─────────────────────────────────────────────────────────────┤
│  🔍 Rechercher un plugin...                                 │
│                                                             │
│  ┌──────────────────┐ ┌──────────────────┐                  │
│  │ 📊 Metrics        │ │ 🐳 Docker         │                  │
│  │ Collecte CPU/RAM  │ │ Gestion containers│                  │
│  │ ✅ Activé         │ │ ✅ Activé         │                  │
│  ├──────────────────┤ ├──────────────────┤                  │
│  │ ⚙️ Systemd        │ │ ☁️ Backup         │                  │
│  │ Gestion services  │ │ Sauvegarde auto   │                  │
│  │ ✅ Activé         │ │ 📥 Installer      │                  │
│  ├──────────────────┤ ├──────────────────┤                  │
│  │ 🔔 Alerting       │ │ 📧 Mail Report    │                  │
│  │ Notifications     │ │ Rapport hebdo     │                  │
│  │ 📥 Installer      │ │ 📥 Installer      │                  │
│  └──────────────────┘ └──────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

- Grille de cartes
- Chaque carte : icône, nom, description, statut (activé/installer)
- Bouton d'installation en un clic
- Page de détail du plugin (config, hooks, logs)

---

### 8. Barre latérale (structure pour toutes les pages)

```
┌──────────┬──────────────────────────────────────────────────┐
│ 🔲       │  Header : Vigile              admin  ⚙️  🚪    │
│          │                                                  │
│  📊      │                                                  │
│  Dashboard│            CONTENU PRINCIPAL                    │
│          │                                                  │
│  🖥️      │                                                  │
│  Nœuds   │                                                  │
│          │                                                  │
│  💬      │                                                  │
│  Chat    │                                                  │
│          │                                                  │
│  📋      │                                                  │
│  Actions │                                                  │
│          │                                                  │
│  📜      │                                                  │
│  Audit   │                                                  │
│          │                                                  │
│  🧩      │                                                  │
│  Plugins │                                                  │
│          │                                                  │
└──────────┴──────────────────────────────────────────────────┘
```

---

## API à utiliser

| Endpoint | Usage |
|---|---|
| `POST /api/auth/login` | Login |
| `GET /api/auth/me` | Vérifier token |
| `GET /api/nodes` | Liste des nœuds |
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
| `GET /api/admin/nodes/connections` | Connexions actives |

---

## Structure des fichiers

```
frontend/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.ts
├── index.html
├── public/
│   └── favicon.svg
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── lib/
    │   ├── api.ts          # Client HTTP (fetch wrapper)
    │   ├── auth.ts         # Gestion token JWT
    │   └── sse.ts          # EventSource pour SSE
    ├── hooks/
    │   ├── useAuth.ts
    │   ├── useNodes.ts
    │   ├── useChat.ts
    │   └── useProposals.ts
    ├── components/
    │   ├── ui/             # shadcn/ui components
    │   ├── layout/
    │   │   ├── Sidebar.tsx
    │   │   └── Header.tsx
    │   ├── dashboard/
    │   │   ├── StatsCards.tsx
    │   │   └── NodeList.tsx
    │   ├── node/
    │   │   ├── NodeCard.tsx
    │   │   ├── MetricsPanel.tsx
    │   │   ├── ServiceList.tsx
    │   │   ├── ContainerList.tsx
    │   │   └── BackendLogViewer.tsx
    │   ├── chat/
    │   │   ├── ChatPanel.tsx
    │   │   ├── ChatMessage.tsx
    │   │   └── ProposalCard.tsx
    │   ├── proposals/
    │   │   └── ProposalList.tsx
    │   ├── audit/
    │   │   └── AuditLog.tsx
    │   └── plugins/
    │       └── PluginCatalogue.tsx
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

## Ordre d'implémentation proposé

| Étape | Composant | Dépend de |
|---|---|---|
| 1 | Setup Vite + Tailwind + shadcn/ui | Rien |
| 2 | Layout (Sidebar + Header) | Rien |
| 3 | LoginPage + auth | Layout |
| 4 | DashboardPage + NodeList | Layout, auth |
| 5 | NodeDetailPage + Metrics + Services + Containers | Dashboard |
| 6 | LogViewer | NodeDetail |
| 7 | ChatPage + SSE streaming | Layout, auth |
| 8 | ProposalList + ActionProposalCard | Chat |
| 9 | AuditLog | Layout, auth |
| 10 | PluginCatalogue | Layout, auth |
| 11 | SettingsPage | Layout, auth |
| 12 | Intégration Nginx + déploiement | Tout |

---

## Durée estimée

| Phase | Temps |
|---|---|
| Setup + Layout + Auth | 1 session |
| Dashboard + Node Detail | 1 session |
| Logs + Chat + Proposals | 1-2 sessions |
| Audit + Plugins + Settings | 1 session |
| Déploiement + polish | 1 session |
| **Total** | **5-6 sessions** |
