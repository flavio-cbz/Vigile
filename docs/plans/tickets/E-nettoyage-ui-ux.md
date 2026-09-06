# Chantier E — Nettoyage UI/UX (E1 à E5)

*Protocole partagé, règles d'exécution et anti-triche : voir [`00-protocole-commun.md`](00-protocole-commun.md).*

---

## Protocole Allégé pour ce Chantier (2 Sessions)

Ces 5 tickets sont des corrections d'interface et d'ergonomie à faible surface de risque technique (traductions, affichage de métadonnées, aide contextuelle, plafonnement de liste, retrait de raccourcis clavier), sans action destructrice.

Le protocole est donc optimisé en **2 sessions distinctes** :
1. **Session 1 & 2 fusionnées — Plan & Exécution** : L'agent prend connaissance de l'audit et des arbitrages validés, exécute le plan dans le workspace local, lance les tests, consigne dans `SESSION.md`, et **affiche obligatoirement le diff complet (`git diff HEAD`) dans un bloc markdown à la fin de sa réponse**.
2. **Session 3 — Review Diff** : Audit hostile neutre sur le diff seul (`git diff HEAD`).

---

## E1. Traductions Manquantes `node_detail.*` et Dotted Keys (Qualité +++)

**Outil / Modèle :** OpenCode + omo / Antigravity — EXEC **Muse Spark 1.2** (qualité +++ : zéro drift FR/EN, gestion fail-closed des clés) · Garde-fou standard.

> **Décisions qualité +++ figées** :
> - Locales cibles : `fr` et `en` uniquement (`i18n/index.ts`).
> - Suppression de l'utilisation de `defaultValue` trompeur : `translateWith(key)` doit retourner la clé brute si non trouvée, permettant une détection immédiate des manques.
> - Harmonisation des conventions de nommage : canonique `api.toast.rate_limit` (EN/FR unifié sans suffixe `_msg`).
> - Correction des 8 clés `node_detail.*` manquantes et des 30+ clés transverses manquantes (`plugins.kill_switch.*`, `common.*`, `metrics.disk.saturation.*`).

---

### Session 1 & 2 — Plan & Exécution (Fusionnés)

```markdown
Contexte : projet Vigile, ticket E1. Des clés de traduction i18n manquent ou ont dérivé entre le code TSX et les fichiers de locale `fr.ts` / `en.ts`.

Voici l'audit exhaustif validé pour le ticket E1 :

### 1. Clés `node_detail.*` prioritaires manquantes
- `node_detail.enrolled_chip_prefix` (Composant : `NodeDetailHeader.tsx`, chip Enregistré)
- `node_detail.hostname_chip_prefix` (Composant : `NodeDetailHeader.tsx`, chip Host)
- `node_detail.logs_lines_500` (Composant : `LogToolbar.tsx`, select lignes)
- `node_detail.logs_search_placeholder` (Composant : `LogToolbar.tsx`, champ recherche)
- `node_detail.logs_search_matches` (Composant : `LogToolbar.tsx`, compteur résultats)
- `node_detail.logs_copy` / `node_detail.logs_copied` (Composant : `LogToolbar.tsx`, bouton copie)
- `node_detail.logs_download` (Composant : `LogToolbar.tsx`, bouton téléchargement)

### 2. Clés transverses à harmoniser (FR et EN)
- `api.toast.rate_limit` (unifié, suppression des alias `rate_limit_msg`)
- `plugins.kill_switch.*` (12 clés complètes pour le dialogue et les statuts du coupe-circuit)
- `common.all`, `common.copied`, `common.no_results`, `common.reset`, `common.total`
- `metrics.disk.saturation.day`, `metrics.disk.saturation.today`

### 3. Plan d'action
1. Mettre à jour `frontend/src/i18n/fr.ts` avec toutes les clés manquantes en français soigné.
2. Mettre à jour `frontend/src/i18n/en.ts` avec la stricte parité des clés en anglais.
3. Vérifier les call-sites `t()` dans les composants pour supprimer les fallbacks `defaultValue` non pris en charge.
4. Lancer `npm run test` / `vitest` pour vérifier l'absence de régression.

Règles strictes d'exécution et anti-triche :
- Environnement : modifie directement les fichiers du workspace local avec tes outils d'édition intégrés et lance les tests dans ton terminal local.
- INTERDIT de modifier ou supprimer un test existant pour le faire passer.
- Ne supprime aucune clé existante sans vérification absolue qu'elle est morte partout.
- Clôture et sortie obligatoire du diff : à la fin de l'intervention, (1) documente ce qui a été réalisé en ajoutant une entrée à la fin de SESSION.md selon le format invariant, et (2) AFFICHE OBLIGATOIREMENT LE DIFF COMPLET (dans un bloc de code markdown ```diff contenant la sortie exacte de `git diff HEAD`) à la toute fin de ta réponse finale pour que l'opérateur puisse le copier directement vers la session de review.

