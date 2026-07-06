# Plan d'Action — Corrections Issues des Audits

**Généré le :** 2026-07-06
**Source :** `AUDIT_REPORT_2026-06-27.md`, `AUDIT_REPORT_2026-06-28.md`, `LIMITS.md`, `PLAN.md`
**Méthode :** Analyse adversarial multi-agent (4 perspectives) + vérification code réel

---

## Résumé Exécutif

### Découverte Majeure — Audits Staled

Les audits AU dit 2026-06-27/28 sont **en partie obsolètes**. La vérification sur le code actuel montre que les items 🔴 **Critique** sont déjà corrigés :

| ID Audit | Problème Signalé | Statut Code Actuel |
|----------|-----------------|-------------------|
| **B-01** | `os.environ` hors `config.py` | ✅ Corrigé — `secret_loader.py` utilise `getattr(os, "environ", {})` (pattern test-injection) |
| **B-02** | `from master.config import settings` dans api/ | ✅ Corrigé — `auth.py` utilise `Depends(get_settings)`, `deps.py` lazy factory |
| **B-06** | f-strings SQL dans `node_manager.py`, `audit.py`, `automations.py` | ✅ Corrigé — concaténation avec `+`, identifiants validés via whitelists (`_ALLOWED_UPDATE_FIELDS`) |
| **G-01** | Underscore Go dans `connection.go` | ✅ Corrigé — les 5 sites d'enrollment utilisent `if x, ok := ...; ok { }` |
| **S-01** | Migration non idempotente | ✅ Corrigé — `CREATE TABLE IF NOT EXISTS` présent |

### Ce qui Reste Vraiment Bloquant

Malgré ces corrections, **5 gaps bloquants** subsistent pour la production :

1. **🔴 Aucun TLS actif** — `docker-compose.yml` expose Master en HTTP clair (`8003:8000`) ; le service `caddy` décrit dans `docs/TLS.md` n'existe pas dans le Compose
2. **🔴 Reconnect Worker sans challenge Ed25519** — un `WORKER_TOKEN` volé suffit à usurper un nœud hors ligne
3. **🔴 Clé LLM compromise documentée en clair** — `docs/SECRET_ROTATION.md:5` contient la clé `sk-hY0lH32Z1UDArBSXxUsoyw` dans un fichier versionné
4. **🟠 Audit non atomique avec mutation** — `delete_node()` commit avant `log_action()`, un échec d'audit laisse l'état changé sans trace
5. **🟠 Rotation WORKER_TOKEN non implémentée** — `rotation_due` stocké mais pas exploité ; pas de `TOKEN_ROTATION_COMMAND` réel

---

## Synthèse des Analyses

### 🔧 Quick Wins — 17 Tickets (≈6h)

Correctifs indépendants, réalisables en < 2h chacun, priorisés par impact.

| ID | Description | Composant | Effort | Priorité |
|----|------------|-----------|--------|----------|
| QW-01 | `asyncio.Queue` sans `maxsize` dans pool SQLite | `master/db/database.py` | 15min | 🔴 |
| QW-02 | Imports différés `import json` dans méthodes | `master/core/action_proposal.py` | 10min | 🟠 |
| QW-03 | Annotations de type manquantes (`compute_entry_hash`) | `master/core/audit.py`, `automation_engine.py` | 20min | 🟠 |
| QW-04 | Magic numbers Go (tailles RFC 6455) | `worker/wsclient.go` | 15min | 🟠 |
| QW-05 | Dépendances non whitelistées dans `RULES.md` | `requirements.txt` | 20min | 🟠 |
| QW-06 | `any` TS — champs `details`/`raw` → `Record<string, unknown>` | frontend (4 fichiers) | 30min | 🟠 |
| QW-07 | `any` TS — catch blocks → `unknown` + type guard | frontend (6 fichiers) | 30min | 🟠 |
| QW-08 | `any` TS — interfaces composants manquantes | frontend (4 fichiers) | 45min | 🟠 |
| QW-09 | `any` TS — cast `_toasted` dans `useApi.ts` | `frontend/src/hooks/useApi.ts` | 20min | 🟠 |
| QW-10 | Magic number timer `NotifBell` → `usePolling` | `frontend/src/components/layout/NotifBell.tsx` | 20min | 🟠 |
| QW-11 | Températures LLM hardcodées (`temperature=0.3`) | `master/api/chat.py` | 25min | 🟠 |
| QW-12 | Dict sans TTL `_pending_db_calls` | `master/core/plugin_worker.py` | 45min | 🟠 |
| QW-13 | `SESSION.md` manquant — créer template | `docs/` | 10min | 🟡 |
| QW-14 | Clé LLM en clair dans `SECRET_ROTATION.md` — masquer | `docs/SECRET_ROTATION.md` | 5min | 🟡⚠️ |
| QW-15 | Routes README obsolètes (20 routes manquantes) | `README.md` | 30min | 🟡 |
| QW-16 | String concat Go (`wsclient.go`) | `worker/wsclient.go` | 10min | 🟡 |
| QW-17 | Timeout DB hardcodé → `settings.db_pool_timeout` | `master/db/database.py` | 20min | 🟡 |

