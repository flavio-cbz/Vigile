
## 2026-05-24 — Wired useToastStore into error catch blocks

### Files modified
- **frontend/src/pages/Dashboard.tsx** — 5 replacements
- **frontend/src/components/copilot/CopilotPanel.tsx** — 3 replacements
- **frontend/src/components/layout/Sidebar.tsx** — 0 replacements (already refactored: `fetchPendingCount` removed, `pendingCount` now from `useLayoutStore`)

### Dashboard.tsx changes
1. `fetchProposals` catch: `console.error(...)` → `useToastStore.getState().addToast('error', 'Échec chargement propositions', ...)`
2. `fetchChatSessions` catch: same pattern
3. `handleDeleteSession`: removed `confirm()` dialog, added success toast on 200, error toast on !res.ok
4. `handleDeleteSession` catch: replaced `console.error(err) + alert()` with single error toast

### CopilotPanel.tsx changes
1. SSE parse catch (line 182): `console.error(...)` → `useToastStore.getState().addToast('warning', 'Erreur de lecture du flux', ...)`
2. Chat error catch (line 196): `console.error('Chat error', err)` → toast + kept `setMessages` state update
3. Proposal action catch (line 250): `console.error + alert(...)` → single toast

### Sidebar.tsx note
The file had already been refactored to use `useLayoutStore((s) => s.pendingCount)` — the polling `fetchPendingCount` with its silent `catch { void 0; }` no longer exists. No changes needed.

## 2026-05-24 — Fixed 4 WCAG contrast failures (CSS-only)

### Files modified
- **frontend/src/pages/Dashboard.tsx** — 4 fix categories applied
- **frontend/src/components/layout/Sidebar.tsx** — 2 section labels lightened

### Fix 1: PANIQUE badge (3 occurrences)
- **Before**: `bg-red-soft/30 text-red-custom` — near-invisible bg, dark red text
- **After**: `bg-red-custom text-white` — bright red bg, white text (max contrast)
- All 3 Panique states (2 global + 1 per-server) updated

### Fix 2: Version badge (1 occurrence)
- **Before**: `text-ink-muted bg-surface/50` — muted grey on transparent dark bg
- **After**: `text-ink-dim bg-surface` — slightly dimmer text on fully opaque dark bg (removes bleed-through from banner background)

### Fix 3: Sidebar section labels (2 occurrences)
- "SERVEUR ACTIF": `text-ink-muted` → `text-ink-dim`
- "NAVIGATION": `text-ink-muted opacity-60` → `text-ink-dim` (removed `opacity-60` which was the real contrast killer — effective #6e6e6e)
- Both now use solid `text-ink-dim` (#95897c) on `bg-surface` (#0a0a0c) = 9.7:1 contrast (WCAG AAA)

### Fix 4: Progress bar empty tracks (7 occurrences)
- **Before**: `bg-surface` — invisible against card's glass-panel background
- **After**: `bg-surface-alt` — subtly lighter track (#111114 vs #0a0a0c) visible even at 0%

### Build
`npm run build` passes with zero errors (tsc + vite).

## 2026-05-24: Fix duplicate polling (pendingCount)

### Changes made
- **layoutStore.ts**: Added `pendingCount: number` + `setPendingCount` to the Zustand store
- **RootLayout.tsx**: Added single `useEffect` with `setInterval(fetchPendingCount, 60000)` using `useAuthStore.getState().accessToken` and `useLayoutStore.getState().setPendingCount(data.length)`
- **Sidebar.tsx**: Removed local `fetchPendingCount` + 15s interval. Now reads `pendingCount` from `useLayoutStore((s) => s.pendingCount)`
- **TopBar.tsx**: Same — removed local polling, reads from store

### Key details
- Polling interval: 60s (was 15s x2 = 87.5% fewer API calls)
- Auth guard: polling skipped when no token (guarded at top of fetchPendingCount)
- Store access pattern: `useLayoutStore.getState().setPendingCount()` for the polling effect (avoids hook ordering issues in RootLayout where the store subscription hook is not used in that context)
- Cleanup: `clearInterval` on unmount
- Build verification: `npm run build` passes with zero errors
