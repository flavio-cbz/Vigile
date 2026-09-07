# Vigile — Protocole Commun et Règles d'Exécution

*Compagnon du backlog technique consolidé. Révisé le 30 août 2026.*

Ce document définit les règles partagées et le protocole méthodologique non négociable pour l'ensemble des tickets du projet Vigile. Chaque fichier de ticket dans ce dossier (`docs/plans/tickets/`) est un prompt autonome prêt à être injecté dans une session d'agent.

---

## 1. Index des Fichiers de Tickets Actifs

| Fichier | Contenu & Objectifs | Risque & Garde-fou |
|---|---|---|
| [`C3-sonarr-radarr-overseerr.md`](C3-sonarr-radarr-overseerr.md) | **C3** (plugins Sonarr, Radarr, Overseerr — bloc catalogue `media-service-card`) | Renforcé (Anti-hallucination API) |
| [`C4-plex.md`](C4-plex.md) | **C4** (vraie intégration API Plex, flux live B1, token chiffré) | Renforcé (Anti-hallucination API) |
| [`C4.2-plex-activites-et-previsualisation.md`](C4.2-plex-activites-et-previsualisation.md) | **C4.2** (Plex : prévisualisation lectures & hub tâches d'arrière-plan / activities) | Renforcé (Anti-hallucination API) |
| [`D1-migration-plugins.md`](D1-migration-plugins.md) | **D1** (migration des 9 plugins vers manifests déclaratifs V2) | Renforcé (1 session / plugin, captures) |
| [`F1-dette-technique.md`](F1-dette-technique.md) | **F1** (audit exhaustif et unification des routes API backend) | Standard (Session 0 Audit préalable) |
| [`G1-ia-copilote.md`](G1-ia-copilote.md) | **G1** (fiabilisation streaming SSE/WS, contexte frais, structured proposals) | Renforcé (Observabilité & Résilience) |

### Tickets Terminés & Mergés
- **Chantier B (B4, B5)** : Cache services p95 < 100ms, SingleFlight, auto-refresh passif — *Mergé dans commit `d67390b`*.
- **Chantier C1 (C1)** : Sélecteur point de montage, cache SQLite multi-path, drill-down treemap — *Mergé dans commit `2fb467a`*.
- **Chantier C2 (C2)** : Actions destructives fleet (`DELETE_CONTAINER`, `STOP_SERVICE`) avec garde-fous terminaux, sanitization et audit SHA256 — *Mergé dans commit `66c42fc`*.
- **Chantier E (E1 à E5)** : Parité i18n, IP header, popover aide contextuelle, tri proposals et raccourcis logs — *Mergé dans commits `38889ce`, `d8aa7f7`, `4fb0fe1`*.

> **Note :** La table d'assignation des modèles et les benchmarks de routage pour l'opérateur humain sont documentés dans [`docs/plans/00-modeles-et-routage.md`](../00-modeles-et-routage.md).

---

## 2. Protocole Méthodologique Strict

### A. Protocole Standard (4 sessions distinctes)

Applicable à tous les tickets hors Chantier E :

1. **Session 1 — PLAN (Lecture seule stricte)** : L'agent analyse le codebase local, formule ses hypothèses et produit un plan ordonné fichier par fichier sans modifier aucun fichier.
2. **Session 1.5 — VÉRIFICATION PLAN (Critique hostile — Momus / Oracle)** : Un agent d'audit indépendant critique le plan point par point, détecte les angles morts et donne son verdict (`GO`, `GO avec corrections`, `REWORK`).
3. **Session 2 — EXÉCUTION (Session vierge)** : L'agent implémente le plan validé, exécute les tests locaux, vérifie le typage strict, consigne dans `SESSION.md` et **affiche obligatoirement le diff complet (`git diff HEAD`) dans sa réponse finale**.
4. **Session 3 — REVIEW DIFF (Audit neutre du diff seul)** : Une session neutre, ouverte sans l'historique de conversation de développement, inspecte uniquement le `git diff HEAD` (copié directement de la fin de Session 2) pour traquer régressions, failles et contournements.

### B. Protocole Allégé UI/UX (2 sessions — Chantier E)

Applicable uniquement aux tickets E1 à E5 (faible risque, corrections cosmétiques et traductions) :

1. **Session 1 & 2 fusionnées — PLAN + EXÉCUTION** : L'agent prend connaissance de l'audit et des hypothèses figées, implémente les corrections, valide les tests, consigne dans `SESSION.md` et **affiche le diff complet dans sa réponse**.
2. **Session 3 — REVIEW DIFF** : Audit neutre sur le diff seul.

---

## 3. Dispositif Anti-Triche et Invariants Qualité +++

Pour contrer les modes d'échec connus des modèles d'IA (*Reward Hacking*, sycophancie, code lazy) :

1. **Interdiction de modifier les tests existants** :
   - Il est **formellement interdit de modifier ou supprimer un test existant** pour faire passer du nouveau code. Si un test existant casse, c'est que l'implémentation introduit une régression : corrige ton code, pas le test.
2. **Cloisonnement total de la Review (Session 3)** :
   - La session de review ne doit **JAMAIS** recevoir le prompt de développement ni l'historique du chat. Elle ne reçoit que le diff brut (`git diff HEAD` généré en fin de Session 2) et une checklist d'attaque.
3. **Zéro contournement de typage & Zéro erreur avalée** :
   - `as any`, `@ts-ignore`, `try/except: pass` sans logging explicite et bypasses de linting sont formellement interdits.
   - Toute opération externe (Worker, API, DB) doit être traitée en **fail-closed** avec état d'erreur actionnable côté UI.
4. **Workspace local direct** :
   - L'agent manipule directement les fichiers du workspace et exécute les commandes dans son terminal local.
   - Aucune action destructrice réelle sur l'infrastructure de production : mocks et tests d'intégration locaux uniquement.

---

## 4. Clôture Obligatoire dans `SESSION.md` & Sortie du Diff

À la fin de chaque session d'exécution ou d'intervention, l'agent **DOIT impérativement** :
1. Ajouter une entrée à la fin de [`SESSION.md`](../../SESSION.md) en respectant le template invariant (Objectif, Durée, Processus, Fichiers modifiés, Notes techniques et diff).
2. **Afficher le diff complet (`git diff HEAD`) dans un bloc markdown ` ```diff ` à la toute fin de sa réponse finale**, permettant ainsi à l'opérateur de le copier directement vers la session de review sans manipulation manuelle de terminal.
