# Vigile Sprint 4 — Frontend HTMX/SSR

## Plan Corrigé (basé sur SPRINT4_FRONTEND.md + mockup_directions.html)

**Date :** 2026-05-17
**Note :** Remplace le plan React SPA v1 qui était basé sur des docs obsolètes.

---

## 1. Stack Technique

```
FastAPI + Jinja2Templates (Server-Side Rendering)
HTMX              → interactivité, polling, navigation sans JS custom
Tailwind CSS v4   → CDN @tailwindcss/browser (pas de build npm)
Inter (Google Fonts)
Tabler Icons      → SVG inline, text-muted, 14px max
EventSource JS    → SSE streaming chat (LE seul JS custom)
jinja2            → à ajouter aux dépendances (pip install jinja2)
```

### Architecture de déploiement

```
Navigateur ── HTTPS ── Nginx Proxy Manager ──→ master:8002
```

Tout est servi par le master FastAPI lui-même :

- Templates Jinja2 rendus par FastAPI
- Pas de build séparé, pas de CORS, pas de port supplémentaire
- Les appels API `/api/*` existent toujours — la différence : le frontend est servi par le master

### Dépendances à ajouter

```bash
pip install jinja2
```

C'est la seule nouvelle dépendance. Jinja2 est déjà une dépendance transitive de `starlette` (via FastAPI), mais doit être installée explicitement pour utiliser `Jinja2Templates`.

### Nouvelles routes frontend (dans `master/api/frontend.py`)

```
GET  /login              → login.html (public)
POST /login              → login (session cookie) → redirect /
POST /logout             → clear session → redirect /login
GET  /                   → dashboard.html (auth)
GET  /nodes/{id}         → node.html (auth, tabs inline)
GET  /nodes/{id}/services  → _services.html fragment (HTMX)
GET  /nodes/{id}/containers → _containers.html fragment (HTMX)
GET  /nodes/{id}/logs    → _logs.html fragment (HTMX)
GET  /nodes/{id}/metrics → _metrics.html fragment (HTMX poll 15s)
GET  /chat/stream        → SSE EventSource (Operator+)
GET  /proposals          → proposals.html (Operator+)
GET  /audit              → audit.html (Admin)
GET  /plugins            → plugins.html (Admin)
```

---

## 2. Direction Visuelle — Glass Dark Ops

### Palette (depuis mockup_directions.html)

```
Background  #050505      (noir profond)
Surface     #0a0a0c      (panels, sidebar)
Surface-2   #111114      (cartes secondaires, inputs)
Border      white/5 à white/10
Text        white        (primaire)
Text muted  neutral-400 / #a3a3a3
Accent      teal-400 / #14b8a6  (UNIQUE accent — badges, CTAs, actif)
Danger      red-400 / #f87171   (FAILED, erreurs)
Warning     amber-500 / #f59e0b (LOST, dégradés)
Info        blue-600 / #1d4ed8  (auto-discovery, info)
```

### Glassmorphism

```css
/* Pattern commun pour toutes les cartes, panels, inputs */
.glass-panel {
  @apply bg-white/[0.02] border border-white/[0.05] backdrop-blur-xl;
}

/* Surface active (cartes cliquables) */
.card-active {
  @apply bg-[#111114] border border-white/5 hover:border-teal-500/40;
}

/* Inputs / barres */
.input-glass {
  @apply bg-white/5 border border-white/10;
}
```

### Layout type

```
┌──────────┬───────────────────────────────┬──────────────┐
│ Sidebar  │         #main                  │  Copilot     │
│ 80-240px │  (contenu principal)           │  340-400px   │
│          │  carrousels Netflix            │  (droite)    │
│          │  overflow-x-auto               │              │
│ expand   │  scrollable                    │  glassmorphic│
│ on hover │                                │  chat +      │
│          │                                │  proposals   │
└──────────┴───────────────────────────────┴──────────────┘
```

**Détails layout :**

