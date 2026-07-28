# Vigile — Makefile
# Commandes pratiques pour le développement et le déploiement.
# Utilisation :
#   make setup    → Installer les hooks pre-commit et commitlint
#   make build    → Rebuild l'image master (sans cache)
#   make deploy   → Rebuild + redémarre le conteneur
#   make restart  → Redémarre le conteneur seulement
#   make logs     → Suivre les logs du master
#   make ps       → Statut des conteneurs
#   make health   → Vérifier la santé du master

.PHONY: build deploy restart logs ps health setup

build:
	docker compose build --no-cache master

deploy: build
	docker compose up -d master
	@echo 
	@echo ✓ Déploiement terminé. Vérifie avec : make health

restart:
	docker compose restart master

logs:
	docker compose logs -f master

ps:
	docker compose ps

health:
	@curl -s http://localhost:8000/health | python3 -m json.tool || echo Master indisponible

setup:
	pip install pre-commit
	npm install
	pre-commit install --hook-type commit-msg
	pre-commit install
	@echo
	@echo ✓ Hooks installés. Les commits seront vérifiés automatiquement.
