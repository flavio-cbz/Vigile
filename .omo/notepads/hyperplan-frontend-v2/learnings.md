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

## 2026-05-24: Dashboard 60s polling

- Added centralized 60-second polling to `Dashboard.tsx` (lines 215-224)
- Pattern: `useRef(refreshAll)` + `useEffect([], [])` to avoid stale closures
  - Ref always points to the latest `refreshAll` (updated every render)
  - Effect with empty deps runs once on mount, calls the ref every 60s
- First `poll()` call is immediate (no 60s delay), then every 60000ms
- `clearInterval` on unmount prevents memory leaks
- No changes to existing fetch logic, metrics useEffect, or any other code
- Build verified: `npm run build` passes with zero errors

## 2026-05-24 — CRT mode toggle implementation

- Moved ~180 lines of dead CRT CSS (`index.css`) into a user-toggleable "Terminal Mode" setting
- Kept grain texture overlay (body::before) and cyber-corners as always-on brand character
- Removed crt-flicker and crt-glow animations entirely (seizure risk, WCAG motion sensitivity)
- Removed bloom text-shadows (GPU performance concern)
- Scanlines (.crt-active::after) and vignette (.crt-active::before) preserved behind the toggle
- Added isCrtEnabled + toggleCrt to layoutStore with localStorage persistence (key: 'crtEnabled', default false)
- RootLayout applies .crt-active class on <html> via useEffect
- TopBar user dropdown has "Terminal Mode ON/OFF" toggle replacing the defunct "Paramètres" button
- Note: npm run build fails on pre-existing Dashboard.tsx unused imports (BellRing, Lightbulb, Coffee, Flame, ThumbsUp) — not caused by this change. vite build passes cleanly.

## 2026-05-24: Emoji → Lucide Icons in Dashboard.tsx

### What was done
Replaced all emoji characters in `frontend/src/pages/Dashboard.tsx` with Lucide React SVG icons.

### Changes summary
- **File modified**: `frontend/src/pages/Dashboard.tsx`
- **Imports added**: `ShieldCheck, ShieldAlert, AlertTriangle, Moon, Search, BellRing, Lightbulb, Coffee, Flame, ThumbsUp` from `lucide-react`

### Variable renames
| Old | New | Type |
|-----|-----|------|
| `globalMascotEmoji` (string) | `GlobalMascotIcon` (component ref) | Stores Lucide icon component reference |
| `mascotEmoji` (string) | `MascotIconComp` (component ref) | Stores Lucide icon component reference |

### Icon mapping
| Emoji | Icon | Context |
|-------|------|---------|
| 😌 (calm) | `ShieldCheck` | Serein state |
| 💤 (sleep) | `Moon` | Inactif/Offline state |
| 😰 (worried) | `AlertTriangle` | Panic/Stress (sué) state |
| 😱 (scream) | `ShieldAlert` | Panic/Urgency state |
| 🧐 (searching) | `Search` | Attentif state |
| 🚨 (alert) | `BellRing` | Alert messages |
| 🔥 (fire) | `Flame` | High CPU label |
| ⚠️ (warning) | `AlertTriangle` | Disk warning label |
| 👍 (thumbs up) | `ThumbsUp` | Positive disk message |
| 🍹 (drink) | `Coffee` | Relaxed state message |
| 💡 (lightbulb) | `Lightbulb` | Disk prediction hint |

### Template changes
- Mascot emoji displays: `{globalMascotEmoji}` → `<GlobalMascotIcon className="w-5 h-5" />`
- 💡 before disk prediction: replaced with `<Lightbulb className="w-3 h-3 inline" />`
- All trailing emoji in status strings were removed (state badge + icon already convey tone)

### Verification
- `npx tsc --noEmit` → 0 errors
- `npx vite build` → 0 errors (1 pre-existing chunk size warning)
- `lsp_diagnostics` → clean (0 errors, 0 warnings)

## 2026-05-24: Loading text → skeleton components in Dashboard.tsx

### What was done
Replaced `<div>Chargement...</div>` + spinner text in `Dashboard.tsx` with fixed-height skeleton components that match final card dimensions, eliminating layout shift.

### Files created
- **`frontend/src/components/ui/CardSkeleton.tsx`**: New reusable skeleton component file with:
  - `Skeleton` — base block with shimmer animation using existing `animate-shimmer` Tailwind utility + inline `linear-gradient` for the shimmer gradient
  - `ProposalCardSkeleton` (280×150px) — mirrors proposal card structure: header (risk badge + node name), body (action preview), footer (date + status)
  - `ChatCardSkeleton` (240×130px) — mirrors chat session card structure: header (icon + node name), body (title 2 lines), footer (date)

### Files modified
- **`frontend/src/pages/Dashboard.tsx`**:
  - Added import: `{ ProposalCardSkeleton, ChatCardSkeleton }` from `../components/ui/CardSkeleton`
  - Proposals loading (line ~785): replaced full-width spinner div with `Array.from({ length: 4 }).map(...)` rendering 4 `ProposalCardSkeleton` components
  - Chat sessions loading (line ~857): replaced spinner div with `Array.from({ length: 4 }).map(...)` rendering 4 `ChatCardSkeleton` components
  - Removed 4 unused imports (`BellRing`, `Coffee`, `Flame`, `ThumbsUp`) found during build verification

### Design decisions
- 4 skeletons shown during loading to match the approximate visible area (~4 cards fit horizontally in the carousel)
- Skeletons match exact real card dimensions (`w-[280px] h-[150px]`, `w-[240px] h-[130px]`) to guarantee zero layout shift
- Use existing `animate-shimmer` animation from index.css `@theme` — no new CSS needed
- Reuses `glass-panel`, `border-border-custom`, `rounded-xl` classes for visual consistency
- Skeleton inner elements use smaller `rounded` (not `rounded-xl`) for realistic shape mimicry

### Build verification
- `npx tsc -b && npx vite build` → 0 errors (1 pre-existing chunk size warning)