- **Sidebar gauche** : 80px fixe → 240px au hover (transition 300ms). Overlay `z-50`. Fixed width wrapper évite les sauts de layout.
- **Header** : Dans `#main` — titre de page + sélecteur de nœud (optionnel, comme dans la maquette)
- **Contenu `#main`** : Carrousels horizontaux (Netflix-style) avec `overflow-x-auto netflix-row snap-x`
- **Copilot droite** : Sidebar droite permanente 340-400px, glassmorphic, `backdrop-blur-3xl`
- **HTMX swap** : Dans `#main-content` (sous le header)
- **Un seul squelette HTML** : `base.html` avec blocks Jinja2

### Typographie

- Inter uniquement (Google Fonts via Tailwind `font-sans`)
- Taille : `text-[13px]` à `text-[15px]` selon le contexte
- **Pas de JetBrains Mono** (contrairement au plan React v1)

### Glows & Ombres (depuis la maquette)

```css
.glow-teal    { box-shadow: 0 0 15px rgba(45,212,191,0.2); }
.glow-status  { box-shadow: 0 0 8px rgba(16,185,129,0.8); }
.glow-blue    { box-shadow: 0 0 20px rgba(37,99,235,0.4); }
.panel-shadow { box-shadow: 0 4px 20px rgba(0,0,0,0.5); }
.sidebar-shadow { box-shadow: 10px 0 30px rgba(0,0,0,0.5); }
```

---

## 3. Auth — Session Cookie (adaptation pour SSR)

Le backend existant utilise JWT (Bearer token en JSON). Pour le rendu SSR, on a besoin d'une session.

### Stratégie

1. **Login** : `POST /api/auth/login` → récupère le JWT → le stocke dans un cookie httpOnly signé
2. **Middleware frontend** : lit le cookie JWT, le valide, attache `request.user` pour les templates
3. **Logout** : efface le cookie
4. **Templates** : utilisent `request.user.role` pour afficher/cacher des éléments

### SessionMiddleware (FastAPI/Starlette)

```python
from starlette.middleware.sessions import SessionMiddleware

# Dans main.py, après création de l'app
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.server_secret_key,
    session_cookie="vigile_session",
    max_age=86400,  # 24h
    same_site="lax",
    https_only=False,  # True en prod
)
```

### Frontend auth middleware

```python
# master/api/frontend.py
from fastapi import Request, HTTPException
from master.api.deps import get_security

async def require_auth(request: Request):
    """Vérifie le cookie de session et injecte l'utilisateur."""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    try:
        security = get_security()
        payload = security.validate_access_token(token)
        request.state.user = {
            "user_id": payload["sub"],
            "username": payload.get("username", "unknown"),
            "role": payload.get("role", "viewer"),
        }
    except Exception:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
```

**Note LIMITS.md** : Le backend a `CORS_ORIGINS=*` avec `allow_credentials=True` — mais comme le frontend est servi par le master (même origine), le CORS n'est pas un problème pour les routes frontend. Les API restent accessibles via `fetch`/`hx-headers` avec le cookie.

---

## 4. Pages & Templates

### Structure des fichiers

```
master/
├── main.py                 # + Jinja2Templates + StaticFiles + frontend router
├── api/
│   └── frontend.py         # NOUVEAU : routes frontend (login, dashboard, etc.)
├── templates/              # NOUVEAU
│   ├── base.html           # Squelette : sidebar + #main + copilot
│   ├── login.html          # Page login
│   ├── dashboard.html      # Dashboard carrousels
│   ├── node.html           # Détail nœud (tabs : stats, services, containers, logs)
│   ├── _services.html      # Fragment services (HTMX)
│   ├── _containers.html    # Fragment containers (HTMX)
│   ├── _logs.html          # Fragment logs (HTMX)
│   ├── _metrics.html       # Fragment métriques (HTMX poll)
│   ├── proposals.html      # Propositions d'actions
│   ├── audit.html          # Audit trail
│   └── plugins.html        # Catalogue plugins
└── static/                 # NOUVEAU
    ├── css/
    │   └── app.css         # Styles customs (si besoin, sinon CDN only)
    └── js/
        └── chat.js         # EventSource SSE — LE seul JS custom
```

### base.html — Squelette global

