# Chantier C1 — Disques : Choix du Point de Montage à Analyser

*Protocole partagé, règles d'exécution et anti-triche : voir [`00-protocole-commun.md`](00-protocole-commun.md).*

---

## C1. Choix du Point de Montage dans l'Analyse Disque (Qualité +++)

**Outil / Modèle :** OpenCode + omo / Antigravity — PLAN **MiMo-V2.5** (1M ctx) + EXEC **Muse Spark 1.2** · Garde-fou standard.

> **Décisions qualité +++ figées** :
> - Cache multi-path par paire `(node_id, path)` dans une table dédiée `disk_scans_cache(node_id, path, scan_json, scanned_at, PRIMARY KEY(node_id, path))` — évite d'alourdir la table `nodes`.
> - Normalisation backend et frontend tolérant à la fois les listes plates de chaînes `["/", "/mnt/data"]` et les objets `[{mount_point: "..."}]`.
> - Mémorisation persistante dans `localStorage` (`vigile_disk_mount_${nodeId}`) avec fallback `sessionStorage` si indisponible.
> - Fallback automatique sur `validMounts[0] ?? '/'` si le point de montage sélectionné disparaît (disque démonté ou déconnecté).
> - Gestion sécurisée des espaces et caractères spéciaux via `encodeURIComponent` côté API et validation contre la liste des montages détectés côté backend (fail-closed anti-traversal).

---

### Session 1 — Plan

```markdown
Contexte : projet Vigile, ticket C1. Seule la racine "/" est actuellement analysable dans l'arborescence treemap de l'analyse disque, aucune sélection n'est possible.
Attendu : la liste des points de montage détectés sur le nœud est proposée dans un sélecteur ; changer de point de montage relance l'analyse ou lit le cache correspondant ; la sélection est mémorisée de manière persistante par nœud.

Environnement : lis et explore directement les fichiers du workspace local via ta session en lecture seule stricte.

Ne code rien. Produis uniquement :
1. L'origine des points de montage détectés (champs remontés par le worker, format stocké dans `cached_disks_json`, endpoints concernés) et le câblage actuel sur "/".
2. Un plan ordonné, fichier par fichier : adaptation de la table/cache backend, normalisation des formats, composant sélecteur frontend et persistance de session.
3. Les garde-fous de sécurité : protection contre le path traversal, gestion des espaces/caractères spéciaux, et disparition d'un point de montage.
4. Tes hypothèses, que je dois valider.

J'attends ta réponse, je la valide, puis nous passerons à la vérification du plan.
```

---

### Session 1.5 — Vérification Plan (Momus / Oracle — Qualité Maximale)

```markdown
Agent : Momus (Oh My OpenCode) / Oracle — Critique de plan.

Consigne qualité NON NÉGOCIABLE :
- Analyse exhaustive du plan fichier par fichier, sans complaisance.
- Vérifie la cohérence du cache multi-path, l'absence de régression sur le drill-down treemap et la validation stricte des chemins côté backend.

Mission : critique le plan. Cherche les vulnérabilités de path traversal, les risques d'écrasement du localStorage lors d'un drill-down, et la gestion des montages avec caractères spéciaux.
Verdict attendu : GO / GO avec corrections mineures / REWORK.
```

---

### Session 2 — Exécution