Exécute uniquement le ticket E1.
```

---

### Session 3 — Review Diff (Audit Hostile)

```markdown
Voici le diff de l'implémentation du ticket E1 :
[colle le diff brut git diff HEAD]

Environnement : vérifie directement les fichiers dans le workspace de ta session en lecture seule.

Review-le en mode hostile, sans supposer qu'il est correct. Cherche activement :
1. Clé ajoutée dans une langue mais absente de l'autre (asymétrie FR/EN).
2. Clé brute `node_detail.xxx` ou `common.xxx` encore affichable dans un composant UI.
3. Erreur de syntaxe JSON / TS dans les dictionnaires (virgule manquante, clé dupliquée).
4. Traduction trompeuse ou contresens dans le contexte technique des serveurs.

Liste chaque problème avec fichier:ligne. Ne complimente pas le code.
```

---

## E2. Affichage de l'IP du Serveur en En-tête Node Detail (Qualité +++)

**Outil / Modèle :** OpenCode + omo / Antigravity — EXEC **Muse Spark 1.2** · Garde-fou standard.

> **Décisions qualité +++ figées** :
> - Stockage persistant en base : ajout de la colonne `last_ip TEXT` dans la table `nodes` (migration idempotente dans `migrations.py`).
> - Mise à jour de `last_ip` lors de l'enrollment (`_run_enrollment`), de la reconnexion (`_run_reconnect`) et des heartbeats.
> - Prise en compte des proxys de confiance (`trusted_proxies` via `X-Forwarded-For`), sinon adresse `websocket.client.host`.
> - Exposition via `NodeResponse` (`last_ip` / `ip_address`) et typage frontend `NodeRecord`.
> - Affichage d'un 5ème chip dans `NodeDetailHeader.tsx` avec l'icône Lucide `Network`, placé entre Hostname et Version.
> - Gestion des cas limites : masquage propre si IP inconnue, affichage de la dernière IP connue si le nœud est offline (utile pour debug SSH), gestion IPv4 et IPv6 entre crochets.

---

### Session 1 & 2 — Plan & Exécution (Fusionnés)

```markdown
Contexte : projet Vigile, ticket E2. L'adresse IP du serveur n'est pas affichée dans la carte d'en-tête du détail du nœud.

Voici le plan validé pour le ticket E2 :

### 1. Backend & Base de données
- Migration DB : `ALTER TABLE nodes ADD COLUMN last_ip TEXT` dans `master/db/migrations.py`.
- Enregistrement : persister l'adresse IP distante lors du handshake WebSocket dans `master/ws/worker_handler.py`.
- Modèle API : ajouter `last_ip: Optional[str] = None` dans `NodeResponse` (`master/api/nodes_models.py`) et mapper dans `_node_to_response`.

### 2. Frontend
- Types : étendre `NodeRecord` dans `frontend/src/components/node-detail/types.ts` avec `last_ip?: string | null` (et alias `ip_address`).
- Composant `NodeDetailHeader.tsx` :
  - Ajouter le chip IP : icône `<Network className="w-3.5 h-3.5" />`, label i18n `node_detail.ip_chip_prefix`, valeur en police monospace.
  - Masquer le chip si aucune IP n'a jamais été enregistrée.
  - Afficher la dernière IP connue même si le nœud est déconnecté.

Règles strictes d'exécution et anti-triche :
- Environnement : modifie directement les fichiers du workspace local avec tes outils d'édition intégrés et lance les tests dans ton terminal local.
- INTERDIT de modifier ou supprimer un test existant pour le faire passer.
- Gère l'absence d'IP proprement (aucun texte "undefined" ou badge vide).
- Clôture et sortie obligatoire du diff : à la fin de l'intervention, (1) documente ce qui a été réalisé en ajoutant une entrée à la fin de SESSION.md selon le format invariant, et (2) AFFICHE OBLIGATOIREMENT LE DIFF COMPLET (dans un bloc de code markdown ```diff contenant la sortie exacte de `git diff HEAD`) à la toute fin de ta réponse finale pour que l'opérateur puisse le copier directement vers la session de review.