```html
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Vigile{% endblock %}</title>
    <script src="https://unpkg.com/@tailwindcss/browser@4"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
</head>
<body class="bg-[#050505] text-white font-sans antialiased">
    <div class="flex h-screen">
        <!-- Sidebar (80px → 240px hover) -->
        <nav class="w-[80px] hover:w-[240px] group transition-all duration-300 ...">
            {% include "_sidebar.html" %}
        </nav>

        <!-- Main content -->
        <main class="flex-1 flex flex-col min-w-0">
            <header>{% block header %}{% endblock %}</header>
            <div id="main-content" class="flex-1 overflow-y-auto">
                {% block content %}{% endblock %}
            </div>
        </main>

        <!-- Copilot sidebar (340-400px) -->
        <aside class="w-[340px] lg:w-[400px] ...">
            {% include "_copilot.html" %}
        </aside>
    </div>

    <script src="/static/js/chat.js"></script>
</body>
</html>
```

### Dashboard (Netflix-style rows)

```html
<!-- Hero Auto-Discovery -->
<div class="rounded-3xl bg-gradient-to-r from-blue-900/40 ...">
    <!-- Plugin suggestion banner -->
</div>

<!-- Row 1: Vitals (signes vitaux) -->
<div class="flex gap-5 overflow-x-auto netflix-row snap-x">
    {% for metric in metrics %}
    <div class="snap-start w-[240px] glass-panel rounded-2xl p-5">
        <!-- icône + valeur + barre progression colorée -->
    </div>
    {% endfor %}
</div>

<!-- Row 2: Docker containers -->
<div class="flex gap-5 overflow-x-auto netflix-row snap-x">
    {% for container in containers %}
    <div class="snap-start w-[300px] bg-[#111114] rounded-2xl border border-white/5">
        <!-- gradient header + status badge + infos + buttons -->
    </div>
    {% endfor %}
    <!-- "Déployer un conteneur" card (dashed border) -->
</div>

<!-- Row 3: Plugin example (Plex, etc.) -->
<div class="flex gap-5 overflow-x-auto netflix-row snap-x">
    <!-- media cards with cover image + progress -->
</div>
```

### Copilot sidebar (présente sur toutes les pages)

```
┌──────────────────────────┐
│ ✨ Vigile Copilot         │
│ ● Connecté au système     │
│                           │
│ ┌─ Messages ───────────┐ │
│ │ IA: bulle glassmorphic│ │
│ │ User: bulle teal/10   │ │
│ │ Action proposal card  │ │
│ └──────────────────────┘ │
│                           │
│ [Suggestion rapide]       │
│ [Suggestion rapide]       │
│ ┌─ Input chat ─────────┐ │
│ │ ▓                     │ │
│ └──────────────────────┘ │
└──────────────────────────┘
```

### Chat SSE (EventSource JS)

```javascript
// static/js/chat.js — LE seul fichier JS custom
const es = new EventSource(`/chat/stream?node_id=${nodeId}`);

es.addEventListener('token', (e) => {
    const data = JSON.parse(e.data);
    appendToMessage(data.content);
});

es.addEventListener('proposal', (e) => {
    const data = JSON.parse(e.data);
    showProposalCard(data);
});

es.addEventListener('error', (e) => {
    showError("Connexion perdue. Reconnexion...");
});

es.addEventListener('done', () => {
    es.close();
});
```

---

## 5. HTMX Patterns (remplacent tout le state management React)

### Principe

Aucun JS custom sauf EventSource pour le chat. HTMX gère tout :

- Navigation (`hx-get`, `hx-target`, `hx-push-url`)
- Polling (`hx-trigger="every 15s"`)
- Formulaires (`hx-post`, `hx-target`)
- Pagination infinie (`hx-trigger="revealed"`)

### Navigation

```html
<a hx-get="/nodes/{{ node.id }}" hx-target="#main-content" hx-push-url="true"
   class="...">
  {{ node.name }}
</a>
```

### Polling métriques

```html
<div hx-get="/nodes/{{ id }}/metrics"
     hx-trigger="every 15s"
     hx-target="#metrics-panel"
     hx-swap="innerHTML">
  {% include "_metrics.html" %}
</div>
```

### Formulaires

```html
<form hx-post="/login" hx-target="#login-error" hx-swap="innerHTML">
    <input type="text" name="username" required>
    <input type="password" name="password" required>
    <button type="submit">Sign in</button>
</form>
```

### Pagination logs (infinite scroll)

