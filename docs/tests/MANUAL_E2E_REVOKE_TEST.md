# E2E: Node Deletion via Admin UI

**Last verified:** 2026-06-24
**Test file:** `scripts/test_revoke_node_e2e.py`
**Status:** PASSING (last run: 1/1 clean run)

## What it validates

The full UI flow of hard-deleting a node as an admin:

1. **Auth bypass** — admin tokens injected into `localStorage` before the SPA mounts, so the zustand `useAuthStore` hydrates as authenticated (avoids the flaky Playwright login form submit).
2. **Add node** — clicks the "AJOUTER SERVEUR" button in the **Sidebar** (not the ServersPage header) to open `AddNodeModal`, fills the name, submits, closes the modal.
3. **Card visibility** — waits for the new PENDING card to appear on `/servers`.
4. **Kebab menu** — clicks the kebab on the new card (`aria-label="Plus d'actions"`), then "Supprimer" in the dropdown.
5. **Type-to-confirm** — types the node's `name` (since `hostname` is `null` for a PENDING node) into the confirm input.
6. **Delete** — clicks the "Révoquer" submit button.
7. **Verify** — card disappears from the UI, no "Node not found" toast, the node is **completely removed from the API** (hard delete, not soft state).

## Hard-delete semantics

The DELETE endpoint performs a real `DELETE FROM nodes WHERE id = ?` instead of transitioning to a `REVOKED` state. The FK `ON DELETE CASCADE` clauses on `join_tokens`, `worker_tokens`, `metrics_snapshots`, `action_proposals` automatically clean up child rows. The `chat_sessions.node_id` is set to NULL via `ON DELETE SET NULL`. The `audit_log` keeps a `NODE_DELETED` entry forever (it stores `node_id` as plain TEXT, no FK).

| Endpoint / Behavior | Response |
|---|---|
| `DELETE /api/nodes/{id}` (admin) | `204 No Content` |
| `DELETE /api/nodes/{id}` (operator) | `403 Forbidden` |
| `DELETE /api/nodes/{id}` (already deleted) | `404 Not Found` |
| `GET /api/nodes/{id}` (after delete) | `404 Not Found` |
| `GET /api/nodes` (after delete) | Node not in list |
| `audit_log` entries | `NODE_DELETED` row kept (search by `node_id` still works) |
| SSE events emitted | `node.state` (with `new_state=REVOKED` for back-compat) + `node.deleted` |

## How to run

### Prerequisites

- Backend running on `http://127.0.0.1:8000`
- Frontend dev server running on `http://127.0.0.1:5173` (Vite)
- Playwright + chromium installed in the venv:
  ```bash
  .venv/bin/python -m pip install playwright
  .venv/bin/playwright install chromium
  ```
- Default admin credentials `admin`/`admin` (seeded in dev)

### Run

```bash
# From project root, with both servers up:
.venv/bin/python scripts/test_revoke_node_e2e.py
```

### Exit codes

- `0` = PASS (all assertions hold)
- `1` = FAIL (see stdout for which assertion failed)

Screenshots are written to `/tmp/vigile_*.png` for visual debugging.

## Why these design choices

### Auth bypass via `localStorage` + `add_init_script`

The Vigile SPA uses **zustand** for auth state, with a factory that reads `localStorage` synchronously during `create()`. By calling `context.add_init_script` with the token serialization, the value is set in `localStorage` **before the page's JS runs** — so zustand's initial state already contains the admin user and `isAuthenticated=true`. This is more reliable than:
- Submitting the login form (Playwright's `fill` + `press("Enter")` was timing out on the Vigile form),
- Waiting for the SPA to mount and then `setItem`ing the token (race condition with the initial `getStoredAuth()` call).

### `127.0.0.1` instead of `localhost`

Forces IPv4 to avoid potential `::1` resolution issues on macOS where some Python urllib versions prefer IPv6 first and may hit a stale `::1` listener.

### Sidebar `+` button, not ServersPage header

There is no `+` button in `ServersPage` — the `AddNodeModal` is triggered exclusively from the `Sidebar` (in `renderServerSelector()` at two locations: single-server shortcut `title="Ajouter un serveur"`, and the dropdown footer `AJOUTER SERVEUR`).

### Type the `name`, not the hostname

`ConfirmDeleteModal`'s `confirmWord` is `node.hostname || node.name` (set in `ServersPage.tsx` line 335). For a PENDING node, `hostname` is `null` — so the test must type the `name` it just submitted.

### Click "Révoquer", not "Supprimer"

The kebab menu item is labeled "Supprimer" (i18n-friendly, not destructive-sounding), but the confirm modal's submit button is labeled with `confirmLabel="Révoquer"`. The test targets the submit button explicitly via `button[type="submit"]:has-text("Révoquer")`.

## Bugs discovered & fixed during this test

| Bug | File | Fix |
|-----|------|-----|
| `ip_prefix: null` (frontend) sent to API expecting `str` → 422 | `frontend/src/components/modals/AddNodeModal.tsx:45` | Changed `ip_prefix: ipPrefix \|\| null` to `ip_prefix: ipPrefix` (empty string is valid per Pydantic pattern `^$\|^[\d.]+$`) |
| `[object Object]` error display for 422 responses | `frontend/src/hooks/useApi.ts:130` | Known minor — `parsed.detail` is an array, displayed as toString. Doesn't affect the delete flow. |
| REVOKED nodes remained visible in API list (state-based soft delete) | `master/core/node_manager.py:437` | Replaced `revoke_node()` (UPDATE state=REVOKED) with `delete_node()` (DELETE FROM nodes) so the row is fully removed. The `NodeState.REVOKED` enum value is kept for back-compat with any pre-migration rows. |

## Out of scope (deliberately)

- **Login form itself** — bypassed for stability. The form's behavior is unit-tested elsewhere.
- **Worker-side enrollment** — this test only validates the admin UI + backend delete endpoint, not the worker's reaction.
- **SSE node state events** — not asserted (only the post-refresh card state is checked).
- **Demo mode** — the test targets the real backend with default `admin`/`admin`.

## Adding a new E2E test

1. Copy `scripts/test_revoke_node_e2e.py` as a template
2. Use the same auth bypass pattern (`add_init_script` + localStorage)
3. Target `127.0.0.1` explicitly
4. Use `aria-label` selectors when available; fall back to text content; avoid SVG class selectors (lucide-react class names are version-dependent)
5. For type-to-confirm modals, type the `name` (never the `hostname` for a PENDING node)
6. Write screenshots to `/tmp/vigile_<step>_<description>.png` for debugging
