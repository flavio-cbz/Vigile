# Manual Integration Test — Node Management Refactor (Sprint 2026-06-19)

End-to-end validation of the new "add server / manage server" UX.
Run on a fresh `data/vigile.db` (delete it first if testing locally).

## Pre-requisites

- Master running: `cd /Users/flavio/Documents/Projets/Youcloud-API && PYTHONPATH="." python -m uvicorn master.main:app --host 127.0.0.1 --port 8000`
- Frontend running: `cd frontend && npm run dev`
- A Linux box with the worker binary to test full flow
- Browser open at `http://localhost:5173`

## Test 1 — Minimal add flow (no name, no group)

1. Login as `admin` / `admin`
2. Click `+` in the sidebar
3. Leave the name field empty, click "Générer la commande"
4. **Expected**: a curl command appears with a 30-min token, no "ip_prefix" mention
5. Run the curl on a Linux box
6. **Expected**:
   - Toast "Nouveau serveur" appears in the UI within 1s
   - The ServerConfigModal opens, name pre-filled with the worker's hostname
   - The new card on the ServersPage has a "NEW" badge
7. Type a name (e.g. "media-server") and a group (e.g. "prod"), click "Enregistrer"
8. **Expected**:
   - Toast "Serveur configuré"
   - Modal closes
   - The card's name updates to "media-server" and the group badge shows "prod"
   - The state is `CONNECTED` (green dot)

## Test 2 — Edit existing server via kebab

1. On the ServersPage, click the kebab menu (...) on the "media-server" card
2. Click "Renommer"
3. Change the name to "media-prod-01", click "Enregistrer"
4. **Expected**: card updates immediately, no reload

## Test 3 — Disable / re-enable

1. Click kebab on "media-prod-01", click "Désactiver"
2. **Expected**: card dims, shows a "Désactivé" badge
3. Click the "Désactivés" filter chip
4. **Expected**: only the disabled card shows
5. Click kebab → "Réactiver"
6. **Expected**: card is back in "Tous" / "En ligne" filters

## Test 4 — Regenerate token on PENDING

1. Click `+`, generate a new command, do NOT run the curl yet
2. On the ServersPage, find the new PENDING card
3. Open its kebab → click "Voir les détails" (or navigate manually)
4. In the "Settings" tab, click "Renvoyer la commande"
5. **Expected**: a new token + curl is displayed
6. Copy the new curl, run it on a different box
7. **Expected**: that box enrolls successfully
8. Try running the OLD curl
9. **Expected**: master rejects it with a token-already-consumed error (close 4401)

## Test 5 — Delete with confirmation

1. On the ServersPage, click kebab on "media-prod-01", click "Supprimer"
2. A modal appears: "Tapez 'media-prod-01' pour confirmer"
3. **Expected**: the "Supprimer" button stays disabled until you type the exact hostname
4. Type the hostname, click "Supprimer"
5. **Expected**: card disappears, toast "Serveur supprimé"

## Test 6 — Audit log

After running the above, navigate to `/audit` (or `/audit-log`):
- All actions are recorded: `GENERATE_JOIN_TOKEN`, `ENROLL_NODE`, `CONFIGURE_NODE`, `UPDATE_NODE`, `DISABLE_NODE`, `ENABLE_NODE`, `REGENERATE_JOIN_TOKEN`, `REVOKE_NODE`
- The hash chain remains intact: run `GET /api/admin/audit-verify` as admin → `{"valid": true}`

## Test 7 — Demo mode

1. Logout, login as `guest` / `guest`
2. Verify the new UI works in demo mode (the demo data layer in `master/api/demo_data.py` should short-circuit all new endpoints)

## Known limitations

- SSE auth uses a query-param token; in production, switch to a short-lived SSE-specific token (TODO, see plan §8.7)
- "NEW" badge uses server-computed `enrolled_recently`; 24h expiry is approximate
- The post-connexion modal does NOT auto-open if the operator is on a different page (toast still fires)