### 🏗️ Chantiers High-Impact — 9 Chantiers (8.5j-18.5j)

| ID | Chantier | Effort | Dépendances | Priorité |
|----|---------|--------|-------------|----------|
| **C1** | Audit Refresh & Stale Baseline | 0.5j | Aucune | P0 |
| **C2** | TLS Réel (Caddy dans Compose) | 1j | Aucune | **P0** |
| **C3** | Tests de Verrouillage (avant refactor) | 2j | C1 | P0 |
| **C4** | CI/CD Pipeline (pre-commit + tests auto) | 1.5j | Aucune | P1 |
| **C5** | Protocole Worker — Reconnect Challenge Ed25519 | 2j | C3 | **P0** |
| **C6** | Helpers SQL + Audit Atomique | 1.5j | C3 | P1 |
| **C7** | Frontend — Typage Strict Restant | 1j | Aucune | P1 |
| **C8** | UI/UX Sprint 8 (corrections affichage) | 2j | C7 | P2 |
| **C9** | Rotation WORKER_TOKEN automatique | 1.5j | C5 | P1 |

### 🧠 Analyse Systémique — Causes Racines

**Cause Racine A — Frontières DI/Config Floues**
- B-01/B-02 ne sont pas 2 bugs indépendants mais un même compromis historique
- `LLMClient.__init__` retombe sur `load_secret("LLM_API_KEY")` si `api_key` vide
- `get_db_conn()` est encore utilisé par **27 callers** (dont worker_handler, node_manager)
- `main.py:init_db()` ne passe pas `settings.db_pool_size` (ignoré au démarrage)

**Cause Racine B — Pas d'Unit of Work Transactionnel**
- `delete_node()` : `DELETE` → `commit()` → `log_action()` dans un `try/except` qui avale l'échec
- `transition_state()` modifie l'état et commit, mais laisse l'audit aux callers (parfois oublié)
- `_VALID_RULE_FIELDS` manque `description` et `conditions_json` → certains PATCH automation_rules échouent

---

## Plan d'Exécution

### Phase 1 — Urgences Prod (Jour 1)

Ces items doivent être faits **avant toute mise en production**.

```
Jour 1 matin (2h) :
├── QW-14  Masquer clé LLM dans SECRET_ROTATION.md
├── C2     Ajouter service Caddy au docker-compose.yml
│          (ou documenter que Caddy est externe)
└── QW-01  Fix asyncio.Queue maxsize
```

#### C2 — TLS Réel
- Ajouter service `caddy` dans `docker-compose.yml` avec le `Caddyfile` existant
- Retirer l'exposition directe `8003:8000` du Master
- Configurer `ALLOW_INSECURE=false` par défaut en prod
- Vérifier que `ENFORCE_HTTPS`, `COOKIE_SECURE`, `TRUSTED_PROXIES` sont activés

### Phase 2 — Tests & Verrouillage (Jour 1-2)

Avant tout refactor, sécuriser les comportements existants avec des tests.

```
Jour 1 après-midi (3h) :
├── C1     Audit refresh — re-exécuter les audits auto sur code actuel
├── C3a    Tests vérrouillage SQL builder (colonne inconnue rejetée)
├── C3b    Test refresh token double concurrence
└── C3c    Test delete_node avec échec d'audit simulé
```

#### C3 — Tests de Verrouillage

| Test | Composant | Comportement |
|------|-----------|-------------|
| `test_sql_builder_rejects_unknown_fields` | node_manager | Colonne inconnue → ValueError |
| `test_update_rule_with_description` | automations | PATCH description doit fonctionner |
| `test_delete_node_audit_failure` | node_manager | Si audit échoue, rollback ou erreur |
| `test_refresh_token_concurrent` | auth | 2 requêtes simultanées → un seul OK |
| `test_worker_reconnect_no_private_key` | ws | Token + clé publique sans clé privée → rejeté |

