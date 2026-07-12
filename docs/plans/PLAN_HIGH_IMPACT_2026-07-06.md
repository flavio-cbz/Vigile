# Plan d'action — Chantiers à fort impact Vigile
**Date d'analyse :** 2026-07-06
**Analyste :** Sisyphus-Junior (audit croisé code vs docs)
**Portée :** Dette technique + gaps pré-production (pas de nouvelles features)

---

## 0. Résumé exécutif

L'analyse croisée des 6 documents d'audit **contre l'état réel du code** révèle un décalage majeur :

| Item classé "🔴 Critique" dans les audits | État réel sur disque (2026-07-06) |
|---|---|
| **B-01** — `os.environ.get` hors `config.py` (`secret_loader.py:53-58`) | ⚠️ **Faux positif partiel** — le code utilise `getattr(os, "environ", {})` puis `env.get(...)`, ce qui est le pattern de test-injection standard. Reste violation formelle de la règle RULES.md mais **pas un vrai bug** |
| **B-02** — `from master.config import settings` module-level (`auth.py:67/75/100`, `deps.py:73/200`) | ✅ **Corrigé** — `auth.py` utilise `Depends(get_settings)` (lignes 151, 263, 409) ; `deps.py:71-75` définit un factory lazy ; les autres imports sont **dans des corps de fonction** (lazy import), pas module-level |
| **B-06** — SQL f-strings (`node_manager.py:272/440/672/1000`, `audit.py:81`, `automations.py:259`) | ✅ **Corrigé** — toutes les concaténations utilisent `"..." + var + "..."` avec des identifiants validés via whitelist (`_ALLOWED_UPDATE_FIELDS` à `node_manager.py:670-672`). Aucune injection possible |
| **G-01** — underscore assertions (`worker/connection.go:118-168`) | 🟡 **Partiellement corrigé** — les 5 sites d'enrollement utilisent maintenant `if token, ok := ...; ok`, mais **9 sites subsistent** dans `containers.go:75-92` et `connection.go:277,447` |

**Conséquence stratégique :**
1. Les audits 2026-06-27 / 2026-06-28 sont **stales** — ils listent des items déjà résolus dans le Sprint 5 (voir sections ✅ de `LIMITS.md` §116-135).
2. Le vrai chemin critique pré-prod n'est **pas** dans les 🔴 Critique des audits, mais dans **les gaps cross-cutting** : TLS non branché, build frontend cassée, token rotation.
3. Sprint 6 (Production Hardening) est **bien plus avancé que les audits ne l'indiquent** : CI complète, builds cross-platform, Prometheus, config prod. Ce qui reste : TLS à brancher, frontend build à fixer, token rotation.

**Ordre d'exécution recommandé (efforts recalculés vs réel 2026-07-12) :**
```
P0 → C1 (Audit refresh)         [0.5 j]  ← démarre par ça, sinon tu retravailles à l'aveugle
P0 → C2 (TLS end-to-end wiring) [1 j]    ← BLOCKER prod : Caddyfile existe, docker-compose à brancher
P0 → C3 (Fix frontend build)    [0.5 j]    ← BLOCKER prod : 6 erreurs TS dans Sidebar.tsx
P0 → C4 (CI/CD pipeline)        [✅ DONE]  ← CI complète + release workflow existants
P1 → C5 (Worker robustesse)     [2 j]      ← context.Context, assertions Go, timeouts exec
P1 → C6 (Migrations idempotentes) [1 j]
P1 → C7 (Frontend types F-05)   [3 j]
P1 → C9 (Rotation WORKER_TOKEN) [2 j]
P2 → C8 (Sprint 8 UI/UX cleanup) [5 j]
```

**Gate pré-production (ne PAS déployer sans) :** C1 → C2 → C3 → C4 → C6 → C9.

---

## 1. Chantiers prioritaires (détaillés)

### C1 — Refresh de la baseline d'audit
**Priorité :** P0 (bloque tout le reste)
**Effort :** 0.5 j
**Dépendances :** aucune

