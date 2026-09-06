# Chantier C3 — Media Stack : Sonarr, Radarr, Overseerr

*Protocole partagé, règles d'exécution et anti-triche : voir [`00-protocole-commun.md`](00-protocole-commun.md).*

---

## C3. Ajout des Plugins Sonarr, Radarr et Overseerr (Qualité +++)

**Outil / Modèle :** Antigravity — PLAN **MiMo-V2.5** + EXEC **Muse Spark 1.2** · Garde-fou renforcé (Anti-hallucination API) · **1 session d'exécution par service** (jamais les 3 en un seul run).

> **Décisions qualité +++ figées** :
> - Bloc catalogue mutualisé `media-service-card` et **un unique wrapper partagé** `MediaServiceHost.tsx` (Option A) — zéro composant React custom dupliqué par plugin.
> - Helper HTTP factorisé `master/core/media_helpers.py` (`_query_arr_api_detailed`) évitant la duplication de code entre Sonarr et Radarr.
> - Ports par défaut : Sonarr 8989, Radarr 7878, Overseerr 5055.
> - Chiffrement systématique des clés API au repos via `config_encryption.py` (`secret: true`, préfixe `v1:` dérivé de la clé maître du Master) et masquage à la lecture (`••••••••`).
> - Authentification : header `X-Api-Key: <key>` avec fallback `Authorization: Bearer <key>` pour Overseerr.
> - Auto-refresh SWR `30s` (`revalidateInterval: 30_000`).
> - Détection croisée d'instances en 4 étapes : conteneurs en cache -> services systemd en cache -> processus (`top_processes`) -> probe HTTP sur `/api/v3/system/status` (timeout 1.5s).
> - Configuration par nœud avec fallback global (`sonarr_url` global ou `sonarr_url_by_node`).
> - Persistance de l'historique en base locale (`sonarr_history`, `radarr_history`, `overseerr_requests`) avec rétention configurable (`retention_days`).

---

### Session 1 — Plan (Commun aux trois services)

```markdown
Contexte : projet Vigile, ticket C3. Ajout de trois nouveaux plugins pour la stack média : Sonarr, Radarr et Overseerr.
Contraintes d'architecture : chaque plugin est un module autonome dans `master/plugins/<id>/` contenant uniquement `__init__.py` et `manifest.json` au format déclaratif V2. L'interface utilisateur est 100% basée sur les blocs du catalogue, aucun composant React ad-hoc.
Ces trois services partageant des structures d'API proches (REST, files d'attente, historique), concevoir un bloc catalogue mutualisé `media-service-card` et un hôte générique partagé.

Environnement : lis et explore directement les fichiers du workspace local via ta session en lecture seule stricte.

Ne code rien. Produis uniquement :
1. Le design détaillé du bloc mutualisé `media-service-card` (contrats de données TypeScript, gestion des états `idle/busy/error/empty/data`).
2. Pour chacun des trois services : les endpoints API réels utilisés avec l'URL de la documentation officielle associée (marquer "À VÉRIFIER" en cas de doute).
3. Le plan d'exécution ordonné par phase : Socle mutualisé (Phase 0), puis Sonarr (Phase 1), Radarr (Phase 2), Overseerr (Phase 3).
4. Les hypothèses techniques sur la configuration, le chiffrement des clés, et la persistance locale de l'historique.

J'attends ta réponse, je la valide, puis nous passerons à la vérification du plan.
```

---

### Session 1.5 — Vérification Plan (Momus / Oracle — Qualité Maximale)

```markdown
Agent : Momus (Oh My OpenCode) / Oracle — Critique de plan.

Consigne qualité NON NÉGOCIABLE :
- Vérifie la conformité exacte aux spécifications d'API réelles Servarr/Overseerr (anti-hallucination).
- Contrôle que le bloc `media-service-card` respecte strictement `block-contract-v2.md` et que la configuration des clés API est protégée par chiffrement.

Mission : critique le plan fichier par fichier. Cherche les divergences DTO, les risques de fuite de tokens dans les logs, et les incohérences de mapping entre Sonarr et Radarr.
Verdict attendu : GO / GO avec corrections mineures / REWORK.
```

---

### Session 2 — Exécution (1 session dédiée par service)

