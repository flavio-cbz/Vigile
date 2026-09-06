# Vigile — Guide de Routage & Assignation des Modèles (Référence Humaine)

> **IMPORTANT :** Ce document est destiné exclusivement à l'opérateur humain pour router les tickets vers les bons modèles et outils. Il ne doit **PAS** être injecté dans le contexte d'un agent exécutant un ticket.

*Dernière mise à jour : 28 août 2026 — Directive QUALITÉ +++ (sans limite temps/coût)*

---

## 1. Table d'Assignation Révisée (Qualité +++)

> **Directive qualité +++ (appliquée le 2026-08-26)** : pour chaque ticket, le modèle EXEC est systématiquement le **meilleur modèle qualité**, sans compromis de temps ni de coût.
> - **MiMo-V2.5** : 78.9% SWE-bench Verified / 68.4% Terminal / 1M ctx → Recommandé pour la planification d'architectures globales et gros refactors.
> - **Muse Spark 1.2 Contributor** : ~77.4% SWE-bench / 59.3% DeepSWE (extended thinking) → Recommandé pour la logique fine, les algorithmes pointus, les garde-fous fail-closed et l'exécution complexe.
> - **Nemotron 3.5 Lightning** : 51.56% SWE-bench → Cantonné à l'orchestration rapide ou scripts éphémères, **banni de l'EXEC qualité +++**.

### Tickets Restants (Backlog Actif)

| Ticket | Chantier & Périmètre | Outil Recommandé | Modèle PLAN (Session 1) | Modèle EXEC (Session 2) | Garde-fou |
|---|---|---|---|---|---|
| **B4** | Services : optimisation chargement (p95 < 100ms) | OpenCode + omo / Antigravity | **Muse Spark 1.2** | **Muse Spark 1.2** | Standard (Prérequis B1) |
| **B5** | Suppression des boutons refresh manuels (audit 19 boutons) | OpenCode + omo / Antigravity | **Muse Spark 1.2** | **Muse Spark 1.2** | Standard |
| **C1** | Disques : sélecteur point de montage & cache multi-path | OpenCode + omo / Antigravity | **MiMo-V2.5** | **Muse Spark 1.2** | Standard |
| **C2** | Services + Docker : actions destructrices (`DELETE_CONTAINER`, `STOP_SERVICE`) | Antigravity | **MiMo-V2.5** + **Muse Spark 1.2** (Duo) | **Muse Spark 1.2** | **Maximal** (Confirmation humaine stricte) |
| **C3** | Media Stack : Sonarr, Radarr, Overseerr (bloc `media-service-card`) | Antigravity | **MiMo-V2.5** | **Muse Spark 1.2** (1 session / service) | Renforcé (Anti-hallucination API) |
| **C4** | Plex : vraie intégration API & flux live B1 | Antigravity | **MiMo-V2.5** | **Muse Spark 1.2** | Renforcé (Anti-hallucination API) |
| **C4.2** | Plex : prévisualisation lectures & hub tâches d'arrière-plan | Antigravity | **MiMo-V2.5** | **Muse Spark 1.2** | Renforcé (Anti-hallucination API) |
| **D1** | Migration des 9 plugins déclaratifs (7 simples + 2 critiques) | Antigravity | **MiMo-V2.5** (7 simples) / **Duo MiMo+Spark** (Docker/Systemd) | **Muse Spark 1.2** (1 session / plugin) | Renforcé (Captures avant/après) |
| **E1-E5**| Nettoyage UI/UX (i18n, IP header, popover aide, cap proposals, shortcuts logs) | OpenCode + omo / Antigravity | — (Protocole allégé Plan+Exec) | **Muse Spark 1.2** | Standard |
| **F1** | Dette technique : audit & refactor routes API | OpenCode + omo / Antigravity | **MiMo-V2.5** (Audit S0) / **Muse Spark 1.2** (Plan S1) | **Muse Spark 1.2** | Standard |
| **G1** | IA & Copilote : streaming SSE/WS, contexte frais, structured outputs | Antigravity | **MiMo-V2.5** | **Muse Spark 1.2** | Renforcé (Observabilité & Résilience) |

---

## 2. Historique des Tickets Achevés (Archivés)

Ces tickets ont déjà été développés, testés et mergés. Ils servent de référence d'architecture pour les chantiers dépendants (notamment le pattern précalcul+live de B1) :

| Ticket | Sujet | Date de merge | Notes |
|---|---|---|---|
| **A3** | Hardening `localStorage` + garde-fou visuel + cycle `isRefreshing` | 2026-08 | Résilience du stockage local et des refreshs UI |
| **A4** | Raisonnement fail-open registre (`refreshRegistry` + resync mutations) | 2026-08-22 | Resync `pluginStore` après toggle/install/delete/upload |
| **A5** | Algo extrapolation disque (tri, dédupe, IQR, confidence, `hours_collected`) | 2026-08 | Estimation robuste de la saturation disque |
| **B1** | Pipeline architectural précalcul + live global | 2026-08 | Socle de mise en cache et de rafraîchissement asynchrone |
| **B2** | Structuration globale backend | 2026-08 | Factorisation des gestionnaires de nœuds |
| **B3** | Structuration globale frontend | 2026-08 | Standardisation des hooks SWR et gestion d'état |

---

## 3. Analyse & Sélection des Modèles

### Modèles Retenus

* **MiMo-V2.5** : Contexte large de 1M tokens, 78.9% SWE-bench Verified. Idéal pour la planification d'architectures globales, la cartographie globale des routes API et la cohérence de gros modules.
* **Muse Spark 1.2 Contributor** : Raisonnement approfondi (extended thinking, 59.3% DeepSWE). Idéal pour l'implémentation fine, la sécurité fail-closed, les algorithmes de parsing et les sessions de review hostile.
* **Claude Opus 4.6 / Gemini 3.7 Pro** : Modèles d'analyse de haut niveau pour les arbitrages de conception et la vérification des invariants critiques.

### Modèles Écartés / Déclassés

* **Nemotron 3 Ultra** : 56.4% Terminal-Bench, en retrait sur le code agentique. **Déclassé : plus jamais en PLAN**.
* **Nemotron 3.5 Lightning** : 51.56% SWE-bench, orienté débit/vitesse pure. **Écarté de l'exécution qualité +++** pour éviter la dette technique.
* **Laguna S 2.1** : Tendance aux boucles agentiques et arrêts prématurés. **Écarté**.
* **Big Pickle** : Modèle stealth expérimental déprécié, remplacé par Muse Spark 1.2.
* **Hy3** : Initialement écarté pour restrictions de licence. *Note 2026-08 : La version officielle Apache 2.0 a levé ces restrictions ; modèle réévaluable pour l'orchestration si besoin.*

---

## 4. Mapping des Outils / Subagents

### `oh-my-openagent` (si utilisé)
* **Prometheus / Plan** → MiMo-V2.5 (architecture) ou Muse Spark 1.2 (bug/algo)
* **Momus / Review Plan & Review Diff** → Muse Spark 1.2 (DeepSWE) ou MiMo-V2.5
* **Explore / Librarian** → Modèle flash léger (recherche documentaire)
* **Build / EXEC** → Muse Spark 1.2
* **Oracle / Sisyphus** → Muse Spark 1.2 ou MiMo-V2.5

### `Antigravity`
* **Planification & Architecture** → Agent principal (Opus / Flash Thinking / Pro)
* **Recherche & Exploration** → Subagent `research`
* **Exécution** → Agent principal avec tests et validation stricts
* **Review** → Session séparée dédiée uniquement à l'inspection du diff
