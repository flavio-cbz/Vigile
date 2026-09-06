# Chantier F1 — Dette Technique : Unification des Routes API Backend

*Protocole partagé, règles d'exécution et anti-triche : voir [`00-protocole-commun.md`](00-protocole-commun.md).*

---

## F1. Audit et Unification des Routes API Backend (Qualité +++)

**Outil / Modèle :** OpenCode + omo / Antigravity — AUDIT S0 **MiMo-V2.5** (1M ctx, traversée globale en lecture seule) + PLAN S1 **Muse Spark 1.2** + EXEC S2 **Muse Spark 1.2** · Garde-fou standard.

> **Objectif & Cadrage** :
> Les routes de l'API backend souffrent de duplications et d'incohérences de nommage / gestion d'erreurs suite aux itérations successives.
> Le ticket suit un protocole en 5 étapes strictes :
> 1. **Session 0 — Audit exhaustif** (lecture seule, cartographie complète de toutes les routes).
> 2. **Session 1 — Plan de refactorisation** (ordonnancement sans casser les consommateurs).
> 3. **Session 1.5 — Vérification du plan** (Momus / Oracle).
> 4. **Session 2 — Exécution du refactor**.
> 5. **Session 3 — Review du diff**.

---

### Session 0 — Audit Exhaustif (Lecture Seule Stricte)

```markdown
Contexte : projet Vigile, ticket F1. Les routes de l'API backend présentent des doublons de logique, des structures de réponses divergentes et des incohérences de conventions.

Environnement : lis et explore directement les fichiers du workspace local via ta session en lecture seule stricte. Aucun fichier ne doit être modifié.

Produis uniquement un audit structuré :
1. L'inventaire exhaustif de toutes les routes API déclarées dans `master/api/` et dans les plugins : méthode HTTP, path, handler, rôle requis, fichier:ligne.
2. La liste des doublons identifiés : routes effectuant la même opération, handlers quasi-identiques, logique dupliquée.
3. Les incohérences : divergence dans la structure des erreurs (detail str vs dict), formats de timestamps (epoch vs ISO), conventions de nommage (/kebab-case vs /snake_case).
4. Pour chaque doublon : proposition tranchée (fusionner, déprécier, ou conserver séparé) avec justification technique d'impact.
5. Une proposition de convention canonique d'API REST pour Vigile à documenter.

J'attends ton audit, je le valide, puis nous ouvrirons la session de planification.
```

---

### Session 1 — Plan de Refactorisation

```markdown
Voici l'audit des routes validé :
[colle l'audit validé issu de la Session 0]

Environnement : vérifie directement les fichiers dans le workspace local en lecture seule.

Ne code rien. Produis uniquement :
1. Un plan de refactorisation ordonné, route par route, garantissant qu'aucun appel frontend, plugin ou webhook ne soit cassé entre deux étapes.
2. Pour chaque route fusionnée ou renommée : liste des consommateurs exacts et stratégie de transition (redirection, alias déprécié temporaire si nécessaire).
3. Les nouveaux schémas Pydantic unifiés à introduire.
4. Les tests d'intégration et unitaires à mettre à jour ou ajouter.
5. Tes hypothèses, que je dois valider.

J'attends ta réponse, je la valide, puis nous passerons à la vérification du plan.
```

---

### Session 1.5 — Vérification Plan (Momus / Oracle — Qualité Maximale)

```markdown
Agent : Momus (Oh My OpenCode) / Oracle — Critique de plan de refactorisation API.

Consigne qualité NON NÉGOCIABLE :
- Analyse approfondie sans compromis de rapidité.
- Vérifie minutieusement qu'aucun breaking change n'est introduit pour le frontend ou les plugins existants.

Mission : critique le plan fichier par fichier. Cherche les routes oubliées, les ruptures de contrat DTO silencieuses et les risques de régressions sur l'authentification/RBAC.
Verdict attendu : GO / GO avec corrections mineures / REWORK.
```

---

### Session 2 — Exécution

```markdown
Voici le plan validé pour le ticket F1 :
[colle le plan validé]

Règles strictes d'exécution et anti-triche :
- Environnement : modifie directement les fichiers du workspace local avec tes outils d'édition intégrés et lance la suite complète de tests dans ton terminal local.
- INTERDIT de modifier ou supprimer un test existant pour masquer une régression. Si un test échoue après une modification de route, corrige le code du handler ou du client, pas l'assertion du test.
- Documente la convention canonique d'API au fur et à mesure dans `docs/architecture/` ou `AGENTS.md`.
- Si tu découvres un doublon imprévu non listé dans l'audit, ne le fusionne pas à la volée : signale-le et poursuis le plan validé.
- Zéro `as any`, typage strict Pydantic v2 et FastAPI dependencies (`Depends`).
- Clôture et sortie obligatoire du diff : à la fin de l'intervention, (1) documente ce qui a été réalisé en ajoutant une entrée à la fin de SESSION.md selon le format invariant, et (2) AFFICHE OBLIGATOIREMENT LE DIFF COMPLET (dans un bloc de code markdown ```diff contenant la sortie exacte de `git diff HEAD`) à la toute fin de ta réponse finale pour que l'opérateur puisse le copier directement vers la session de review.

Exécute uniquement le ticket F1.
```

---

### Session 3 — Review Diff (Audit Hostile)

```markdown
Voici le diff du refactor d'API du ticket F1 :
[colle le diff brut git diff HEAD]

Environnement : vérifie directement les fichiers dans le workspace de ta session en lecture seule.

Review-le en mode hostile, sans supposer qu'il est correct. Cherche activement :
1. Breaking change silencieux : une ancienne route a-t-elle été supprimée alors qu'un composant frontend l'appelle encore ?
2. Structure de réponse altérée sans adaptation du client TSX correspondant.
3. Faille d'autorisation : une route unifiée a-t-elle perdu sa dépendance de rôle RBAC (`require_role`, `_operator_plus`) ?
4. Duplication simplement déplacée plutôt que réellement éliminée.
5. Gestion des exceptions : les erreurs 400/404/422/500 respectent-elles rigoureusement la convention unifiée ?

Liste chaque problème avec fichier:ligne. Ne complimente pas le code.
```
