# Chantier C2 — Services + Docker : Actions Destructrices et Refonte

*Protocole partagé, règles d'exécution et anti-triche : voir [`00-protocole-commun.md`](00-protocole-commun.md).*

---

## C2. Services + Docker : Suppression de Container et Arrêt de Service (Garde-fou MAXIMAL)

**Outil / Modèle :** Antigravity — PLAN **MiMo-V2.5** + **Muse Spark 1.2** (Duo qualité +++) + EXEC **Muse Spark 1.2** · **Garde-fou MAXIMAL**.

> **Avertissement de Sécurité Non Négociable :**
> Ce ticket introduit des actions destructrices réelles (`DELETE_CONTAINER`, `STOP_SERVICE`). Aucune action autonome n'est permise en production. L'opérateur humain valide explicitement chaque étape via une modale de confirmation avec saisie du nom. Mocks et tests d'intégration locaux uniquement.

> **Décisions qualité +++ figées** :
> - Services système protégés : `protected_services = ["networking", "ssh", "docker", "systemd-resolved"]` (extensible via configuration, blocage 403 strict côté Master et refus côté Worker).
> - Modale de confirmation UI avec saisie textuelle obligatoire du nom exact du conteneur (`confirmInput`), affichage de l'ID court et de l'image Docker.
> - Validation double `(container_id, container_name)` côté Worker avant toute suppression + paramètres `v=false` et `force=false` stricts (interdiction formelle de supprimer un conteneur en état `running` ou de purger les volumes).
> - Traçabilité SHA256 inviolable : toute action (validée, rejetée ou échouée) génère une `ActionProposal` et une entrée cryptographique dans l'audit log.

---

### Session 1 — Plan

```markdown
Contexte : projet Vigile, ticket C2. Refonte de la page Services + Docker avec ajout de deux actions destructrices : suppression d'un container et arrêt d'un service.
Contraintes d'architecture : ces actions doivent être des commandes déclarées dans les manifests de `docker` et `systemd`, avec confirmation explicite avant exécution, dans la continuité du modèle intent-based human-in-the-loop. L'UI utilise le bloc `action-panel` du catalogue, aucun composant custom ad-hoc. Chaque action est journalisée : qui, quoi, quand, résultat.

Environnement : lis et explore directement les fichiers du workspace local via ta session en lecture seule stricte.

Ne code rien. Produis uniquement :
1. Un plan d'exécution ordonné par couche : Worker Go (nouveaux intents dans la whitelist), Manifests déclaratifs, Backend Python & Audit SHA256, Frontend & Catalogue de blocs.
2. Le design exact du flux de confirmation : ce que voit l'utilisateur, ce qu'il doit saisir pour valider, et le comportement en cas d'erreur ou d'échec partiel.
3. La liste complète des fichiers existants impactés et les nouveaux tests de sécurité à créer.
4. Contredis-toi : analyse les trois pires scénarios où cette fonctionnalité peut causer des dégâts en production malgré les garde-fous prévus, et détaille les protections spécifiques que tu ajoutes au plan pour les neutraliser.

J'attends ta réponse, je la valide, puis nous passerons à la vérification du plan.
```

---

### Session 1.5 — Vérification Plan (Momus / Oracle — Qualité Maximale)

```markdown
Agent : Momus (Oh My OpenCode) / Oracle — Critique de plan de sécurité critique.

Consigne qualité NON NÉGOCIABLE :
- Analyse hostile et ultra-rigoureuse.
- Cherche activement toute possibilité de bypass de confirmation, de race condition, d'élévation de privilèges ou d'injection de commandes shell.

Mission : critique le plan fichier par fichier. Liste chaque faille potentielle, chaque hypothèse fragile et chaque cas limite non couvert.
Verdict attendu : GO / GO avec corrections mineures / REWORK — avec liste des corrections bloquantes avant EXEC.
```

---

### Session 2 — Exécution