```html
<div hx-get="/nodes/{{ id }}/logs?offset={{ next_offset }}"
     hx-trigger="revealed"
     hx-swap="afterend">
</div>
```

---

## 6. Ordre d'Implémentation

| Étape | Composant | Dépend de | Fichiers | Est. |
|-------|-----------|-----------|----------|------|
| 1 | Setup Jinja2 + StaticFiles + frontend router | Rien | `main.py` (modif), `requirements.txt` | 30min |
| 2 | base.html (sidebar, #main, copilot layout) | Étape 1 | `base.html`, `_sidebar.html`, `_copilot.html` | 1 session |
| 3 | Login + auth session + middleware | Étape 2 | `frontend.py`, `login.html` | 1 session |
| 4 | Dashboard (carrousels, hero, polling) | Étape 3 | `dashboard.html`, `_metrics.html` | 1 session |
| 5 | Node detail (tabs, services, containers, logs) | Étape 4 | `node.html`, `_services.html`, `_containers.html`, `_logs.html` | 1 session |
| 6 | Chat SSE (EventSource + copilot) | Étape 3 | `chat.js`, `_copilot.html` (modif) | 1 session |
| 7 | Proposals page | Étape 3 | `proposals.html` | 0.5 session |
| 8 | Audit page | Étape 3 | `audit.html` | 0.5 session |
| 9 | Plugins page | Étape 3 | `plugins.html` | 0.5 session |

**Total : ~6-7 sessions** (vs 5 estimé dans SPRINT4_FRONTEND.md — plus réaliste avec les sessions auth)

### Dépendances entre étapes

```
Étape 1 (setup) ──→ Étape 2 (layout) ──→ Étape 3 (login/auth)
                                                  │
                    ┌──────────────────────────────┤
                    │                              │
               Étape 4 (dashboard)            Étape 6 (chat SSE)
                    │                              │
               Étape 5 (node detail)           Étape 7 (proposals)
                    │
               Étape 8 (audit) + Étape 9 (plugins)
```

Étapes 6/7 et 8/9 peuvent être parallélisées.

---

## 7. Contraintes LIMITS.md Appliquées

| LIMITE | Impact Frontend | Solution |
|--------|----------------|----------|
| **CORS wildcard + credentials** | Bloquant si frontend séparé | ✅ Frontend servi par master (même origine = pas de CORS) |
| **Rate limiter cleanup jamais appelé** | 429 peut arriver après usage prolongé | ✅ HTMX polling doit gérer 429 avec Retry-After header. Afficher temps d'attente |
| **Pas de pagination list_nodes** | Dashboard lent avec 500+ nœuds | ✅ Client-side filter dans template Jinja2. Acceptable en Sprint 4 |
| **Refresh token sans invalidation** | Session cookie = 24h TTL. Pas de refresh token exposé au frontend | ✅ Cookie JWT avec rotation automatique. Si volé, valide 24h max |
| **Plugin hook async ignoré** | Plugin peut sembler chargé mais ne pas répondre | ✅ Template plugins.html affiche l'état réel via l'API |
| **Pending intents non nettoyés** | Proposals PENDING peuvent être orphelines | ✅ Frontend affiche le statut temps réel via polling |

---

## 8. Gestion d'Erreurs (adaptée du plan React — applicable à HTMX)

Les insights du critique Perfectionist restent valables, adaptés à l'architecture HTMX :

### États par page

| Page | Loading | Empty | Error | Edge |
|------|---------|-------|-------|------|
| Login | spinner bouton | N/A | message inline + champs conservés | Déjà connecté → redirect / |
| Dashboard | skeleton shimmer cartes (Tailwind `animate-pulse`) | "Aucun nœud. [Enrôler]" | Toast erreur polling partiel | 500+ nœuds → scroll |
| Node Detail | skeleton panneaux | "En attente du premier heartbeat" | 404 → "Nœud supprimé" + lien retour | Transition CONNECTED→LOST pendant affichage |
| Chat SSE | curseur clignotant | placeholder "Pose une question" | Bannière "Connexion perdue" + reconnexion | Tab background → garde le streaming |
| Proposals | skeleton liste | "Aucune proposition en attente" | Toast si approve/reject fail | Proposition approuvée depuis un autre onglet |
| Audit | skeleton timeline | "Aucun événement" | Chaîne cassée → highlight rouge | Millions d'entrées → pagination |

### HTTP Errors spécifiques au frontend HTMX

- **401** : Le middleware redirect vers `/login?reason=expired`
- **403** : Le template n'affiche pas les actions admin. Si accès forcé → message "Accès refusé"
- **429** : HTMX `hx-trigger` doit respecter le `Retry-After`. Afficher "Trop de requêtes. Réessayez dans Xs"
- **5xx** : Fragment d'erreur inline (pas de page blanche)

### Gestion offline (navigator.onLine)

- Bannière fixe en haut : "⚠️ Connexion perdue. Les données peuvent être obsolètes."
- HTMX continue de tenter les requêtes (elles échoueront silencieusement)
- Au retour en ligne : rafraîchir `#main-content`

---

## 9. Checklist Production

- [x] `jinja2` ajouté à `requirements.txt`
- [x] `Jinja2Templates` monté dans `main.py` avec directory `master/templates/`
- [x] `StaticFiles` monté pour `/static/` → `master/static/`
- [x] `frontend.py` router créé et inclus dans `main.py`
- [x] SessionMiddleware configuré (cookie signé, httpOnly, same_site=lax)
- [x] Login POST → session cookie JWT → redirect /
- [x] Logout → clear cookie → redirect /login
- [x] Middleware auth sur toutes les routes frontend protégées
- [x] base.html : sidebar 80→240px, #main scrollable, copilot 340-400px
- [x] Dashboard : hero discovery + vitals row + docker row + plugin row
- [x] Node detail : breadcrumb + tabs (stats, services, containers, logs)
- [x] Chat SSE : EventSource JS, token/proposal/error/done events
- [x] Copilot : messages, proposals, input, suggestions
- [x] Proposals : liste filtrée, approve/reject inline
- [x] Audit : timeline, SHA256 chain verify
- [x] Plugins : data-driven depuis `/api/admin/plugins`
- [x] Gestion 429 : messages explicites, cooldown
- [x] Offline detection : bannière + auto-refresh au retour
- [x] Loading skeletons : shimmer sur toutes les données
- [x] Empty states : messages utiles avec CTA

---

## 10. Ce qui RESTE DU PLAN REACT V1 (insights conservés)

| Insight | Source | Adapté pour HTMX |
|---------|--------|-------------------|
| SSE doit gérer reconnexion + déduplication | Perfectionist | EventSource reconnecte auto. `last_event_id` pour dédup |
| Token refresh race condition | Perfectionist | Cookie session = pas de refresh token exposé. Cookie JWT avec durée |
| WCAG AA: keyboard nav, aria-live, contrast, reduced-motion | Perfectionist | Applicable inchangé. HTML sémantique, `aria-live` pour SSE |
| Double-submit prevention | Perfectionist | HTMX `hx-disable` sur les boutons pendant requête |
| Erreur CORS en prod | Architect | Résolu : frontend servi par le master = même origine |
| Layout 3-col + copilot permanent | Innovator | Exactement le layout de mockup_directions.html |
| Icônes Tabler, pas de lib lourde | — | Directive SPRINT4_FRONTEND.md respectée |
| Dark glassmorphism, teal accent | — | Directe de mockup_directions.html |
| Chat proposals data-source-agnostic | Architect | ProposalCard réutilisable = fragment Jinja2 avec include |
| Tests | Implementor | Tests backend des routes frontend avec `TestClient`. Tests JS = manuels |
| CI/CD | Implementor | Pas de build frontend. CI = typecheck + lint du Python backend |

---

## 11. Annexe : Exemple base.html (layout complet)

```html
{# master/templates/base.html #}
{% load static %}
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Vigile{% endblock %}</title>
    <script src="https://unpkg.com/@tailwindcss/browser@4"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        @theme { --font-sans: 'Inter', sans-serif; }
        .glass-panel { @apply bg-white/[0.02] border border-white/[0.05] backdrop-blur-xl; }
        .netflix-row::-webkit-scrollbar { display: none; }
        .netflix-row { -ms-overflow-style: none; scrollbar-width: none; }
        body { @apply bg-[#050505] text-white font-sans antialiased; }
    </style>
    {% block head %}{% endblock %}
</head>
<body>
<div class="flex h-screen">
    <!-- Sidebar gauche : 80px → 240px hover -->
    <div class="w-[80px] shrink-0 z-50 relative">
        <nav class="absolute inset-0 w-[80px] hover:w-[240px] group transition-all duration-300
                    bg-[#0a0a0c] border-r border-white/5 flex flex-col overflow-hidden
                    shadow-[10px_0_30px_rgba(0,0,0,0.5)] backdrop-blur-3xl">
            <div class="h-20 flex items-center px-6 border-b border-white/5 shrink-0">
                <div class="w-8 h-8 rounded-full bg-teal-500/20 text-teal-400 flex items-center justify-center font-bold
                            shadow-[0_0_15px_rgba(45,212,191,0.2)] shrink-0">V</div>
                <span class="ml-4 font-bold text-lg opacity-0 group-hover:opacity-100 whitespace-nowrap">Vigile</span>
            </div>
            <div class="flex-1 py-6 flex flex-col gap-2 overflow-y-auto">
                <a href="/" hx-get="/" hx-target="#main-content" hx-push-url="true"
                   class="flex items-center px-6 py-3 {% if active_page == 'dashboard' %}text-white bg-white/5{% else %}text-neutral-400{% endif %} hover:text-white hover:bg-white/5">
                    <svg class="w-6 h-6 shrink-0" ...><!-- icône dashboard --></svg>
                    <span class="ml-4 font-medium opacity-0 group-hover:opacity-100 whitespace-nowrap">Vue Principale</span>
                </a>
                <div class="mt-6 mb-2 px-6 opacity-0 group-hover:opacity-100 text-[11px] font-bold text-neutral-500 uppercase tracking-wider">Catalogue</div>
                <a href="/proposals" hx-get="/proposals" hx-target="#main-content" hx-push-url="true" ...>Propositions</a>
                {% if user.role == 'admin' %}
                <a href="/audit" hx-get="/audit" hx-target="#main-content" hx-push-url="true" ...>Audit</a>
                <a href="/plugins" hx-get="/plugins" hx-target="#main-content" hx-push-url="true" ...>Plugins</a>
                {% endif %}
            </div>
            <div class="px-6 py-4">
                <a href="/logout" class="flex items-center text-neutral-500 hover:text-white">Déconnexion</a>
            </div>
        </nav>
    </div>

    <!-- Main content area -->
    <main class="flex-1 flex flex-col min-w-0 bg-[#0d0d12] relative overflow-hidden">
        <div class="absolute top-0 left-0 right-0 h-96 bg-gradient-to-b from-teal-900/20 to-transparent pointer-events-none"></div>

        <header class="h-20 flex items-center justify-between px-8 shrink-0 relative z-10 border-b border-white/[0.02]">
            <h2 class="text-xl font-bold">{% block page_title %}Vue Principale{% endblock %}</h2>
            {% block header_right %}
            <div class="flex items-center gap-3 bg-white/[0.05] px-4 py-2 rounded-full border border-white/10">
                <span class="w-2 h-2 rounded-full bg-teal-400 shadow-[0_0_8px_rgba(45,212,191,0.6)]"></span>
                <span class="text-sm font-semibold">{{ user.username }}</span>
            </div>
            {% endblock %}
        </header>

        <div id="main-content" class="flex-1 overflow-y-auto pb-20 pt-8 relative z-10">
            {% block content %}{% endblock %}
        </div>
    </main>

    <!-- Copilot sidebar droite -->
    <aside class="w-[340px] lg:w-[400px] bg-white/[0.02] backdrop-blur-3xl border-l border-white/[0.05]
                  flex flex-col shrink-0 shadow-[-20px_0_40px_rgba(0,0,0,0.3)] relative overflow-hidden">
        <div class="absolute top-0 right-0 w-full h-[500px] bg-gradient-to-b from-teal-500/10 to-transparent pointer-events-none"></div>
        {% block copilot %}
        {% include "_copilot.html" %}
        {% endblock %}
    </aside>
</div>
<script src="/static/js/chat.js"></script>
</body>
</html>
```