Exécute uniquement le ticket E2.
```

---

### Session 3 — Review Diff (Audit Hostile)

```markdown
Voici le diff de l'implémentation du ticket E2 :
[colle le diff brut git diff HEAD]

Environnement : vérifie directement les fichiers dans le workspace de ta session en lecture seule.

Review-le en mode hostile, sans supposer qu'il est correct. Cherche activement :
1. Cas limites non gérés : IPv6 avec port, nœud jamais connecté, champ `last_ip` null.
2. Fuite de clé de traduction : `node_detail.ip_chip_prefix` est-il bien déclaré dans `fr.ts` et `en.ts` ?
3. Respect des proxys : l'IP enregistrée prend-elle bien en compte `trusted_proxies` ou lit-elle aveuglément l'IP de la socket locale ?
4. Migration DB : l'ajout de colonne est-il idempotent (pas de plantage si la colonne existe déjà) ?

Liste chaque problème avec fichier:ligne. Ne complimente pas le code.
```

---

## E3. Jauges CPU/RAM/DISK : Remplacement du "30j" par une Aide Contextuelle (Qualité +++)

**Outil / Modèle :** OpenCode + omo / Antigravity — EXEC **Muse Spark 1.2** · Garde-fou standard.

> **Décisions qualité +++ figées** :
> - Remplacement du texte "30j" ambigu par un composant d'aide réutilisable du catalogue : `HelpTooltip.tsx` (`registerBlock('help-tooltip')`).
> - Affichage des seuils RÉELS configurés dans le backend ([`master/core/alert_engine.py`](file:///home/flavio/Docker-Compose/vigile/master/core/alert_engine.py) `BUILTIN_THRESHOLDS`) :
>   - CPU : Warning > 80%, Critical > 95%, Résolu ≤ 60%.
>   - RAM : Warning > 85%, Critical > 95%, Résolu ≤ 80%.
>   - DISK : Warning > 85%, Critical > 95%, Résolu ≤ 80%.
> - Mention de la nuance adaptative : explication claire que si le nœud a ≥ 24h d'historique (`TARGET_OBSERVATION_HOURS`), les seuils adaptatifs p75/p90/p99 sont appliqués.
> - Accessibilité : trigger sous forme de popover accessible au clic/clavier (`role="dialog"` / `aria-expanded`), fermeture via Échap ou clic extérieur.
> - Conservation de l'extrapolation utile `+7j / +30j` dans le tiroir d'analyse détaillée de `DiskMountCards.tsx`.

---

### Session 1 & 2 — Plan & Exécution (Fusionnés)

```markdown
Contexte : projet Vigile, ticket E3. Le libellé "30j" à côté des jauges CPU/RAM/DISK est opaque et doit être remplacé par un point d'interrogation "?" ouvrant une aide contextuelle expliquant ce que mesure la jauge, les seuils d'alerte réels et leurs conséquences.

Voici le plan validé pour le ticket E3 :

### 1. Composant Catalogue `HelpTooltip`
- Créer `frontend/src/components/blocks/HelpTooltip.tsx` (export `HelpTooltip` et primitif `HelpTooltipIcon`).
- Enregistrer dans `frontend/src/components/blocks/registry.ts` (`help-tooltip`).
- Props : `title`, `description`, `thresholds: { warning, critical, resolve, unit }`, `consequence`.
- Accessibilité : bouton trigger accessible, popover click, support touche Escape et clic extérieur.

### 2. Intégration dans les cartes de métriques
- Dans `MetricsOverviewCards.tsx` : intégrer `HelpTooltip` à côté du titre de chaque jauge (CPU, RAM, STORAGE).
- Fournir les seuils réels de `BUILTIN_THRESHOLDS` (`alert_engine.py`).
- Traductions i18n FR/EN complètes sous `metrics.help.*`.

Règles strictes d'exécution et anti-triche :
- Environnement : modifie directement les fichiers du workspace local avec tes outils d'édition intégrés et lance les tests dans ton terminal local.
- INTERDIT de modifier ou supprimer un test existant pour le faire passer.
- Les seuils affichés dans l'aide doivent correspondre exactement aux seuils de l'alert engine (ne pas inventer de seuils).
- Accessibilité obligatoire : focus clavier, aria-describedby, fermeture Échap.
- Clôture et sortie obligatoire du diff : à la fin de l'intervention, (1) documente ce qui a été réalisé en ajoutant une entrée à la fin de SESSION.md selon le format invariant, et (2) AFFICHE OBLIGATOIREMENT LE DIFF COMPLET (dans un bloc de code markdown ```diff contenant la sortie exacte de `git diff HEAD`) à la toute fin de ta réponse finale pour que l'opérateur puisse le copier directement vers la session de review.