```markdown
Voici le plan validé pour le ticket C2 :

### 1. Plan d'exécution ordonné par couche

#### Phase 1 — Worker Go (`worker/`)
- `worker/dispatcher.go` : Ajouter `STOP_CONTAINER`, `START_CONTAINER`, `DELETE_CONTAINER`, `STOP_SERVICE`, `START_SERVICE` à `ALLOWED_ACTIONS` et brancher les cas dans `dispatchIntent`.
- `worker/containers.go` :
  - `handleStopContainer` (Docker API `POST /containers/{id}/stop` avec timeout 30s).
  - `handleStartContainer` (Docker API `POST /containers/{id}/start`).
  - `handleDeleteContainer` (Docker API `DELETE /containers/{id}?v=false&force=false`). Fail-closed strict : vérifier que `State == "exited"` et valider la concordance du `container_name` si fourni (anti-stale ID). Refuser toute suppression d'un conteneur en cours d'exécution.
- `worker/services.go` :
  - `handleStopService` (`exec.CommandContext("systemctl", "stop", service)` sans shell).
  - `handleStartService` (`exec.CommandContext("systemctl", "start", service)`).
- Tests unitaires Go sur les 5 nouveaux intents et mise à jour du comptage `TestAllowedActions`.

#### Phase 2 — Manifests déclaratifs (`master/plugins/`)
- `master/plugins/docker/manifest.json` : Déclarer `STOP_CONTAINER` (HIGH risk, confirmation), `START_CONTAINER` (LOW risk), `DELETE_CONTAINER` (CRITICAL risk, confirmation).
- `master/plugins/systemd/manifest.json` : Déclarer `copilot_actions` avec `STOP_SERVICE` (HIGH risk, confirmation) et `START_SERVICE` (LOW risk). Ajouter `protected_services` dans la configuration par défaut (`["networking", "ssh", "docker", "systemd-resolved"]`).

#### Phase 3 — Backend Python & Audit (`master/`)
- `master/plugins/docker/__init__.py` & `master/plugins/systemd/__init__.py` :
  - Mapper les routes REST vers les intents Worker correspondants.
  - Défense en profondeur : refuser `delete` si le conteneur n'est pas `exited` (400), et refuser `stop` si le service fait partie de `protected_services` (403).
  - Passer conjointement `container_id` et `container_name` pour sécuriser l'intent `DELETE_CONTAINER`.
- `master/core/audit.py` : Ajouter les actions spécifiques dans `AuditAction` pour une traçabilité SHA256 complète.

#### Phase 4 — Frontend & Catalogue de blocs (`frontend/src/`)
- `frontend/src/components/blocks/types.ts` & `ActionButtonRow.tsx` :
  - Étendre `BlockAction` avec `confirm?: boolean`, `confirmMessage?: string | ((row: any) => string)`, `confirmInput?: string`.
  - Intégrer la modale accessible dans le catalogue `ActionButtonRow` (aucun composant ad-hoc dans les pages).
  - Si `confirmInput` est spécifié, exiger la saisie exacte du nom avant d'activer le bouton d'exécution.
- `DockerContainers.tsx` & `SystemdServices.tsx` :
  - Configurer les actions contextuelles par état : running -> `[STOP, RESTART]`, exited -> `[START, RESTART, DELETE]`.
  - Masquer ou désactiver `STOP` sur les services protégés (`protected_services`).
- Clés i18n FR et EN pour tous les messages de confirmation et avertissements.

#### Phase 5 — Tests de sécurité et non-régression
- Tests backend `test_docker.py` et `test_systemd.py` vérifiant :
  - Le blocage d'une suppression sur conteneur actif (400).
  - Le blocage d'un arrêt de service critique protégé (403).
  - L'enregistrement complet dans la chaîne de hash d'audit SHA256.

### 2. Arbitrages et Garde-fous contre les 3 scénarios de dégâts
1. Scénario 1 (Erreur humaine / mauvais conteneur ciblé) :
   - Modale enrichie avec affichage de l'ID court, de l'image et du nom.
   - Saisie obligatoire du nom exact du conteneur dans `confirmInput`.
2. Scénario 2 (Coupure réseau / arrêt service vital) :
   - `protected_services` configuré en dur par défaut (`ssh`, `networking`, `docker`, `systemd-resolved`) et extensible en configuration.
   - Blocage 403 côté Master + refus côté Worker + tentative journalisée dans l'audit.
3. Scénario 3 (Race condition / recyclage d'ID conteneur) :
   - Validation double `(container_id, container_name)` côté Worker avant exécution de `DELETE_CONTAINER`.
   - `force=false` et `v=false` stricts (préservation des volumes de données).

Règles strictes d'exécution et anti-triche :
- Environnement : modifie directement les fichiers du workspace local avec tes outils d'édition intégrés et lance les tests dans ton terminal local.
- INTERDIT de modifier ou supprimer un test existant pour le faire passer. Écris d'abord les tests de sécurité (qui doivent échouer sans confirmation), puis implémente le code.
- Zéro `as any`, typage strict TypeScript et Python.
- Zéro commande shell arbitraire : passage strict par `exec.CommandContext` avec arguments séparés.
- Clôture et sortie obligatoire du diff : à la fin de l'intervention, (1) documente ce qui a été réalisé en ajoutant une entrée à la fin de SESSION.md selon le format invariant, et (2) AFFICHE OBLIGATOIREMENT LE DIFF COMPLET (dans un bloc de code markdown ```diff contenant la sortie exacte de `git diff HEAD`) à la toute fin de ta réponse finale pour que l'opérateur puisse le copier directement vers la session de review.

Exécute uniquement le ticket C2.
```

---

### Session 3 — Review Diff (Audit Hostile & Sécurité)

```markdown
Voici le diff de l'implémentation du ticket C2 :
[colle le diff brut git diff HEAD]

Environnement : vérifie directement les fichiers dans le workspace de ta session en lecture seule.

Review-le en mode hostile avec une exigence de sécurité maximale. Cherche activement :
1. Chemin d'exécution contournant la confirmation (appel direct à l'API, retry automatique imprévu, état de modale partagé entre plusieurs lignes).
2. Injection de commande : le nom du service ou du container est-il interpolé dans un shell ou passé proprement en argument séparé à `exec.Command` ?
3. Vérification des permissions : l'endpoint API vérifie-t-il les rôles RBAC (Operator/Admin) et le manifest, ou fait-il confiance au frontend ?
4. Défaillances partielles & traçabilité : une action qui échoue à mi-parcours est-elle correctement journalisée dans la chaîne SHA256 de l'audit log avec l'identité de l'utilisateur ?
5. Cas limites : tentative de suppression d'un container en cours d'exécution, arrêt d'un service protégé, daemon Docker inaccessible.
6. Tests de sécurité : les tests vérifiant le refus sans confirmation et le blocage 403 existent-ils et sont-ils stricts ?

Liste chaque problème avec fichier:ligne. Ne complimente pas le code.
```