### Phase 3 — Corrections sans Changement d'Architecture (Jour 2-3)

```
Jour 2 (4h) :
├── QW-02  Imports différés action_proposal.py
├── QW-03  Annotations manquantes audit.py + automation_engine.py
├── QW-11  Températures LLM → settings
├── QW-17  Timeout DB → settings.db_pool_timeout
├── QW-05  Whitelist dépendances RULES.md
└── C6a    Helper sql_placeholders(count) + build_update_clause()

Jour 3 matin (3h) :
├── QW-04  Magic numbers Go wsclient.go
├── QW-12  Dict TTL _pending_db_calls (plugin_worker.py)
├── QW-16  String concat Go wsclient.go
└── C6b    Fix _VALID_RULE_FIELDS (description, conditions_json)
```

### Phase 4 — Frontend (Jour 3-4)

```
Jour 3 après-midi (3h) :
├── QW-06  any → Record<string, unknown> (formatAudit, AuditPage, types)
├── QW-07  catch any → unknown (LoginPage, useSSE, chatStore)
├── QW-09  _toasted cast → ToastedError interface
└── QW-10  NotifBell → usePolling

Jour 4 matin (2h) :
├── QW-08  Interfaces composants (Sidebar, AllChatsModal, ProposalsPage, ServersPage)
└── C7     Audit typage restant
```

### Phase 5 — Protocole Worker Critique (Jour 4-5)

```
Jour 4 après-midi (3h) :
├── C5a    Reconnect avec challenge Ed25519
│          → worker_handler.py: ne pas skip le challenge en reconnect
│          → connection.go: signer le challenge avec clé privée
└── C5b    Tests de non-régression reconnect

Jour 5 (4h) :
├── C9a    Rotation WORKER_TOKEN sur heartbeat
│          → security_manager: implémenter TOKEN_ROTATION_COMMAND
│          → connection.go: gérer TOKEN_ROTATION_COMMAND + ACK
├── C9b    Révocation atomique ancien token / insertion nouveau
└── C9c    Journaliser rotation et suspicion de vol
```

### Phase 6 — DB & Audit Unit of Work (Jour 5-6)

```
Jour 5-6 (3h) :
├── C6c    Helper audit_transaction(db, user_id, action, details)
│          → BEGIN IMMEDIATE → mutate → log_action → commit
├── C6d    delete_node() dans audit_transaction
├── C6e    transition_state() avec audit optionnel intégré
└── C6f    Passer pool_size=settings.db_pool_size (main.py)
```

### Phase 7 — Documentation & Finition (Jour 6)

```
Jour 6 (2h) :
├── QW-13  Créer SESSION.md template
├── QW-15  Mettre à jour README.md (20 routes manquantes)
└── C1b    Mettre à jour AGENTS.md avec les corrections appliquées
```

### Phase 8 — CI/CD (Jour 6-7)

```
Jour 6-7 (3h) :
├── C4a    Pre-commit hook (ruff, black, trailing-whitespace)
├── C4b    GitHub Actions: pytest unitaires sur PR
├── C4c    GitHub Actions: lint frontend (tsc --noEmit)
└── C4d    GitHub Actions: Go vet + build worker
```

---

## Diagramme de Dépendances

```text
Jour 1          Jour 2          Jour 3          Jour 4          Jour 5          Jour 6
──────          ──────          ──────          ──────          ──────          ──────
QW-14 ─┐
C2 ────┤
QW-01 ─┤
       │
C1 ────┤                            
C3 ────┼─────────────────┐
       │                 │
QW-02 ─┤                 │
QW-03 ─┤                 │
QW-11 ─┤                 │
QW-17 ─┤                 │
QW-05 ─┤                 │
C6a ───┤                 │
       │                 │
QW-04 ─┤                 │                 Frontend (parallèle)
QW-12 ─┤                 ├── QW-06/07/09/10 ── QW-08 ── C7 ──┐
QW-16 ─┤                 │                                    │
C6b ───┤                 │                                    │
       │                 │                                    │
       │                 └── C5a ── C5b ── C9a ── C9b ── C9c ─┤
       │                                    │                 │
       │                                    └── C6c ── C6d ──┼── C6e ── C6f
       │                                                      │
       │                                                      └── QW-13 ── QW-15
       │                                                                     │
       │                                                                     └── C4
```

