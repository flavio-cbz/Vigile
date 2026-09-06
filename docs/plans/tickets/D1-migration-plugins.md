# Chantier D1 — Migration des 9 Plugins vers Manifests Déclaratifs V2

*Protocole partagé, règles d'exécution et anti-triche : voir [`00-protocole-commun.md`](00-protocole-commun.md).*

---

## D1. Migration des Plugins du Catalogue (Qualité +++)

**Outil / Modèle :** Antigravity — PLAN **MiMo-V2.5** (7 simples) / **Duo MiMo + Spark** (Docker/Systemd) + EXEC **Muse Spark 1.2** partout · Garde-fou renforcé (Captures comparatives avant/après) · **1 session dédiée par plugin** (jamais de migration en lot).

> **Directive d'Architecture Déclarative V2** :
> Chaque plugin doit être un module autonome `master/plugins/<id>/` contenant uniquement `__init__.py` et `manifest.json` (`schema_version: 2`, `trusted: true` pour les plugins intégrés).
> L'interface utilisateur doit être rendue à 100% par le moteur générique `BlockRenderer` à partir des blocs du catalogue (`stat-card`, `table`, `chart`, `log-viewer`, `action-panel`, `form`, `alert-banner`, `media-service-card`). Aucun composant React custom spécifique dans `frontend/src/plugins/`.
> La suppression d'un dossier de plugin doit retirer automatiquement ses routes, son UI et ses permissions sans effet de bord.

### Ordre d'Exécution Conseillé (du plus simple au plus critique)

| # | Plugin | Modèle Recommandé | Prérequis | Blocs Catalogue Cibles | Risque Principal |
|---|---|---|---|---|---|
| **1** | Clean Logs Utility | Muse Spark 1.2 | — | `action-panel`, `stat-card`, `log-viewer` | Faible (UI simple) |
| **2** | Discord Alerts | Muse Spark 1.2 | — | `form`, `action-panel`, `stat-card` | Formulaires & webhooks |
| **3** | Slack Alerts | Muse Spark 1.2 | — | `form`, `action-panel`, `stat-card` | Formulaires & webhooks |
| **4** | Log File Housekeeping | Muse Spark 1.2 | — | `table`, `stat-card`, `action-panel` | Tableaux & filtres |
| **5** | Metrics Collector | Muse Spark 1.2 | B1 | `chart`, `stat-card` | Rendu des graphiques & échelles |
| **6** | Analyse Disque | Muse Spark 1.2 | A5 + C1 | `chart`, `stat-card`, `table` | Treemap & extrapolation |
| **7** | Plex Media Server | Muse Spark 1.2 | C4 | `stat-card`, `table`, `alert-banner` | Télémétrie live & sessions |
| **8** | Systemd Service Manager | Muse Spark 1.2 | C2 | `table`, `action-panel`, `alert-banner` | Actions & confirmations |
| **9** | Docker Container Orchestrator | Muse Spark 1.2 | C2 | `table`, `action-panel`, `form` | Actions destructrices |

---

### Session 1 — Plan (À répéter pour chaque plugin)

```markdown
Contexte : projet Vigile, ticket D1. Migration du plugin [NOM DU PLUGIN] vers l'architecture déclarative V2 (manifest.json + blocs catalogue).

Voici une capture d'écran de l'état actuel de l'UI du plugin : [colle la capture de référence].

Environnement : lis et explore directement les fichiers du workspace local via ta session en lecture seule stricte.

Ne code rien. Produis uniquement :
1. L'inventaire exhaustif de l'UI actuelle du plugin : sections, cartes, formulaires, tableaux, et gestion des états (chargement, vide, erreur).
2. Le mapping vers les blocs du catalogue (stat-card, table, chart, log-viewer, action-panel, form, alert-banner) : quel bloc reproduit quelle section.
3. La liste des fichiers backend et frontend actuels du plugin et leur sort (migré vers manifest, supprimé, ou fondu dans le catalogue).
4. Les routes (`routes`), hooks (`hooks`), pages (`pages`) et configurations (`config_schema`) à déclarer dans le `manifest.json`.
5. Tes hypothèses, que je dois valider.

J'attends ta réponse, je la valide, puis nous passerons à la vérification du plan.
```

---

### Session 1.5 — Vérification Plan (Momus / Oracle — Qualité Maximale)

```markdown
Agent : Momus (Oh My OpenCode) / Oracle — Critique de plan de migration.

Consigne qualité NON NÉGOCIABLE :
- Vérifie la parité fonctionnelle stricte avec l'UI d'origine.
- Contrôle que le manifest respecte le schéma Pydantic `PluginManifestV2` (`extra="forbid"`) et que zéro composant React custom orphelin n'est créé.

Mission : critique le plan fichier par fichier. Cherche les omissions de permissions, les pertes d'interactions utilisateur et les couplages frontend résiduels.
Verdict attendu : GO / GO avec corrections mineures / REWORK.
```

---

### Session 2 — Exécution (À répéter pour chaque plugin)

```markdown
Voici le plan validé pour la migration du plugin [NOM DU PLUGIN] :
[colle le plan validé]

Capture de référence initiale : [colle la capture]

Règles strictes d'exécution et anti-triche :
- Environnement : modifie directement les fichiers du workspace local avec tes outils d'édition intégrés et lance les tests dans ton terminal local.
- INTERDIT de modifier ou supprimer un test existant pour le faire passer.
- L'UI doit être ENTIÈREMENT rendue par `BlockRenderer` avec les blocs du catalogue. Zéro composant custom ad-hoc.
- Le manifest doit être validé strictement par `PluginLoader` (schéma JSON, routes, permissions).
- Vérification visuelle obligatoire : après modification, prends une capture d'écran du résultat dans le navigateur et compare-la section par section avec la capture de référence. Signale toute divergence visuelle.
- Test de suppression propre : vérifie que supprimer le dossier du plugin retire immédiatement son UI, ses routes et ses permissions sans erreur ni trace résiduelle.
- Clôture et sortie obligatoire du diff : à la fin de l'intervention, (1) documente ce qui a été réalisé en ajoutant une entrée à la fin de SESSION.md selon le format invariant, et (2) AFFICHE OBLIGATOIREMENT LE DIFF COMPLET (dans un bloc de code markdown ```diff contenant la sortie exacte de `git diff HEAD`) à la toute fin de ta réponse finale pour que l'opérateur puisse le copier directement vers la session de review.

Exécute uniquement la migration de [NOM DU PLUGIN].
```

---

### Session 3 — Review Diff (Audit Hostile & Parité Visuelle)

```markdown
Voici le diff de la migration du plugin [NOM DU PLUGIN] ainsi que les captures avant/après :
Diff : [colle le diff brut git diff HEAD]
Capture Avant : [colle]
Capture Après : [colle]

Environnement : vérifie directement les fichiers dans le workspace de ta session en lecture seule.

Review-le en mode hostile, sans supposer qu'il est correct. Cherche activement :
1. Différences visuelles ou régressions fonctionnelles entre les captures (espacements, alignements, badges, états vides, troncatures).
2. Code frontend résiduel : reste-t-il des imports orphelins, des composants React non nettoyés ou des références en dur dans le routeur ?
3. Manifest : permissions trop larges, routes non protégées, champs non conformes au schéma V2.
4. Gestion des erreurs : les états d'erreur réseau ou de timeout sont-ils gérés proprement par les blocs catalogue ?
5. Isolation : la suppression du dossier de ce plugin a-t-elle un impact sur d'autres plugins ?

Liste chaque problème avec fichier:ligne ou zone visuelle. Ne complimente pas le code.
```