```markdown
Voici le plan validé pour le ticket C3 (Service ciblé : [Sonarr / Radarr / Overseerr]) :

### 1. Bloc mutualisé catalogue (`media-service-card`)
Fichier : `frontend/src/components/blocks/MediaServiceCard.tsx`
Contrat DTO TypeScript :
export interface MediaServiceCardData {
  service: {
    id: string;
    name: string;
    version?: string;
    status: 'online' | 'offline' | 'degraded' | 'unconfigured';
    url?: string;
    uptimeSeconds?: number;
    health?: Array<{ source: string; type: 'warning' | 'error'; message: string }>;
  };
  activity: {
    queue: Array<{
      id: string | number;
      title: string;
      status: string;
      progress?: number;
      protocol?: string;
      indexer?: string;
      timeleft?: string;
      sizeBytes?: number;
    }>;
    totalCount: number;
    isPaused?: boolean;
  };
  history: {
    items: Array<{
      id: string | number;
      title: string;
      eventType: string;
      date: number;
      quality?: string;
      sourceTitle?: string;
    }>;
    totalCount: number;
  };
}

### 2. Endpoints API réels par service
- Sonarr (port 8989) :
  - Statut : GET /api/v3/system/status & GET /api/v3/health (Doc: wiki.servarr.com/sonarr/api)
  - File d'attente : GET /api/v3/queue?includeUnknownSeriesItems=true&pageSize=50&sortKey=timeleft
  - Historique : GET /api/v3/history?pageSize=20&sortKey=date&sortDirection=descending
- Radarr (port 7878) :
  - Statut : GET /api/v3/system/status & GET /api/v3/health (Doc: wiki.servarr.com/radarr/api)
  - File d'attente : GET /api/v3/queue?includeUnknownMovieItems=true&pageSize=50&sortKey=timeleft
  - Historique : GET /api/v3/history?pageSize=20&sortKey=date&sortDirection=descending
- Overseerr (port 5055) :
  - Statut : GET /api/v1/status & GET /api/v1/settings/public (Doc: api.overseerr.dev)
  - File d'attente : GET /api/v1/request?take=20&filter=pending&sort=added
  - Historique : GET /api/v1/request?take=20&filter=available&sort=modified

### 3. Déroulement par phase
- Phase 0 (Socle) : `MediaServiceCard.tsx` + enregistrement `registry.ts` + hôte partagé `MediaServiceHost.tsx` + helper `media_helpers.py`.
- Phase 1 (Sonarr) : `master/plugins/sonarr/manifest.json` + `__init__.py` + tests.
- Phase 2 (Radarr) : `master/plugins/radarr/manifest.json` + `__init__.py` + tests.
- Phase 3 (Overseerr) : `master/plugins/overseerr/manifest.json` + `__init__.py` + tests.

Règles strictes d'exécution et anti-triche :
- Environnement : modifie directement les fichiers du workspace local avec tes outils d'édition intégrés et lance les tests dans ton terminal local.
- INTERDIT de modifier ou supprimer un test existant pour le faire passer.
- Les clés API doivent obligatoirement être chiffrées via `derive_config_key`, jamais affichées en clair dans les logs ou les réponses API.
- Le dossier du plugin (`master/plugins/<id>/`) doit contenir UNIQUEMENT `__init__.py` et `manifest.json`. Zéro fichier frontend dans ce dossier.
- Zéro `as any`, typage strict TypeScript et Python.
- Clôture et sortie obligatoire du diff : à la fin de l'intervention, (1) documente ce qui a été réalisé en ajoutant une entrée à la fin de SESSION.md selon le format invariant, et (2) AFFICHE OBLIGATOIREMENT LE DIFF COMPLET (dans un bloc de code markdown ```diff contenant la sortie exacte de `git diff HEAD`) à la toute fin de ta réponse finale pour que l'opérateur puisse le copier directement vers la session de review.

Exécute uniquement le service : [Sonarr / Radarr / Overseerr].
```

---

### Session 3 — Review Diff (Audit Hostile & Anti-Hallucination)

```markdown
Voici le diff de l'implémentation du plugin [Sonarr / Radarr / Overseerr] :
[colle le diff brut git diff HEAD]

Environnement : vérifie directement les fichiers dans le workspace de ta session en lecture seule.

Review-le en mode hostile, sans supposer qu'il est correct. Cherche activement :
1. Hallucination d'API : les endpoints, paramètres de requête et structures de réponse correspondent-ils rigoureusement aux documentations officielles Servarr/Overseerr ?
2. Fuite de clé API ou de secret : la clé API est-elle chiffrée au repos, masquée dans les retours API (`••••••••`) et absente des logs de debug ?
3. Gestion des erreurs et service indisponible : que voit l'utilisateur si le service est hors-ligne ou si la clé API est invalide (état d'erreur explicite avec raison ou page vide) ?
4. Mutualisation : le plugin réutilise-t-il bien le bloc générique `media-service-card` sans créer de composant frontend ad-hoc ?
5. Conformité du manifest déclaratif V2 (`schema_version: 2`, `trusted: true`, déclaration des routes).

Liste chaque problème avec fichier:ligne. Ne complimente pas le code.
```