Exécute uniquement le ticket E3.
```

---

### Session 3 — Review Diff (Audit Hostile)

```markdown
Voici le diff de l'implémentation du ticket E3 :
[colle le diff brut git diff HEAD]

Environnement : vérifie directement les fichiers dans le workspace de ta session en lecture seule.

Review-le en mode hostile, sans supposer qu'il est correct. Cherche activement :
1. Seuils erronés : les seuils documentés dans l'aide correspondent-ils rigoureusement à `alert_engine.py` ?
2. Couplage abusif : le composant `HelpTooltip` est-il générique et réutilisable ou codé en dur pour les seules 3 métriques ?
3. Accessibilité défaillante : le tooltip est-il utilisable au clavier et sur mobile (click/tap) ?
4. Le libellé opaque "30j" a-t-il bien été supprimé des cartes principales ?

Liste chaque problème avec fichier:ligne. Ne complimente pas le code.
```

---

## E4. Plafonnement des Cartes "Actions Proposées" (Qualité +++)

**Outil / Modèle :** OpenCode + omo / Antigravity — EXEC **Muse Spark 1.2** · Garde-fou standard.

> **Décisions qualité +++ figées** :
> - Plafonnement par défaut : **5 cartes maximum** sur le Dashboard (`ProposalsSection.tsx`) et **6 cartes maximum** sur la page dédiée `/proposals` (`ProposalsPage.tsx`).
> - Tri prioritaire strict : `risk_level DESC` (`CRITICAL > HIGH > MEDIUM = WARNING > LOW > OK`) puis `created_at DESC` (plus récent d'abord à risque égal) puis `updated_at DESC`.
> - Mécanisme d'expansion progressif :
>   - Dashboard : bouton "Afficher 5 sur N — Voir plus (+5)" + bouton d'en-tête "Voir tout →" redirigeant vers `/proposals`.
>   - ProposalsPage : pagination/expansion par incréments de 6 par zone (À valider, En cours, Historique).
> - Gestion des cas limites : masquage propre si 0 action en attente, affichage sans bouton d'expansion si `<= 5` actions.

---

### Session 1 & 2 — Plan & Exécution (Fusionnés)

```markdown
Contexte : projet Vigile, ticket E4. Trop de cartes de propositions d'actions sont affichées simultanément sur le Dashboard en cas de flux important, saturant la page.

Voici le plan validé pour le ticket E4 :

### 1. Tri prioritaire frontend
- Trier les propositions reçues par niveau de risque décroissant (`risk_level`), puis par date décroissante (`created_at`).

### 2. Dashboard (`ProposalsSection.tsx`)
- Constante `PROPOSALS_DASHBOARD_LIMIT = 5`.
- Afficher les 5 premières cartes triées.
- Si le total dépasse 5 : afficher le bouton "Voir plus (+5)" et brancher le `onSeeAll` de `SwimLane` vers `/proposals`.
- Si 0 proposition : masquer la section (`return null`).

### 3. Page dédiée (`ProposalsPage.tsx`)
- Appliquer le tri par risque et date sur chaque zone.
- Limiter initialement à 6 cartes par zone avec bouton "Voir plus (X restants)".

Règles strictes d'exécution et anti-triche :
- Environnement : modifie directement les fichiers du workspace local avec tes outils d'édition intégrés et lance les tests dans ton terminal local.
- INTERDIT de modifier ou supprimer un test existant pour le faire passer.
- Le compteur d'actions restantes doit toujours être exact (ex: "+ 7 autres").
- Clôture et sortie obligatoire du diff : à la fin de l'intervention, (1) documente ce qui a été réalisé en ajoutant une entrée à la fin de SESSION.md selon le format invariant, et (2) AFFICHE OBLIGATOIREMENT LE DIFF COMPLET (dans un bloc de code markdown ```diff contenant la sortie exacte de `git diff HEAD`) à la toute fin de ta réponse finale pour que l'opérateur puisse le copier directement vers la session de review.

Exécute uniquement le ticket E4.
```

---

### Session 3 — Review Diff (Audit Hostile)

```markdown
Voici le diff de l'implémentation du ticket E4 :
[colle le diff brut git diff HEAD]

Environnement : vérifie directement les fichiers dans le workspace de ta session en lecture seule.

