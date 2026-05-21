## [2026-05-18] Session start

### Verified state
- All infrastructure items (1-8): ✅ jinja2 in requirements, Jinja2Templates, StaticFiles, frontend router, SessionMiddleware, login/logout, auth middleware
- All page templates (9-16): ✅ base.html refactored teal/Inter/glass, dashboard Netflix-style, node 4 tabs, chat SSE, copilot, proposals approve/reject, audit, plugins
- All 14 templates exist in master/templates/
- chat.js: 283 lines with EventSource SSE + approve/reject

### Remaining items (17-20)
- 429 error handling: frontend.py rate limit responses, HTMX error display
- Offline detection: navigator.onLine banner + auto-refresh
- Loading skeletons: shimmer on dashboard, node, proposals ✅
- Empty states: CTA messages on all pages ✅

### Key files
- master/api/frontend.py: SSR routes, fragment endpoints, auth
- master/static/js/chat.js: EventSource SSE streaming
- master/templates/base.html: Layout + CSS design system
- master/templates/dashboard.html: Hero + vitals + rows
- master/templates/node.html: Breadcrumb + 4 tabs

## [2026-05-18] Loading Skeletons & Empty States (Items 19-20)

### Implementation summary

#### Loading Skeleton Cards:
Used existing `@keyframes shimmer` from base.html with a new `.skeleton` CSS class added in each template's `head_extra` block:
```css
.skeleton {
  background: linear-gradient(90deg, var(--border-strong) 0%, rgba(255,255,255,0.05) 50%, var(--border-strong) 100%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: 3px;
}
.skeleton-card {
  background: var(--surface);
  border: 1.5px solid var(--border-strong);
  border-radius: var(--r);
  padding: 1.1rem;
  overflow: hidden;
}
```

Placed in HTMX loading indicators: `<div class="htmx-indicator" aria-hidden="true" style="display:none;">`

Files modified:
- **dashboard.html**: Skeleton vitals row (4 cards) + skeleton node cards (3 cards) + enhanced empty state with "Enrôler un worker" CTA button
- **node.html**: Skeleton metrics panel (4 gauge cards) + skeleton tab content (4 rows) 
- **proposals.html**: Skeleton list items (3 rows) + enhanced empty state with French message
- **audit.html**: Skeleton table rows (4 rows with 6 columns) + enhanced empty state "Aucune entrée d'audit"
- **plugins.html**: Skeleton plugin cards (3 items) + enhanced empty states for both plugins and hooks

#### Empty States:
All empty states now use consistent pattern:
```html
<div class="flex flex-col items-center justify-center py-12 text-center fade-in">
  <i class="ti ti-XXX text-3xl" style="color: var(--ink-muted);"></i>
  <p class="mt-3 text-sm font-medium" style="color: var(--ink-muted);">{message}</p>
  <p class="mt-1 text-xs" style="color: var(--ink-dim);">{sub-message}</p>
</div>
```

Files modified:
- **_metrics.html**: "En attente des premières métriques" + subtle pulse indicator
- **_services.html**: "Aucun service système sur ce nœud"
- **_containers.html**: "Aucun conteneur Docker sur ce nœud"
- **_logs.html**: "Aucune entrée de log"

Not modified (per rules): base.html, frontend.py, chat.js, any .py files, any JS files.

### Design system compliance
- All colors use CSS variables (var(--ink-muted), var(--ink-dim), var(--surface), etc.)
- All skeletons use `aria-hidden="true"` for accessibility
- All empty states use Tabler Icons (ti-* classes)
- Uses existing glass/teal design system
- No external dependencies added
- No existing functionality changed
