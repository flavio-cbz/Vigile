# Session — Vigile Sprint 9

**Date :** 2026-08-19
**Sprint :** 9 (Logs Tab Redesign & Worker v1.1.0 Release)
**Statut :** Terminé & Déployé en production

## Objectifs et réalisations du sprint

### 1. ✅ Refonte Complète de l'Onglet Logs (Zen & Timeline Fusion)
- **Timeline d'activité 24h** : Composant `LogTimeline` interactif affichant l'histogramme des événements (info, warn, error) par heure avec navigation et filtrage par clic.
- **Sélecteur de sources moderne** : Remplacement du menu déroulant standard par `LogSourceBar` et `LogSourceModal` catégorisant les sources (`Fichiers système`, `Services systemd`, `Conteneurs Docker`) avec indicateurs d'état et badges d'erreur.
- **Console de logs avancée** : `LogConsole` plein écran avec recherche temps réel, coloration syntaxique des niveaux de sévérité, bascule wrap/nowrap, auto-scroll intelligent et export direct en fichier `.log`.
- **API Master & Architecture** :
  - Endpoints `GET /api/nodes/{id}/logs`, `GET /api/nodes/{id}/log-sources`, `GET /api/nodes/{id}/log-histogram`.
  - Routage 100% read-only via `WorkerQueryPort` garantissant la séparation stricte mutations / requêtes.
  - Traduction bilingue complète (Français / Anglais).

### 2. ✅ Robustesse Worker Go & Sortie de la Version 1.1.0
- **Streaming de logs volumineux** : Remplacement du chargement intégral en mémoire (`os.ReadFile`) par la fonction O(1) mémoire `tailLogFile` (`tail -n <lines>` avec fallback pur Go seek à -2 Mo). Résolution définitive de l'erreur `log file too large`.
- **Nouveaux intents Worker** : Prise en charge officielle de `LIST_LOG_SOURCES` et `LOG_HISTOGRAM` dans la liste blanche d'exécution.
- **Incrémentation de version** : Passage à la version `1.1.0` du Worker (`worker/discovery.go`).
- **Distribution & Auto-update** :
  - Publication des binaires `linux/arm64` et `linux/amd64` avec manifest et signatures SHA256 sur le serveur de distribution Master (`/var/cache/vigile/worker/`).
  - Validation du flux complet d'auto-mise à jour depuis le frontend via `POST /api/nodes/{id}/update` et l'intent `UPDATE_WORKER`.
  - Renforcement de la résilience du journal d'audit (`master/core/audit.py`) sous forte concurrence via boucle de réessai sur collision de séquence.

## Tests et validation
- 12/12 tests unitaires validés avec succès (`pytest tests/test_api/test_logs.py`).
- Déploiement et validation en conditions réelles sur l'instance de production `youcloud.ovh`.