```markdown
Voici le plan validé pour le ticket C1 :

### 1. Diagnostic & Cause racine
1. Cache non dimensionné par path : `get_cached_disk_scan(db, node_id)` ne filtre pas par `path`. Le scan de `/` renvoie son cache (TTL 5 min) pour n'importe quel point de montage demandé.
2. Divergence de format sur `cached_disks_json` : `set_node_disk_mounts` stocke une liste de strings `["/", "/mnt/data"]`, alors que `NodeDetail.tsx` accède à `.mount_point` (attente d'objets).

### 2. Plan d'exécution ordonné
#### Étape 1 — Backend : Cache multi-path (`master/db/disk_scan_cache.py` & migrations)
- Créer/adapter le cache pour indexer par `(node_id, path)` dans la table dédiée `disk_scans_cache`.
- Mettre à jour `get_cached_disk_scan(db, node_id, path)` et `set_cached_disk_scan(db, node_id, path, json_data, timestamp)`.
- Dans `master/api/nodes.py` (`get_disk_scan`), passer le `path` au cache helper pour isoler les scans entre partitions.
- Valider le `path` demandé contre les points de montage réels détectés sur le nœud (fail-closed).
- Unifier `get_node_disk_mounts` / `set_node_disk_mounts` pour supporter les deux formats (strings et objets).

#### Étape 2 — Frontend : Normalisation des mounts (`frontend/src/pages/NodeDetail.tsx`)
- Sécuriser l'extraction des points de montage :
  const parsed = JSON.parse(node.cached_disks_json || '[]');
  const diskMounts = Array.isArray(parsed)
    ? parsed.map((d) => (typeof d === 'string' ? d : d.mount_point)).filter(Boolean)
    : [];

#### Étape 3 — Frontend : Mémorisation persistante (`NodeDetailDiskTab.tsx`)
- Initialiser le point de montage sélectionné depuis `localStorage` (`vigile_disk_mount_${nodeId}`) avec fallback `sessionStorage`.
- Mémoriser le choix lors du changement dans le `<select>`.
- Ne pas écraser la sélection de session lors d'un simple drill-down dans l'arborescence (seuls les points de montage racines modifient le storage).

#### Étape 4 — Frontend : Garde-fous et états limites (`NodeDetailDiskTab.tsx`)
- Si `validMounts` change et que `selectedPath` n'existe plus, fallback immédiat sur `validMounts[0] ?? '/'`.
- Encodage systématique des chemins via `encodeURIComponent`.

Règles strictes d'exécution et anti-triche :
- Environnement : modifie directement les fichiers du workspace local avec tes outils d'édition intégrés et lance les tests dans ton terminal local.
- INTERDIT de modifier ou supprimer un test existant pour le faire passer.
- Zéro `as any`, typage strict TypeScript (`string[]`, `DiskScanResult`).
- Zéro régression sur la visualisation treemap D3 (`d3-hierarchy treemapSquarify`).
- Clôture et sortie obligatoire du diff : à la fin de l'intervention, (1) documente ce qui a été réalisé en ajoutant une entrée à la fin de SESSION.md selon le format invariant, et (2) AFFICHE OBLIGATOIREMENT LE DIFF COMPLET (dans un bloc de code markdown ```diff contenant la sortie exacte de `git diff HEAD`) à la toute fin de ta réponse finale pour que l'opérateur puisse le copier directement vers la session de review.

Exécute uniquement le ticket C1.
```

---

### Session 3 — Review Diff (Audit Hostile)

```markdown
Voici le diff de l'implémentation du ticket C1 :
[colle le diff brut git diff HEAD]

Environnement : vérifie directement les fichiers dans le workspace de ta session en lecture seule.

Review-le en mode hostile, sans supposer qu'il est correct. Cherche activement :
1. Injection ou Path Traversal via le paramètre `path` envoyé au backend : le chemin est-il validé contre la liste des montages réels du nœud avant d'être transmis au worker ?
2. Permission denied sur un point de montage non accessible : que voit l'utilisateur (bannière explicite ou crash treemap) ?
3. Conflit de storage entre différents nœuds : la clé de persistance est-elle bien scopée par `nodeId` ?
4. Drill-down treemap : le clic sur un sous-dossier écrase-t-il par erreur le point de montage racine sélectionné ?
5. Données corrompues en cache : le cache `(node_id, path)` est-il invalidé proprement lors d'un `force=true` ?

Liste chaque problème avec fichier:ligne. Ne complimente pas le code.
```
