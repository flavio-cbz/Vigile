# Chantier C4 — Plex Media Server : Intégration Réelle et Flux Live

*Protocole partagé, règles d'exécution et anti-triche : voir [`00-protocole-commun.md`](00-protocole-commun.md).*

---

## C4. Plex : Vraie Intégration API et Télémétrie Live (Qualité +++)

**Outil / Modèle :** Antigravity — PLAN **MiMo-V2.5** + EXEC **Muse Spark 1.2** · Garde-fou renforcé (Anti-hallucination API & Sécurité Token).

> **Décisions qualité +++ figées** :
> - Remplacement des données mockées/statiques par la véritable API Plex Media Server (sessions actives, flux de transcodage, charge du serveur, historique de visionnage).
> - Endpoints réels documentés :
>   - Statut serveur : `GET /status/sessions` et `GET /` (infos serveur, version, nom convivial).
>   - Sessions actives : `GET /status/sessions` (parsing des nœuds `MediaContainer/Metadata` : utilisateur, titre, bande passante, état de lecture).
>   - Transcodages : `GET /status/sessions` -> `TranscodeSession` (codec vidéo/audio, mode `direct play` vs `transcode`, throttling, HW acceleration).
>   - Historique : `GET /status/sessions/history/all` (ou persistance locale en DB `plex_watch_history`).
> - Chiffrement du `plex_token` au repos via `derive_config_key` (`secret: true`, préfixe `v1:`) et masquage complet dans l'API.
> - Gestion des boutons d'interface :
>   - **`Configure Plex` CONSERVÉ** (paramétrage URL/Token).
>   - **`Rafraîchir` SUPPRIMÉ** une fois le flux live B1 (polling SWR 30s + invalidation SSE) en place (remplacé par un indicateur de fraîcheur passif).
> - Gestion des pannes : en cas de serveur Plex injoignable ou de token révoqué, afficher une bannière d'erreur explicite avec la raison et l'URL tentée (pas de page blanche ni d'erreur silencieuse).

---

### Session 1 — Plan

```markdown
Contexte : projet Vigile, ticket C4. La page Plex n'affiche actuellement que des informations statiques sans télémétrie réelle.
Attendu : connecter la véritable API Plex Media Server pour remonter les sessions de lecture actives, les transcodages en cours, l'état de santé du serveur et l'historique récent, en s'appuyant sur le pattern précalcul + live B1.

Environnement : lis et explore directement les fichiers du workspace local via ta session en lecture seule stricte.

Ne code rien. Produis uniquement :
1. Les endpoints API réels Plex Media Server utilisés pour chaque métrique (sessions, transcodeurs, statut, historique) avec leur format de payload (XML/JSON via headers `Accept: application/json`).
2. Le plan d'exécution ordonné, fichier par fichier : adaptation du backend `master/plugins/plex/`, chiffrement du token, normalisation DTO et mise à jour du frontend `PlexAdmin.tsx` / composants de blocs.
3. La stratégie de rafraîchissement (polling adaptatif 3s en lecture active / 30s au repos) et la gestion de la suppression du bouton refresh manuel.
4. Les mesures de sécurité : isolation du token Plex (jamais loggé, jamais transmis au client web).

J'attends ta réponse, je la valide, puis nous passerons à la vérification du plan.
```

---

### Session 1.5 — Vérification Plan (Momus / Oracle — Qualité Maximale)

```markdown
Agent : Momus (Oh My OpenCode) / Oracle — Critique de plan.

Consigne qualité NON NÉGOCIABLE :
- Vérifie la conformité exacte aux structures d'API Plex Media Server (anti-hallucination sur les champs XML/JSON de transcode).
- Contrôle que le token Plex est protégé par le chiffrement du Master et qu'aucune fuite de token n'est possible dans les logs ou le frontend.

Mission : critique le plan fichier par fichier. Liste chaque faiblesse technique et chaque cas limite non géré (ex: Plex distant non joignable, SSL self-signed Plex).
Verdict attendu : GO / GO avec corrections mineures / REWORK.
```

---

### Session 2 — Exécution

```markdown
Voici le plan validé pour le ticket C4 :

### 1. Backend Plugin Plex (`master/plugins/plex/`)
- Utiliser `httpx.AsyncClient` avec header `X-Plex-Token` et `Accept: application/json`.
- Endpoints clés implémentés :
  - `GET /status/sessions` : agrégation des flux actifs (`title`, `user`, `player`, `transcode_session`).
  - `GET /` : statut serveur (`friendlyName`, `version`, `platform`).
  - `GET /library/sections` : état des bibliothèques.
- Helper `_query_plex_api_detailed` retournant `(data, error_reason)` avec URL tentée en cas d'erreur 502.
- Token stocké sous clé chiffrée `v1:` via `derive_config_key(master_private_key)`.

### 2. Frontend & Flux Live (`frontend/src/plugins/plex/` ou composants catalogue)
- Polling dynamique via `useBlockData` : 3s si des sessions de lecture sont actives, 30s au repos.
- Suppression du bouton de rafraîchissement manuel au profit d'un indicateur passif de fraîcheur.
- Conservation de la modale de configuration ("Configurer Plex").
- Gestion explicite des erreurs avec composant `Banner` (serveur down, token invalide).

Règles strictes d'exécution et anti-triche :
- Environnement : modifie directement les fichiers du workspace local avec tes outils d'édition intégrés et lance les tests dans ton terminal local.
- INTERDIT de modifier ou supprimer un test existant pour le faire passer.
- Le token Plex ne doit JAMAIS apparaître en clair dans les logs, les traces d'erreurs ou les réponses API frontend.
- Zéro `as any`, typage strict TypeScript (`PlexSessionRecord`, `PlexStatusData`).
- Clôture et sortie obligatoire du diff : à la fin de l'intervention, (1) documente ce qui a été réalisé en ajoutant une entrée à la fin de SESSION.md selon le format invariant, et (2) AFFICHE OBLIGATOIREMENT LE DIFF COMPLET (dans un bloc de code markdown ```diff contenant la sortie exacte de `git diff HEAD`) à la toute fin de ta réponse finale pour que l'opérateur puisse le copier directement vers la session de review.

Exécute uniquement le ticket C4.
```

---

### Session 3 — Review Diff (Audit Hostile)

```markdown
Voici le diff de l'implémentation du ticket C4 :
[colle le diff brut git diff HEAD]

Environnement : vérifie directement les fichiers dans le workspace de ta session en lecture seule.

Review-le en mode hostile, sans supposer qu'il est correct. Cherche activement :
1. Hallucination d'API Plex : vérifie que les champs de transcode et de session extraits du JSON Plex existent réellement dans l'API officielle.
2. Fuite de secret : le `plex_token` apparaît-il en clair dans les logs, dans une URL de requête ou dans le payload envoyé au navigateur ?
3. Cycle de vie des sessions : lorsqu'une lecture se termine, l'UI se met-elle à jour sans nécessiter de rechargement manuel de la page ?
4. Gestion des erreurs : en cas de timeout ou de refus de connexion Plex (502/504), l'interface affiche-t-elle un état d'erreur explicite et actionnable ?
5. Conformité de la suppression du bouton refresh manuel.

Liste chaque problème avec fichier:ligne. Ne complimente pas le code.
```
