# Chantier B — Services (B4, B5)

*Protocole partagé, règles d'exécution et anti-triche : voir [`00-protocole-commun.md`](00-protocole-commun.md).*

---

## B4. Services : optimisation du temps de chargement (Qualité +++)

**Outil / Modèle :** OpenCode + omo / Antigravity — PLAN **Muse Spark 1.2** + EXEC **Muse Spark 1.2** (qualité +++ : p95 + stale guard exigent un raisonnement fin, Lightning écarté) · Garde-fou standard · Prérequis : B1 mergé.

> **Décisions qualité +++ figées** :
> - Mesure locale et prod p95 < 2s pour `systemctl list-units --type=service --all --plain` ; parsing regex `^[a-zA-Z0-9@._-]+\.service$` avec gestion de l'indicateur d'état `●` et limite 500 unités.
> - Timeout aligné : Worker 10s (`commandTimeout`), Master 15s (`force_refresh`) / 10s (collecteur cold start).
> - Parallélisation multi-nœuds avec `asyncio.Semaphore(5)` + `gather(return_exceptions=True)` pour qu'un timeout n'écrase pas le cache des autres.
> - Cache en DB avec timestamp `cached_services_at REAL` + contrat `{services, count, cached_at, stale, errors[]}` TTL 300s, méthode `is_stale()` exposée.
> - Auto-refresh SWR `revalidateInterval: 30_000` côté frontend avec conservation du `cached_at` serveur.
> - Fréquence de collecte en tâche de fond : **30s + jitter ±10s** (`service_collector_loop`).

---

### Session 1 — Plan

```markdown
Contexte : projet Vigile, ticket B4. La page Services met trop de temps à charger. Solution : appliquer le pattern précalcul + live de B1 à la collecte de statuts de services. Le statut affiché doit provenir d'un cache précalculé rafraîchi périodiquement, pas d'une requête synchrone au chargement de la page.

Environnement : lis et explore directement les fichiers du workspace local via ta session en lecture seule stricte.

Ne code rien. Produis uniquement :
1. Un plan ordonné, fichier par fichier, qui applique le pattern B1 au plugin services : job de fond, table/cache en base, contrat API et frontend SWR.
2. Le refresh_interval proposé pour les statuts de services, avec sa justification de charge/fraîcheur.
3. Le protocole précis de mesure du temps de chargement avant/après (p95 cible < 100ms sur cache hit).
4. Tes hypothèses sur la collecte actuelle des statuts (systemd, parsing, timeouts, gestion des erreurs), que je dois valider.

J'attends ta réponse, je la valide, puis nous passerons à la vérification du plan.
```

---

### Session 1.5 — Vérification Plan (Momus / Oracle — Qualité Maximale)

```markdown
Agent : Momus (Oh My OpenCode) / Oracle — Critique de plan.

Consigne qualité NON NÉGOCIABLE :
- Pour CHAQUE choix d'évaluation (profondeur d'analyse, exhaustivité du scan, rigueur des vérifications, nombre d'angles morts inspectés), prends le choix qualité +++ sans limite de temps ni de coût.
- INTERDIT de choisir l'option la plus rapide ou un compromis superficiel.
- Privilégie systématiquement la vérification la plus approfondie, la plus stricte et la plus exhaustive.

Mission : critique le plan fichier par fichier, sans coder. Liste chaque problème avec fichier:ligne, faille, hypothèse fragile, angle mort (ex: thundering herd, lock DB, gestion de nœud offline, formatage systemd exotique). Ne complimente pas.
Verdict attendu : GO / GO avec corrections mineures / REWORK — avec liste des corrections bloquantes avant EXEC.
```

---

### Session 2 — Exécution

