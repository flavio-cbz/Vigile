# Chantier G1 — Intelligence Artificielle & Copilote

*Protocole partagé, règles d'exécution et anti-triche : voir [`00-protocole-commun.md`](00-protocole-commun.md).*

---

## G1. Amélioration de l'Intégration de l'IA dans Vigile (Qualité +++)

**Outil / Modèle :** Antigravity — PLAN **MiMo-V2.5** (1M ctx, pipeline complet `llm_client -> structured_llm -> chat_stream -> CopilotPanel`) + EXEC **Muse Spark 1.2** · Garde-fou renforcé (Observabilité, Résilience & Human-in-the-loop).

> **Décisions qualité +++ figées** :
> - **Chaîne de streaming résiliente** : fiabilisation du streaming SSE/WebSocket avec reconnexion transparente, timeouts configurables et état d'erreur UI explicite (en cas d'indisponibilité du provider ou dépassement de quota).
> - **Contexte dynamique et frais** : injection automatisée de la télémétrie récente du nœud (métriques CPU/RAM/Disque, alertes actives de `alert_engine`, conteneurs/services en erreur) sans latence ni données périmées.
> - **Structured Outputs & Proposals** : validation stricte Pydantic des `ActionProposal` suggérées par l'IA avec niveau de risque (`RiskLevel`), raisonnement structuré et soumission au workflow d'approbation humaine stricte (*Human-in-the-Loop*).
> - **Protection contre les fuites de secrets** : masquage systématique des tokens de configuration, des clés API et des mots de passe avant transmission au LLM et dans les logs d'audit.

---

### Session 1 — Plan

```markdown
Contexte : projet Vigile, ticket G1. Amélioration globale de l'intégration de l'IA (Copilote / LLM) dans Vigile : fiabilisation du streaming SSE, injection d'un contexte frais et pertinent (nœuds, métriques, alertes), standardisation des propositions d'actions `ActionProposal`, et gestion robuste des erreurs de fournisseurs LLM (Ollama local, OpenAI, Anthropic).

Environnement : lis et explore directement les fichiers du workspace local via ta session en lecture seule stricte.

Ne code rien. Produis uniquement :
1. L'état des lieux critique de l'architecture IA actuelle : `master/core/llm_client.py`, `master/core/structured_llm.py`, `master/api/chat.py`, `master/api/chat_stream.py`, `frontend/src/components/copilot/CopilotPanel.tsx`, gestion des sessions et prompt system.
2. L'identification des points de fragilité et axes d'amélioration :
   - Streaming SSE/WS : gestion des coupures, timeouts, retries et buffering.
   - Contexte : sélection des signaux pertinents (alertes récentes, logs d'erreur, statut nœud) pour éviter la saturation du contexte.
   - Sécurité & validation : validation Pydantic v2 des schémas d'actions, respect du Human-in-the-Loop, masquage des secrets.
3. Un plan d'exécution ordonné, modulaire et rétrocompatible.
4. Tes hypothèses techniques, que je dois valider.

J'attends ta réponse, je la valide, puis nous passerons à la vérification du plan.
```

---

### Session 1.5 — Vérification Plan (Momus / Oracle — Qualité Maximale)

```markdown
Agent : Momus (Oh My OpenCode) / Oracle — Critique de plan IA & Copilote.

Consigne qualité NON NÉGOCIABLE :
- Analyse approfondie sans compromis de rapidité.
- Vérifie la sécurité absolue du flux Human-in-the-Loop : aucune action proposée par l'IA ne doit pouvoir s'exécuter sans approbation explicite d'un opérateur.
- Contrôle la résilience du streaming et l'absence de fuite de tokens/secrets dans les prompts.

Mission : critique le plan fichier par fichier. Cherche les failles d'injection de prompt, les risques de blocage sur timeout LLM, et les incohérences de gestion d'état frontend.
Verdict attendu : GO / GO avec corrections mineures / REWORK.
```

---

### Session 2 — Exécution

```markdown
Voici le plan validé pour le ticket G1 :
[colle le plan validé]

Règles strictes d'exécution et anti-triche :
- Environnement : modifie directement les fichiers du workspace local avec tes outils d'édition intégrés et lance les tests dans ton terminal local.
- INTERDIT de modifier ou supprimer un test existant pour le faire passer.
- Aucune clé API, endpoint ou secret ne doit être codé en dur : tout provient de la configuration sécurisée.
- Garantir un état d'erreur explicite côté UI pour chaque cas de défaillance (timeout provider, quota dépassé, JSON malformé).
- Respect absolu du modèle `ActionProposal` : l'IA propose, l'humain approuve, le Worker exécute. Zéro exécution directe par le LLM.
- Zéro `as any`, typage strict TypeScript et Pydantic v2.
- Clôture et sortie obligatoire du diff : à la fin de l'intervention, (1) documente ce qui a été réalisé en ajoutant une entrée à la fin de SESSION.md selon le format invariant, et (2) AFFICHE OBLIGATOIREMENT LE DIFF COMPLET (dans un bloc de code markdown ```diff contenant la sortie exacte de `git diff HEAD`) à la toute fin de ta réponse finale pour que l'opérateur puisse le copier directement vers la session de review.

Exécute uniquement le ticket G1.
```

---

### Session 3 — Review Diff (Audit Hostile)

```markdown
Voici le diff de l'implémentation du ticket G1 :
[colle le diff brut git diff HEAD]

Environnement : vérifie directement les fichiers dans le workspace de ta session en lecture seule.

Review-le en mode hostile, sans supposer qu'il est correct. Cherche activement :
1. Erreurs avalées ou blocages infinis : les appels HTTP au provider LLM ont-ils des timeouts explicites et des gestionnaires d'exceptions fiables ?
2. Risque de sécurité : des secrets, clés de tokens ou variables d'environnement sont-ils injectés en clair dans les prompts envoyés au LLM ?
3. Bypass du Human-in-the-Loop : existe-t-il un chemin où une proposition d'action s'exécute automatiquement sans validation humaine ?
4. Dégradation du streaming frontend : les états de chargement, d'arrêt (`abortStreaming`) et de défilement fonctionnent-ils de manière fluide ?
5. Validation des structured outputs : que se passe-t-il si le modèle génère un JSON invalide après plusieurs tentatives de retry ?

Liste chaque problème avec fichier:ligne. Ne complimente pas le code.
```