Review-le en mode hostile, sans supposer qu'il est correct. Cherche activement :
1. Masquage silencieux d'actions critiques : une action CRITICAL peut-elle se retrouver cachée sous le seuil par erreur de tri ?
2. Compteur inexact ou état vide cassé ("+ 0 autres", section vide visible).
3. Perte de réactivité : lors de l'approbation ou du rejet d'une proposition, la liste se réactualise-t-elle correctement ?
4. Comportement du "Voir plus" : étend-il la liste sans recharger toute la page ?

Liste chaque problème avec fichier:ligne. Ne complimente pas le code.
```

---

## E5. Retrait de la Navigation Clavier Parasite dans les Logs (Qualité +++)

**Outil / Modèle :** OpenCode + omo / Antigravity — EXEC **Muse Spark 1.2** · Garde-fou standard.

> **Décisions qualité +++ figées (Variante A validée)** :
> - **Raccourcis retirés** : `/` (focus sur champ de recherche) et `s` / `S` (ouverture de la modale de sélection de source) dans `NodeDetailLogsTab.tsx`.
> - **Branche morte purgée** : suppression du `preventDefault()` sur la frappe `s` lorsque la modale est fermée dans `LogSourceModal.tsx`.
> - **Raccourci conservé** : conservation de la touche `Escape` pour fermer `LogSourceModal.tsx` (standard d'accessibilité des modales).
> - **Nettoyage visuel** : suppression des badges `/` et `S` dans l'interface, conservation du badge `ESC` sur la modale.
> - **Zéro impact global** : les raccourcis globaux de l'application (`Cmd/Ctrl+K` pour la CommandPalette, `Escape` pour le CopilotPanel) restent 100% fonctionnels et isolés.

---

### Session 1 & 2 — Plan & Exécution (Fusionnés)

```markdown
Contexte : projet Vigile, ticket E5. Les raccourcis clavier `/` et `s` enregistrés globalement sur la fenêtre lors de l'affichage de l'onglet logs interfèrent avec la saisie normale et doivent être retirés.

Voici le plan validé pour le ticket E5 :

### 1. `NodeDetailLogsTab.tsx`
- Supprimer l'écouteur d'événement `window.addEventListener('keydown', handleKeyDown)`.
- Supprimer le badge visuel `/` dans le champ de recherche.

### 2. `LogSourceBar.tsx`
- Supprimer le badge visuel `S` à côté du bouton des sources.

### 3. `LogSourceModal.tsx`
- Conserver uniquement la gestion de la touche `Escape` pour fermer la modale.
- Supprimer le bloc interceptant la touche `s` quand la modale est fermée.

### 4. Vérifications transverses
- S'assurer que les clics de souris et sélections restent 100% fonctionnels.
- Vérifier que `CommandPalette` (`Cmd+K`) et `CopilotPanel` (`Escape`) fonctionnent sans perturbation.

Règles strictes d'exécution et anti-triche :
- Environnement : modifie directement les fichiers du workspace local avec tes outils d'édition intégrés et lance les tests dans ton terminal local.
- INTERDIT de modifier ou supprimer un test existant pour le faire passer.
- Ne touche à aucun raccourci clavier en dehors des logs.
- Clôture et sortie obligatoire du diff : à la fin de l'intervention, (1) documente ce qui a été réalisé en ajoutant une entrée à la fin de SESSION.md selon le format invariant, et (2) AFFICHE OBLIGATOIREMENT LE DIFF COMPLET (dans un bloc de code markdown ```diff contenant la sortie exacte de `git diff HEAD`) à la toute fin de ta réponse finale pour que l'opérateur puisse le copier directement vers la session de review.

Exécute uniquement le ticket E5.
```

---

### Session 3 — Review Diff (Audit Hostile)

```markdown
Voici le diff de l'implémentation du ticket E5 :
[colle le diff brut git diff HEAD]

Environnement : vérifie directement les fichiers dans le workspace de ta session en lecture seule.

Review-le en mode hostile, sans supposer qu'il est correct. Cherche activement :
1. Écouteur d'événement orphelin : reste-t-il un `addEventListener` sans cleanup `removeEventListener` ?
2. Régression sur la souris : la sélection de sources ou le filtrage de logs fonctionne-t-il parfaitement au clic ?
3. Raccourci global cassé : `CommandPalette` (`Cmd+K`) et `Escape` modales continuent-ils de fonctionner ?
4. Références visuelles mortes ou badges oubliés dans l'UI.

Liste chaque problème avec fichier:ligne. Ne complimente pas le code.
```