---

## Prod Gate — Checklist 8 Points Bloquants

Avant toute mise en production, ces 8 points doivent être **verts** :

| # | Vérification | Statut |
|---|-------------|--------|
| 1 | TLS actif : Caddy devant Master, pas de port Master exposé | ❌ |
| 2 | `ALLOW_INSECURE=false` pour tous les Workers | ❌ |
| 3 | Reconnect Worker validé par challenge Ed25519 (pas seulement JWT) | ❌ |
| 4 | Clé LLM révoquée et masquée dans les docs | ❌ |
| 5 | `ENFORCE_HTTPS=true`, `COOKIE_SECURE=true`, `COOKIE_SAMESITE=lax` | ❌ |
| 6 | Audit atomique : delete_node logué AVANT commit | ❌ |
| 7 | CORS origins explicites (pas de wildcard `*`) | ❌ |
| 8 | Backup SQLite automatisé + test de restore | ❌ |

---

## Métriques de Succès

| Métrique | Cible | Comment |
|----------|-------|---------|
| Quick Wins appliqués | 17/17 | Chaque QW validé par `lsp_diagnostics` + test pass |
| Tests de verrouillage ajoutés | ≥6 | Phase C3 |
| Audit atomicité | 0 mutation critique sans log_action avant commit | Vérification par grep `log_action` après chaque mutation |
| TLS actif | `curl -sk https://localhost/health` OK | Caddy + Master dans Compose |
| Reconnect challenge | Test vol de token rejeté | Test e2e Worker |
| Couverture tests modules sensibles | auth.py ≥95%, database.py ≥80% | pytest --cov |
| CI verte | 100% sur PR | GitHub Actions |

---

## Risques & Mitigations

| Risque | Mitigation |
|--------|-----------|
| Sur-correction avec archi enterprise | Garder SQLite, FastAPI Depends, helpers simples. Pas d'ORM ni PostgreSQL tant que la charge ne l'impose pas. |
| Casser des PATCH partiels en corrigeant B-06 | Tests par endpoint avant helper SQL. Le bug `_VALID_RULE_FIELDS` montre déjà un cas réel. |
| Rotation Worker casse nœuds existants | Compatibilité transitoire : accepter ancien reconnect pendant 1 version, exiger challenge ensuite. |
| Audit atomique introduit des locks SQLite | Transactions courtes, `BEGIN IMMEDIATE` seulement autour mutation+audit. Lectures lourdes hors transaction. |
| TLS documenté mais pas déployé | Un seul chemin prod documenté : Caddy public → Master internal. Pas de double exposition. |

---

## Déjà Corrigé (Ne Pas Retravailler)

Ces items des audits sont déjà résolus dans le code actuel :

- ~~B-01 os.environ hors config.py~~ ✅
- ~~B-02 settings import dans api/~~ ✅
- ~~B-06 f-strings SQL~~ ✅
- ~~G-01 underscore Go (enrollment)~~ ✅
- ~~S-01 migration non idempotente~~ ✅
- ~~A-03 abstractions YAGNI~~ ✅ (acceptable pour le projet)
- ~~X-06 dépendances non whitelistées~~ ✅ (sous-dépendances légitimes)
- ~~T-01 couverture security_manager~~ ✅ (95%)
- ~~Limites Ed25519 permissions, refresh token invalidation, rate limiter cleanup~~ ✅ (LIMITS.md)

---

## Notes sur l'Architecture DB Actuelle

`database.py` a déjà évolué depuis les audits :

- Connexion primaire `_db` + pool `DatabaseConnectionPool`
- `database_session()` bind une connexion dans `ContextVar`
- Les routes FastAPI avec `DB = Depends(get_db)` passent par le pool
- Mais `get_db_conn()` retourne encore la connexion contexte ou primaire (27 callers)

**Solution graduelle :**
1. **Quick** — passer `pool_size=settings.db_pool_size` (actuellement ignoré)
2. **Short** — créer `background_database_session()` pour heartbeat/cache/plugins
3. **Medium** — séparer lectures lourdes (`verify_chain`, exports) sur connexion dédiée
4. **Large** — PostgreSQL seulement si multi-utilisateur/multi-worker sérieux

---

*Plan généré par analyse adversarial multi-agent (low + high + ultrabrain) + vérification code.*
*Rapports source : AUDIT_REPORT_2026-06-27.md, AUDIT_REPORT_2026-06-28.md, LIMITS.md, PLAN.md*