```markdown
Voici le plan validé pour le ticket B4 :

### Mesure du temps de chargement (Avant / Après)

#### Avant (baseline actuel)
1. Mesure navigateur (DevTools Network) : `/api/plugins/systemd/services` -> Attendu : 1.5s - 4s
2. Mesure backend : logs master -> durée handler LIST_SERVICES (800ms - 3s)
3. Script automatisé :
   curl -w "@curl-format.txt" -H "Authorization: Bearer $TOKEN" \
     "https://vigile.youcloud.ovh/api/nodes/<node_id>/services"

#### Après (avec cache & précalcul)
1. Cache hit : API lit DB uniquement -> 10-50ms
2. Frontend SWR affiche instantanément avec indicateur de fraîcheur
3. Mesure comparative :
   for i in {1..10}; do 
     curl -s -w "%{time_total}\n" -o /dev/null -H "Authorization: Bearer $TOKEN" \
       "https://vigile.youcloud.ovh/api/nodes/<node_id>/services?force_refresh=false"
   done
Métrique cible : p95 < 100ms sur cache hit.

### Hypothèses techniques et cadrage validés (Qualité +++)
- H1 : Parsing systemctl défensif : `--no-legend --plain --all` + regex `^[a-zA-Z0-9@._-]+\.service$` + prise en compte du caractère bullet `●` (fields[1]=name) + cap 500 units.
- H2 : Worker timeout 10s, Master timeout 15s sur force_refresh / 10s sur collecteur.
- H3 : Parsing Go fiable avec `strings.Fields`.
- H4 : Collecte multi-nœuds avec `asyncio.Semaphore(5)` et `asyncio.gather(return_exceptions=True)`.
- H5 : Cache persistant avec colonne/table dédiée et timestamp `cached_services_at REAL`, payload `{services, count, cached_at, stale, errors[]}`.
- H6 : Frontend SWR avec `revalidateInterval: 30_000` et affichage de la fraîcheur ("Dernière mise à jour il y a Xs").
- H7 : Gestion fail-safe : en cas d'erreur worker, conserver le dernier cache valide en marquant `stale: true`.
- H8 : Intervalle de collecte : 30s + jitter ±10s.

Règles strictes d'exécution et anti-triche :
- Environnement : modifie directement les fichiers du workspace local avec tes outils d'édition intégrés et lance les commandes de test dans ton terminal local.
- INTERDIT de modifier ou supprimer un test existant pour le faire passer. Si un test existant échoue, corrige ton code.
- Zéro `as any`, typage strict TypeScript et annotations complètes Python.
- Zéro erreur avalée (`except: pass` interdit).
- La page doit afficher la fraîcheur réelle de la donnée ("Dernière mise à jour il y a Xs").
- Aucune action destructrice (ce ticket est lecture seule côté services).
- Si tu rencontres une décision non couverte par le plan, arrête-toi et demande.
- Clôture et sortie obligatoire du diff : à la fin de l'intervention, (1) documente ce qui a été réalisé en ajoutant une entrée à la fin de SESSION.md selon le format invariant, et (2) AFFICHE OBLIGATOIREMENT LE DIFF COMPLET (dans un bloc de code markdown ```diff contenant la sortie exacte de `git diff HEAD`) à la toute fin de ta réponse finale pour que l'opérateur puisse le copier directement vers la session de review.

Exécute uniquement le ticket B4.
```

---

### Session 3 — Review Diff (Audit Hostile)

```markdown
Voici le diff de l'implémentation du ticket B4 :
[colle le diff brut git diff HEAD]

Environnement : vérifie directement les fichiers dans le workspace de ta session en lecture seule.