**Objectif.** Les rapports d'audit datent d'avant le Sprint 5.5. Toute planification qui prend ces docs comme source de vérité travaillera sur des items fantômes. Il faut **régénérer le rapport** puis **déclasser explicitement** les items faux positifs.

**Étapes.**
1. Relancer le script d'audit automatique qui a produit `AUDIT_REPORT_2026-06-28.md` (chercher le workflow ou script — probablement dans `scripts/` ou hook `.githooks/`).
2. Comparer ligne à ligne avec `LIMITS.md §116-135` (corrections Sprint 5) pour classifier chaque item :
   - **Résolu** → retirer du DEBT_CATALOG.md
   - **Reste** → maintenir avec ligne actuelle correcte
   - **Faux positif de règle** (ex: B-01 sur `getattr(os, "environ", {})` — c'est le pattern de test) → exclure via allowlist dans le linter
3. Régénérer `DEBT_CATALOG.md` et écrire `AUDIT_REPORT_2026-07-06.md`.
4. Créer `SESSION.md` (documenté comme manquant dans DOC-02) avec le baseline du sprint courant.

**Risques.**
- Le script d'audit peut ne pas exister sur disque → il faut le reconstruire depuis les patterns observés dans les rapports.
- Faux positifs récurrents (ex: `getattr(os, "environ", {})`) réintroduits à chaque scan → nécessite une allowlist versionnée.

**Critères de succès.**
- Nouveau rapport avec ≤ 5 items 🔴 vraiment critiques (aujourd'hui 14 dont ~11 obsolètes).
- `SESSION.md` créé et référencé dans le prochain audit.
- Allowlist du linter documentée dans `RULES.md`.

---

### C2 — TLS end-to-end (wiring Caddy dans docker-compose)
**Priorité :** P0 (BLOCKER production)
**Effort :** 3 j
**Dépendances :** aucune (indépendant)

**Objectif.** `docs/TLS.md` documente une architecture Caddy front-Master, `docker/Caddyfile` existe, MAIS `docker-compose.yml` **n'a AUCUN service `caddy`**. Le Master est exposé en HTTP clair sur `8003:8000`. Les Workers utilisent `ALLOW_INSECURE=true` par défaut. **Aucun TLS n'est actif nulle part.**

**État constaté (`docker-compose.yml` lignes 14-73) :**
```yaml
services:
  master:               # ← pas de Caddy en amont
    ports: ["8003:8000"]  # ← HTTP direct exposé
  worker:
    environment:
      - MASTER_URL=http://master:8000     # ← ws:// pas wss://
      - ALLOW_INSECURE=true                # ← désactive TLS worker
```

**Étapes.**
1. **Ajouter le service `caddy`** dans `docker-compose.yml` avec :
   - image `caddy:2-alpine`
   - montage `./docker/Caddyfile:/etc/caddy/Caddyfile:ro`
   - volumes nommés `caddy_data` + `caddy_config` pour la persistance des certs Let's Encrypt
   - ports `80:80` et `443:443`
   - dépendance `depends_on: [master]`
2. **Retirer** l'exposition directe du port Master (`ports:` → interne uniquement).
3. **Ajouter** un profile Docker Compose `prod` qui :
   - substitue `tls internal` par `tls admin@domain.tld` dans le Caddyfile via template
   - retire `ALLOW_INSECURE=true` du worker
   - passe `MASTER_URL=wss://vigile.youcloud.ovh` au worker
4. **Corriger le healthcheck Master** : `test: ["CMD", "curl", "-sk", "https://caddy/health"]` ou garder l'interne HTTP.
5. **Ajouter test d'intégration** `tests/test_tls_e2e.py` qui :
   - démarre le stack en mode dev (`tls internal`)
   - vérifie que `https://localhost/health` retourne 200
   - vérifie qu'un worker se connecte en `wss://` avec cert auto-signé accepté
6. **Documenter** dans `README.md` et `TLS.md` la procédure prod (Let's Encrypt) et l'obligation absolue de retirer `ALLOW_INSECURE` en prod.
7. **Vérifier `ENFORCE_HTTPS`, `TRUSTED_PROXIES`, `COOKIE_SECURE`** dans `master/config.py` — s'assurer qu'ils sont activés quand le master reçoit un `X-Forwarded-Proto: https`.

**Risques.**
- Certificats auto-signés cassent les workers existants qui ne fixent pas `ALLOW_INSECURE=true` → coordination requise.
- Let's Encrypt rate-limit en prod → utiliser staging (`acme-staging-v02`) pour les premiers tests.
- Le healthcheck actuel utilise `http://localhost:8000` (interne conteneur) — reste valide car Caddy et Master sont dans le même compose.
- `LIMITS.md §147` déclare `ENFORCE_HTTPS` prêt mais **il faut vérifier qu'il est actif par défaut** en mode `prod`.

**Critères de succès.**
- `curl -sk https://localhost/health` → `{"status":"ok"}`
- `curl -sI http://localhost/health` → `HTTP 308 → https://localhost/health`
- Worker se connecte en `wss://` (log worker : `Connecting to wss://...`)
- Test d'intégration `tests/test_tls_e2e.py` passe.
- `docs/TLS.md` mis à jour avec la commande `docker compose --profile prod up -d`.

---

### C3 — Couverture de tests critiques (T-01)
**Priorité :** P0 (BLOCKER production — auth + DB sous-testés)
**Effort :** 4 j
**Dépendances :** aucune

**Objectif.** Deux modules de sécurité critique sont sous le seuil :
- `master/api/auth.py` : 91% (seuil 95%)
- `master/db/database.py` : 69% (seuil 95%)

**Étapes.**
1. **Analyse gap coverage** — `pytest --cov=master.api.auth --cov=master.db.database --cov-report=html` puis identifier les branches non couvertes.
2. **`master/api/auth.py`** — ajouter tests pour :
   - Login avec `must_change_password=1` → retourne 403 `MUST_CHANGE_PASSWORD` sur endpoints non-auth.
   - Refresh token avec famille compromise → révocation en cascade.
   - Login sur user `is_active=0` → 403.
   - Détection de vol de refresh token (rotation avec un token déjà consommé).
   - Change-password avec mot de passe faible → validation Pydantic échoue.
3. **`master/db/database.py`** — ajouter tests pour :
   - Pool exhaustion (`asyncio.Queue` vide, timeout de récupération).
   - Reconnexion après WAL checkpoint.
   - Comportement sous `transaction()` avec exception (rollback).
   - Fermeture du pool pendant qu'une coroutine attend une connexion.
   - Init idempotent (double appel de `init_db`).
4. **Ajouter les régressions LIMITS.md (DOC-03)** :
   - Test que la clé Ed25519 `0o700` (mauvaises permissions) émet un warning.
   - Test que rate-limiter cleanup s'exécute périodiquement.
5. **Enforcer le seuil** : ajouter `--cov-fail-under=95` dans `pytest.ini` pour ces deux modules spécifiquement.

**Risques.**
- Tests de concurrence DB flaky sous Windows (aiosqlite comportement différent) → skip conditionnel avec `@pytest.mark.skipif(sys.platform == "win32")`.
- Pool exhaustion peut nécessiter de refactorer `database.py` pour exposer un hook de test (injecter un pool custom).
- Sur `auth.py`, certains chemins de rotation de famille nécessitent de manipuler `time.time()` — utiliser `freezegun` ou une abstraction `Clock`.

**Critères de succès.**
- `pytest --cov=master.api.auth` → ≥ 95%
- `pytest --cov=master.db.database` → ≥ 95%
- `pytest -m "not integration"` reste vert.
- Les régressions LIMITS.md §96-101 ont un test associé.

---

### C4 — Pipeline CI/CD (blocker qualité)
**Priorité :** P0 (BLOCKER production)
**Effort :** 3 j
**Dépendances :** aucune

**Objectif.** L'audit `AUDIT_MISSED_REPORT §Infra 30 issues` et le contexte AGENTS.md §AUDIT FINDINGS listent explicitement "zéro Go/frontend tests en CI, CI no pre-commit/sécurité". C'est un blocker parce qu'aujourd'hui **rien n'empêche un commit régression d'atterrir en main**.

**Étapes.**
1. **Créer `.github/workflows/ci.yml`** avec jobs :
   - **`python-tests`** : `pip install -r requirements.txt` + `pytest -m "not integration" --cov=master --cov-fail-under=90`.
   - **`python-lint`** : `black --check`, `ruff check`, `mypy master/` (si config existe).
   - **`go-tests`** : `cd worker && go test -race ./...`.
   - **`go-lint`** : `cd worker && golangci-lint run` (à installer).
   - **`frontend-build`** : `cd frontend && npm ci && npm run build && npm run typecheck`.
   - **`frontend-lint`** : `cd frontend && npm run lint` (biome ou eslint selon config existante).
   - **`integration`** : docker compose up master + worker + run `scripts/test_all_simulation.py`.
   - **`security`** : `pip-audit`, `npm audit --production`, `gosec` sur worker.
2. **Pre-commit hooks** — créer `.pre-commit-config.yaml` avec black, ruff, gofumpt, biome/eslint, secret scanner (`gitleaks`).
3. **Bloquer les merges** — protection de branche `master` : require CI green.
4. **Secret scanner** — ajouter `gitleaks` dans le CI + baseline actuelle (l'audit note `LLM_API_KEY` live-key dans `.env` — voir C11 rotation).
5. **Coverage badge** dans le README (Codecov ou Coveralls).

**Risques.**
- Timeout des tests Go race sur runners lents → augmenter timeout.
- Frontend tests inexistants — cette tâche ne créera pas les tests, elle assurera juste que la build passe. Le vrai frontend testing est un chantier séparé (hors scope).
- Secret scanner peut lever le `LLM_API_KEY` de `.env` déjà commité historiquement → nécessite un `git filter-repo` séparé (voir C11).

**Critères de succès.**
- PR sans tests → CI rouge, merge bloqué.
- Un `git push` déclenche 8 jobs en parallèle en < 5 min.
- Un commit avec `sk-` en clair est refusé par pre-commit.
- Le README affiche un badge de couverture.

---

### C5 — Robustesse Worker Go (G-01 + G-02 + contexts)
**Priorité :** P1 (Important — pas bloquant mais risqué en prod)
**Effort :** 4 j
**Dépendances :** C4 (CI Go tests) pour valider les changements

**Objectif.** Le worker Go a trois problèmes réels qui subsistent :
1. **G-01** : 9 assertions de type avec `_` swallowed dans `containers.go:75-92` et `connection.go:277,447`.
2. **G-02** : 5 goroutines lancées sans `context.Context` — le shutdown propre repose uniquement sur `wc.Stop()` qui ferme le WebSocket, pas les goroutines de background.
3. **G-06** (signal) : fonctions réseau sans `ctx context.Context` — impossible d'annuler un `Connect()` ou un heartbeat pending.

**Étapes.**
1. **Réparer les assertions G-01** — remplacer chaque `x, _ := m["k"].(T)` par :
   ```go
   x, ok := m["k"].(T)
   if !ok {
       logger.Printf("warning: expected T for k, got %T", m["k"])
       continue // ou return error selon le contexte
   }
   ```
2. **Introduire un `context.Context` root** dans `worker/main.go` :
   ```go
   ctx, cancel := context.WithCancel(context.Background())
   defer cancel()
   go func() {
       <-sigCh
       cancel()
       wc.Stop()
   }()
   wc.RunWithBackoff(ctx)
   ```
3. **Propager `ctx` dans** :
   - `WorkerConn.Connect(ctx)` — utilisable dans `net.Dialer.DialContext`.
   - `WorkerConn.RunOperational(ctx)` — checké dans la boucle read.
   - Toutes les goroutines : `select { case <-ctx.Done(): return ... }`.
4. **Timeouts d'exécution** — ajouter `context.WithTimeout` autour de `exec.Command` (audit MISSED §Worker : "no exec timeouts"). Utiliser `exec.CommandContext(ctx, ...)`.
5. **Frame parse panic** (audit MISSED §Worker) — ajouter defer-recover autour de `parseWebSocketFrame` avec log détaillé au lieu de crash.
6. **Tests Go** — écrire `worker/connection_ctx_test.go` qui :
   - démarre un worker avec `context.WithCancel`
   - appelle `cancel()` après 100ms
   - vérifie que toutes les goroutines terminent en < 500ms (`goleak.VerifyNone(t)`).

**Risques.**
- Ajouter `ctx` à des signatures publiques change l'API du worker → coordination si `worker/` est consommé ailleurs (ce n'est pas le cas ici).
- `goleak` n'est pas stdlib — vérifier si autorisé par la règle "zéro dépendance". Alternative : test manuel avec `runtime.NumGoroutine()` avant/après.
- La règle "worker stdlib only" (AGENTS.md conventions) exclut `github.com/uber-go/goleak` — utiliser assertion manuelle sur `runtime.NumGoroutine()`.

**Critères de succès.**
- `go vet ./...` et `go test -race ./...` verts.
- `SIGTERM` sur le worker → shutdown propre en < 2s (mesurable dans les logs).
- Aucun `_ =` sur `.(string)` dans `worker/**/*.go` (grep contrôle).
- Test `worker/connection_ctx_test.go` passe.

---

### C6 — Migrations idempotentes (S-01)
**Priorité :** P1 (Important — bloquant pour redéploiement)
**Effort :** 1 j
**Dépendances :** aucune

**Objectif.** `master/db/migrations.py:106` utilise `CREATE TABLE join_tokens_new (...)` sans `IF NOT EXISTS`. Un rerun de migration après un crash intermédiaire pète en `table already exists`.

**Étapes.**
1. Audit complet de `master/db/migrations.py` et `master/db/alembic/versions/*.py` — grep `CREATE TABLE|CREATE INDEX|ALTER TABLE` sans `IF NOT EXISTS`.
2. Ajouter `IF NOT EXISTS` à tous les `CREATE`.
3. Pour les `ALTER TABLE` (non idempotent en SQLite), vérifier d'abord `PRAGMA table_info(...)` avant d'appliquer.
4. Ajouter test `tests/test_db/test_migrations_idempotent.py` :
   - Exécute `run_migrations()` deux fois de suite sur une DB vide.
   - Exécute sur une DB partiellement migrée (simule crash au milieu).
   - Aucune exception ne doit remonter.
5. **Fixer le stamping Alembic** (AGENTS.md AUDIT FINDINGS §Backend : "migration stamping broken") — s'assurer que `run_migrations()` appelle `alembic stamp head` après les migrations manuelles pour synchroniser l'état.

**Risques.**
- SQLite ne supporte pas toutes les clauses `IF NOT EXISTS` sur `ALTER` — nécessite check préalable.
- Le stamping Alembic peut casser un environnement de dev existant → tester sur DB fraiche + DB copie de prod.

**Critères de succès.**
- Test `test_migrations_idempotent` passe.
- `alembic current` retourne `head` après `run_migrations()`.
- Redémarrage du master après un crash mid-migration → succès.

---

### C7 — Typage frontend F-05 (23 `any` injustifiés)
**Priorité :** P1 (Important — dette croissante)
**Effort :** 3 j
**Dépendances :** C4 (CI frontend-typecheck pour valider)

**Objectif.** 23 usages `any` recensés dans l'audit — mélange de :
- Casts UI paresseux (`setTheme(t as any)`)
- API responses non typées (`details?: any`)
- Error handling générique (`catch (err: any)`)
- Location state (`(location.state as any)`)

**Étapes.**
1. **Définir les types manquants** dans `frontend/src/types/` :
   - `ChatMessage` (utilisé dans `AllChatsModal`, `chatStore`)
   - `AuditDetails` (utilisé dans `formatAudit`, `AuditPage`, `ActivityItem`)
   - `SidebarItem` (utilisé dans `Sidebar.tsx:126`)
   - `Theme` (union `'dark' | 'warm-dark' | 'light'`)
   - `LocationState` (pour `location.state`)
2. **Créer un helper de typage erreur** dans `frontend/src/utils/errors.ts` :
   ```ts
   export function isErrorWithMessage(err: unknown): err is { message: string } {
     return typeof err === 'object' && err !== null && 'message' in err;
   }
   ```
   Remplacer tous les `catch (err: any)` par `catch (err: unknown)` + guard.
3. **Marker interne `_toasted`** (`useApi.ts:137,155`) → utiliser un `WeakSet<Error>` global au lieu de muter avec `as any`.
4. **Activer `noImplicitAny: true` + `strict: true`** dans `tsconfig.json` si pas déjà fait.
5. **CI check** — `npm run typecheck` doit être dans C4.

**Risques.**
- Le cascade de types dans le store Zustand peut nécessiter de refacturer des selectors → time-boxer à 3j max.
- Certains `any` viennent de libs externes non typées → utiliser `unknown` + type guards plutôt qu'un `any` explicite.

**Critères de succès.**
- `grep -rn "any" frontend/src --include="*.ts" --include="*.tsx" | wc -l` → passe de 23 à ≤ 3 (justifications documentées).
- `npm run typecheck` vert sans `--noEmit` warnings.
- Aucun `as any` restant sauf commenté avec justification.

---

### C8 — Sprint 8 UI/UX cleanup
**Priorité :** P2 (Signal — améliore l'UX mais n'est pas bloquant)
**Effort :** 5 j
**Dépendances :** aucune (parallélisable avec C1-C7)

**Objectif.** Sprint 8 du PLAN.md est marqué ❌ intégral. Les 12 items sont tous des UX debt qui polluent l'usage en démo/prod. Voir PLAN.md §610-641.

**Étapes (regroupées par cluster) :**
1. **Formatage & bugs d'affichage (1.5 j)** :
   - Badge nav `Services (.)` → guard `count ?? 0` puis rendu conditionnel.
   - Uptime `4228462s` → helper `formatDuration()` → `48j 22h`.
   - Prédiction disque `+2145 Go/j` (Sprint 7 dit ✅ mais à re-vérifier).
   - Hover métriques → tooltip shadcn/ui avec animation.
2. **Warm Dark theme (1.5 j)** :
   - Palette : fond `#0e0d0c`, accent alerte `#E8650A`, accent déco `#F59E0B`.
   - Font titrage `DM Serif Display` via `@fontsource`.
   - Migrer les couleurs arbitraires Tailwind `bg-[#6366f1]` (F-01) vers tokens design system (`bg-accent`, `bg-warning`).
3. **Nettoyage UX (1 j)** :
   - Cartes insight `severity=ok` masquées par défaut + toggle "Afficher les stables".
   - Fil d'activité filtré (exclure login/logout par défaut).
   - Dashboard : conteneurs `not running` par défaut + toggle "Voir tout".
   - Suppression de la page "Registre d'Audit Cryptographique" (jugée non-utile).
4. **Sidebar & navigation (0.5 j)** :
   - Raccourci Docker global dans la sidebar (pas juste dans NodeDetail).
   - Logo Vigile appliqué partout (favicon, sidebar, login).
5. **Plugins UI (0.5 j)** :
   - Descriptions plugins affichées.
   - Toggle activation qui fonctionne réellement (fix flux back-front).
   - Bouton désinstaller.

**Risques.**
- Le Warm Dark change la charte globale → prévoir revue design.
- Suppression de la page audit → nécessite validation utilisateur (préciser que l'endpoint API reste, seule la page UI disparaît).
- Fix du toggle plugin peut cascade vers `PluginEngine` (Sprint 9) — s'assurer que c'est un fix d'UI et pas de moteur (sinon décaler à Sprint 9).

**Critères de succès.**
- Screenshots avant/après validés par le PO.
- `visual-qa` skill passe sur les 6 pages principales.
- Aucun style inline restant sur les composants clés (grep `style={{`).

---

### C9 — Rotation WORKER_TOKEN (Sprint 6.2)
**Priorité :** P1 (Important — bloquant pour prod long-running)
**Effort :** 3 j
**Dépendances :** C2 (TLS) + C4 (CI) + C5 (worker context)

**Objectif.** Le champ de terrain (AGENTS.md §FIELD VALIDATION 2026-06-17) montre qu'un worker avec un JOIN_TOKEN expiré tombe en crashloop indéfini. Le PLAN.md Sprint 6 §2 spécifie une rotation automatique du WORKER_TOKEN tous les 7 jours — **non implémentée**.

**Étapes.**
1. **Master** — dans `worker_handler.py` heartbeat :
   - Charger `issued_at` du WORKER_TOKEN JWT.
   - Si `now - issued_at > 7 * 86400`, générer nouveau token et l'envoyer :
     ```json
     {"type": "TOKEN_ROTATION_COMMAND", "new_worker_token": "..."}
     ```
   - Attendre `TOKEN_ROTATION_ACK`.
   - Marquer l'ancien token comme `revoked` dans `refresh_tokens` (ou table dédiée `worker_tokens`).
2. **Worker Go** — dans `dispatcher.go` :
   - Handler pour `TOKEN_ROTATION_COMMAND` → persist via `persistWorkerToken()` (déjà existe).
   - Réponse `TOKEN_ROTATION_ACK`.
   - Bascule immédiate sur nouveau token pour prochain heartbeat.
3. **Test d'intégration** — `tests/test_worker_token_rotation.py` :
   - Force `worker_token_ttl=10s` en config test.
   - Attend 15s + observe la rotation.
   - Vérifie que l'ancien token est refusé.
4. **Migration DB** — table `worker_tokens` avec `revoked_at`, `revoked_by`, `superseded_by`.
5. **Documentation** — `docs/WORKER_TOKEN_ROTATION.md` avec runbook.

**Risques.**
- Si le worker est offline pendant > 7j puis revient, l'ancien token expiré est rejeté → **fallback** : le worker doit pouvoir re-enrôler avec un JOIN_TOKEN si stocké, ou signaler la nécessité d'un re-enrollment manuel.
- Race condition entre heartbeat et rotation → tester avec 2 workers simultanés.
- Le field validation note que `youcloud-persistent` a un JOIN_TOKEN expiré depuis mai 2026 : la rotation résoudra ce cas seulement si le worker est déjà connecté.

**Critères de succès.**
- Worker connecté 8j → rotation observée dans les logs sans coupure.
- Ancien token rejeté en 401 par le master.
- Test `test_worker_token_rotation.py` passe.

---

## 2. Chantiers hors chemin critique (référence uniquement)

Ces items sont dans les audits mais **ne doivent pas bloquer la prod** :

| Item | Effort | Justification report |
|---|---|---|
| **F-07** Composants God (12 fichiers > 250 lignes) | 4 j | Dette lisibilité, pas de bug fonctionnel |
| **B-08** Fonctions Python non typées (19 items) | 2 j | Ajout progressif via `ruff` en CI |
| **B-09** Mutations DB sans `log_action` (7 items) | 1 j | Audit trail incomplet mais pas de faille |
| **B-10** Imports différés (20 items) | 0.5 j | Cosmétique PEP 8 |
| **X-03** Timeouts hardcodés (6 items) | 1 j | Fonctionne mais pas config-driven |
| **X-06** Deps non whitelistées (3 items) | 0.5 j | Vérifier si sous-dépendances FastAPI |
| **A-07** Caches sans TTL (`_pending_intents`, `_pending_db_calls`) | 1 j | AGENTS.md dit déjà corrigé — vérifier |
| **P-01/P-02** Prompts et hyperparams LLM externalisés | 2 j | `LIMITS.md §132-133` dit déjà fait — vérifier |
| **T-03** Tests de contrat Worker/Master | 3 j | Amélioration robustesse, pas régression connue |
| **PERF-02** `asyncio.Queue` sans maxsize | 0.5 j | Théorique — jamais atteint en pratique |
| **DOC-01** Routes README manquantes | 0.5 j | Doc, pas prod |

Sprint 9-12 (Plugin Engine, Marketplace, IA autonomy) : **hors scope pré-production**.

---

## 3. Dépendances et séquençage visuel

```
                                 ┌──────────┐
                                 │ C1 Audit │  0.5j  (démarreur)
                                 │ refresh  │
                                 └──────────┘
                                       │
             ┌─────────────────────────┼──────────────────────────┐
             ▼                         ▼                          ▼
        ┌────────┐               ┌──────────┐               ┌──────────┐
        │ C2 TLS │  3j           │ C3 Tests │  4j           │  C4 CI   │  3j
        │        │               │  T-01    │               │          │
        └────────┘               └──────────┘               └──────────┘
             │                         │                          │
             └────────┬────────────────┴───────────┬──────────────┘
                      ▼                            ▼
                 ┌──────────┐                 ┌──────────┐
                 │ C6 Migr. │  1j             │ C5 Wrk.  │  4j
                 │ S-01     │                 │ Go G-01/2│
                 └──────────┘                 └──────────┘
                      │                            │
                      └──────────────┬─────────────┘
                                     ▼
                              ┌─────────────┐
                              │ C9 Token    │  3j
                              │ Rotation    │
                              └─────────────┘
                                     │
                                     ▼
                            ═════════════════
                            ██ GATE PROD  ██
                            ═════════════════

  Parallel (non-bloquant) : C7 (frontend F-05, 3j) + C8 (Sprint 8 UI/UX, 5j)
```

**Chemin critique pré-prod (séquentiel) :** C2 (TLS) + C3 (frontend fix) + C9 (token rotation) = **~3.5 jours**.
**Parallélisable (solo dev) :** C2 + C3 + C5 + C6 + C7 + C9 + C8 = **~14 jours**.

---

## 4. Gate de mise en production

**BLOQUANTS ABSOLUS** — ne pas déployer sans :

- [ ] **C2** : Caddy wired dans docker-compose, `wss://` bout-en-bout, `ALLOW_INSECURE=false` en prod, cookies `Secure`
- [ ] **C3** : Build frontend verte (`npm run build` passe)
- [ ] **C6** : migrations idempotentes + `alembic stamp head`
- [ ] **C9** : rotation WORKER_TOKEN fonctionnelle (sinon workers crashloop après 7j)
- [ ] **Rotation `LLM_API_KEY`** de `sk-hY0lH32Z1UDArBSXxUsoyw` (voir `SECRET_ROTATION.md`)
- [ ] **Force change du mot de passe `admin/admin`** en prod

**DÉJÀ FAIT (vérifié 2026-07-12) :**
- ✅ CI pipeline : pytest + frontend lint/build + go test en parallèle
- ✅ Release workflow : 8 plateformes + minisign + manifest.json
- ✅ `ENFORCE_HTTPS`, `COOKIE_SECURE` configurés
- ✅ Endpoint `/metrics` Prometheus
- ✅ `scripts/build_worker.sh` cross-compilation
- ✅ 6 tests Go passent
- ✅ Rate limiter actif

---

## 5. Actions immédiates recommandées

1. **AUJOURD'HUI** — Lancer C1 (audit refresh, 4h). C'est le seul moyen de savoir sur quoi on travaille vraiment.
2. **CETTE SEMAINE** — Kick off C2 (TLS) + C4 (CI) en parallèle. Ils sont indépendants et bloquants tous les deux.
3. **SPRINT SUIVANT** — C3 + C5 + C6 + C9 séquentiels ou parallèles selon effectif.
4. **SPRINT +1** — C7 + C8 (UI/UX + types).

---

*Ce plan remplace les priorités des audits 2026-06-27 et 2026-06-28. Les items 🔴 Critique de ces audits (B-01, B-02, B-06) sont majoritairement obsolètes — voir §0 pour la vérification code par code.*
