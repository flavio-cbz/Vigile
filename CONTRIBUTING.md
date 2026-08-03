# Contribuer à Vigile

Merci de votre intérêt pour Vigile ! Ce document explique les conventions du projet pour garantir une histoire Git propre et lisible.

---

## Convention de Messages de Commit

Vigile utilise les **[Conventional Commits](https://www.conventionalcommits.org/)** (v1.0.0). Un hook `commitlint` vérifie automatiquement chaque message de commit.

### Format

```
<type>(<scope>): <description>

[corps optionnel]

[pied de page optionnel]
```

> **Note** : pas d'espace avant les deux-points. Le parser exige le format standard `type(scope): message`.

### Types

| Type | Usage | Exemple |
|------|-------|---------|
| `feat` | Nouvelle fonctionnalité | `feat(master): ajout de la déduplication des alertes` |
| `fix` | Correction de bug | `fix(worker): gérer les stats disque nulles` |
| `docs` | Documentation uniquement | `docs: mise à jour du guide de déploiement` |
| `style` | Formatage, pas de changement de code | `style(frontend): corriger l'indentation` |
| `refactor` | Restructuration sans feature/fix | `refactor(core): extraire le vérificateur d'audit` |
| `perf` | Amélioration de performance | `perf(worker): réduire les alloc dans le scan disque` |
| `test` | Ajout ou mise à jour de tests | `test(api): ajouter les cas limites d'auth` |
| `build` | Système de build ou dépendances | `build: passer Go en 1.23` |
| `ci` | Configuration CI/CD | `ci: ajouter le build arm64` |
| `chore` | Tâches de maintenance | `chore: nettoyer le gitignore` |
| `revert` | Annuler un commit précédent | `revert: annuler le changement de cache` |

### Scopes

Les scopes identifient le module touché. Utilisez un scope quand c'est pertinent :

| Scope | Module |
|-------|--------|
| `master` | Serveur FastAPI (Python) |
| `worker` | Agent Go |
| `frontend` | SPA React |
| `worker-binary` | Distribution binaire / manifest |
| `kickstart` | Script d'installation |
| `plugins` | Système de plugins |
| `api` | Couche REST API |
| `ci` | Pipeline CI/CD |
| `docs` | Documentation |
| `ws` | Protocole WebSocket |
| `db` | Base de données / migrations |
| `core` | Logique métier |
| `schemas` | Schémas Pydantic |
| `scripts` | Scripts de dev / simulation |
| `docker` | Docker / compose |
| `tests` | Suite de tests |
| `git` | Configuration git |
| `logging` | Système de logging |
| `security` | Sécurité / auth / crypto |
| `alerts` | Moteur d'alertes |
| `insights` | Analyse d'anomalies |

Plusieurs scopes sont autorisés avec `+` : `feat(master+worker): ...`

### Règles

1. **Pas de `.` en fin de sujet** — le sujet est une phrase, pas une phrase complète
2. **Pas de majuscule en début de sujet** — sauf noms propres (`ajouter le retry LLM` pas `Ajouter le retry LLM`)
3. **Impératif** — le sujet décrit ce que le commit fait, pas ce qui a été fait (`ajouter la feature` pas `ajouté la feature`)
4. **Maximum 100 caractères** pour la ligne de sujet
5. **Corps optionnel** — séparé d'une ligne vide, max 120 caractères par ligne
6. **Références issues** — dans le pied de page : `Closes #123`, `Fixes #456`, `Refs #789`

### Exemples

```
feat(master): ajouter le WebSocketLoggingMiddleware

- RequestLoggingMiddleware pour les requêtes HTTP
- WebSocketLoggingMiddleware pour les connexions WS
- CorrelationFilter pour le traçage des requêtes

Closes #42
```

```
fix(worker): supprimer les bashisms pour la compatibilité POSIX sh

- set -euo pipefail → set -eu (pipefail est spécifique à bash)
- &>/dev/null → >/dev/null 2>&1

Corrige 'Illegal option -o pipefail' lors de :
  curl ... | sudo sh -s -- --uninstall
```

```
feat(master+worker): ajouter le système de logging structuré verbose slog
```

```
fix(kickstart): supprimer les bashisms pour la compatibilité POSIX sh
```

### Ce qui est Interdit

```
❌  fix: correction tests                                  (pas de scope)
❌  feat(master) : add feature                             (espace avant les deux-points)
❌  Fix Python unit test failures                          (pas de type conventionnel)
❌  Sprint 7 — Correction des métriques CPU/disque         (pas de format conventionnel)
❌  update stuff                                           (trop vague, pas de type)
❌  feat(master): add feature.                              (point en fin de sujet)
```

---

## Installation des Hooks

Les hooks `pre-commit` vérifient automatiquement les messages de commit.

```bash
# Installer les hooks en une seule commande
make setup

# Ou manuellement
pip install pre-commit
npm install
pre-commit install --hook-type commit-msg
pre-commit install
```

> Le hook `commitlint` tourne uniquement sur les messages de commit (`commit-msg`), pas sur les fichiers modifiés.

---

## Branches

- `main` — branche de production, stable
- `master` — branche de développement principale
- Feature branches : `feat/<nom>`, `fix/<nom>`

---

## Pull Requests

1. Créer une branche à partir de `master`
2. Écrire des commits qui suivent les conventions ci-dessus
3. Ouvrir une PR avec une description claire
4. Les checks CI doivent passer (lint, tests, commitlint)

---

## Style de Code

- **Python** : Black (formatage), Flake8 (linting), mypy (typage)
- **Go** : golangci-lint avec la config du projet
- **TypeScript** : ESLint avec la config flat du projet
- **Tous** : EditorConfig pour l'indentation et l'encodage

---

*Des questions ? Ouvrez une issue.*