Review-le en mode hostile, sans supposer qu'il est correct. Cherche activement :
1. Requête synchrone résiduelle au worker lors du chargement nominal de la page (le bug d'origine est-il vraiment résolu ?).
2. Cache stale non signalé : un cache vieux de 10 minutes est-il affiché comme frais sans avertissement ?
3. Thundering herd : que se passe-t-il si 10 clients ouvrent la page en même temps ? Y a-t-il un lock ou un sémaphore ?
4. Défaillance du worker : que voit l'utilisateur en cas de timeout ou de crash ? L'ancien cache est-il préservé avec `stale: true` ?
5. Déviation par rapport au pattern B1 documenté.
6. Tests : y a-t-il eu des tests modifiés ou affaiblis ?

Liste chaque problème avec fichier:ligne. Ne complimente pas le code.
```

---

## B5. Suppression des boutons refresh/recalcul manuels (Qualité +++)

**Outil / Modèle :** OpenCode + omo / Antigravity — PLAN **Muse Spark 1.2** + EXEC **Muse Spark 1.2** · Garde-fou standard · Prérequis : B1 mergé.

> **Décisions qualité +++ figées (Audit 19 boutons)** :
> - **6 boutons impactés** :
>   - *Suppressions sèches (3)* : `#1` `MetricsOverview.tsx:167` (polling 20s et `lastRefreshed` déjà actifs), `#7` `NodeDetailLogsTab.tsx:211` (polling 15s et badge LIVE actifs), `#8` `LogToolbar.tsx:181` (redondant avec #7).
>   - *Remplacements par indicateur passif (3)* : `#10` `SystemdServices.tsx:153`, `#11` `DockerContainers.tsx:191`, `#12` `MetricsHistory.tsx:64` (remplacés par un texte passif "Dernière mise à jour il y a Xs" basé sur `useBlockData`).
> - **13 boutons conservés** :
>   - *Triggers de calcul lourds / scans physiques* : `#2` `MetricsOverview.tsx:157` (recalcul LLM), `#3` `NodeDetailInsightsTab.tsx:296` (baselines), `#9` `NodeDetailDiskTab.tsx:101` (scan disque 45s).
>   - *Données non précalculées (en attente de tickets dédiés)* : `#4` `NodeDetailInsightsTab.tsx:305`, `#5` `NodeDetailServicesTab.tsx:70` (traité en B4), `#6` `NodeDetailContainersTab.tsx:51`, `#13` `PlexAdmin.tsx:356` (traité en C4), `#17` `ProposalsPage.tsx:114`, `#18` `PluginsPage.tsx:41`, `#19` `PluginDetailKillSwitch.tsx:85`.
>   - *Actions d'administration & toggles UI* : `#14` `PlexAdmin.tsx:341` (toggle live), `#15` `PlexAdmin.tsx:347` (modal config), `#16` `PlexFilesTab.tsx:130` (scan bibliothèque).

---

### Session 1 — Plan (Audit)

```markdown
Contexte : projet Vigile, ticket B5. Plusieurs pages possèdent des boutons de rafraîchissement ou de recalcul manuels redondants. Avec le précalcul B1 et le polling automatique en place, ils doivent disparaître ou devenir des indicateurs passifs ("Dernière mise à jour il y a Xs").

Environnement : lis et explore directement les fichiers du workspace local via ta session en lecture seule stricte.

Ne code rien. Produis uniquement :
1. Un audit exhaustif : liste de tous les boutons refresh/recalcul du projet, page par page, plugin par plugin, avec fichier:ligne exacts.
2. Pour chaque bouton : décision tranchée (suppression sèche, remplacement par indicateur passif, ou conservation temporaire) avec justification technique.
3. Les critères de fraîcheur réelle pour chaque indicateur passif.
4. Tes hypothèses, que je dois valider.

J'attends ta réponse, je la valide, puis nous passerons à la vérification du plan.
```

---

### Session 1.5 — Vérification Plan (Momus / Oracle — Qualité Maximale)

```markdown
Agent : Momus (Oh My OpenCode) / Oracle — Critique de plan.

Consigne qualité NON NÉGOCIABLE :
- Analyse exhaustive sans compromis de rapidité.
- Vérifie que chaque bouton dont la suppression est proposée est EFFECTIVEMENT couvert par un rafraîchissement automatique fiable (polling ou SWR).

Mission : critique l'audit fichier par fichier. Cherche les faux positifs (bouton supprimé alors que la donnée n'est pas auto-rafraîchie) et les incohérences d'état.
Verdict attendu : GO / GO avec corrections mineures / REWORK.
```

---

### Session 2 — Exécution

```markdown
Voici l'audit validé pour le ticket B5 :

### 1. Actions à exécuter (6 boutons modifiés)
#### A. Suppressions sèches (Donnée auto-refreshed, indicateur passif déjà présent)
- #1 MetricsOverview.tsx:167 : Supprimer le bouton "Rafraîchir les données" (RefreshCw). Polling 20s et lastRefreshed déjà en place.
- #7 NodeDetailLogsTab.tsx:211 : Supprimer le bouton de refresh manuel dans le tab header. Polling 15s et badge LIVE actifs.
- #8 LogToolbar.tsx:181 : Supprimer le bouton de refresh redondant dans la toolbar des logs.

#### B. Remplacements par indicateur passif (Auto-refresh SWR 30s actif)
- #10 SystemdServices.tsx:153 : Remplacer le bouton "Rafraîchir" par l'indicateur passif "Dernière mise à jour il y a Xs" basé sur useBlockData.
- #11 DockerContainers.tsx:191 : Remplacer le bouton "Rafraîchir" par le même indicateur passif.
- #12 MetricsHistory.tsx:64 : Remplacer le bouton "Rafraîchir" par le même indicateur passif.

### 2. Boutons conservés (13 boutons non modifiés)
- Triggers lourds : #2 (MetricsOverview LLM), #3 (Insights baselines), #9 (Scan disque).
- Données non auto-refreshed : #4 (Insights), #5 (Services NodeDetail), #6 (Containers NodeDetail), #13 (PlexAdmin), #17 (Proposals), #18 (Plugins), #19 (KillSwitch).
- Actions admin : #14, #15, #16.

Règles strictes d'exécution et anti-triche :
- Environnement : modifie directement les fichiers du workspace local avec tes outils d'édition intégrés et lance les vérifications dans ton terminal local.
- INTERDIT de modifier ou supprimer un test existant pour le faire passer. Si un test référence un bouton supprimé, signale-le explicitement.
- Chaque indicateur passif de remplacement doit afficher la fraîcheur réelle de la donnée (pas de timestamp figé ou calculé à la volée sur Date.now()).
- Ne supprime aucun code mort non lié directement aux boutons traités.
- Clôture et sortie obligatoire du diff : à la fin de l'intervention, (1) documente ce qui a été réalisé en ajoutant une entrée à la fin de SESSION.md selon le format invariant, et (2) AFFICHE OBLIGATOIREMENT LE DIFF COMPLET (dans un bloc de code markdown ```diff contenant la sortie exacte de `git diff HEAD`) à la toute fin de ta réponse finale pour que l'opérateur puisse le copier directement vers la session de review.

Exécute uniquement le ticket B5.
```

---

### Session 3 — Review Diff (Audit Hostile)

```markdown
Voici le diff de l'implémentation du ticket B5 :
[colle le diff brut git diff HEAD]

Environnement : vérifie directement les fichiers dans le workspace de ta session en lecture seule.

Review-le en mode hostile, sans supposer qu'il est correct. Cherche activement :
1. Bouton supprimé dont la donnée n'est PAS réellement rafraîchie automatiquement (l'utilisateur se retrouve-t-il sans moyen de mettre à jour la vue ?).
2. Indicateur passif qui affiche une fraîcheur fausse ou jamais réévaluée au fil du temps.
3. Handler d'événement ou fonction orpheline devenue morte après suppression du bouton mais laissée dans le code.
4. Régression : un rafraîchissement fonctionnel (qui rechargeait aussi un store global) a-t-il été cassé par accident ?

Liste chaque problème avec fichier:ligne. Ne complimente pas le code.
```
