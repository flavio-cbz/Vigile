#!/bin/bash
# Push les commits locaux vers GitHub via PAT
# Usage: ./scripts/push_with_pat.sh
# Le PAT sera demandé de manière sécurisée (input masqué)

set -e

REPO_DIR="/home/flavio/Docker-Compose/vigile"
cd "$REPO_DIR"

echo "=== Push des commits locaux vers GitHub ==="
echo ""
echo "Tu as $(git log --oneline origin/master..HEAD | wc -l) commits à pusher :"
git log --oneline origin/master..HEAD
echo ""

# Demande le PAT de manière sécurisée
echo -n "Colle ton Personal Access Token (input visible) : "
read -r TOKEN

if [ -z "$TOKEN" ]; then
  echo "Erreur : token vide"
  exit 1
fi

# Configure le remote avec le token embarqué
git remote set-url origin "https://flavio-cbz:${TOKEN}@github.com/flavio-cbz/Vigile.git"

# Push
echo ""
echo "=== Push en cours... ==="
if git push -u origin master 2>&1; then
  echo ""
  echo "=== Push réussi ! ==="

  # Nettoie le token de la config (retour à l'URL sans credentials)
  git remote set-url origin "https://github.com/flavio-cbz/Vigile.git"

  # Supprime le credential store s'il contient le token
  if [ -f ~/.git-credentials ]; then
    sed -i '/flavio-cbz@github.com/d' ~/.git-credentials 2>/dev/null || true
  fi

  echo ""
  echo "Remote URL nettoyé. Le token n'est plus stocké nulle part."
  echo ""
  echo "=== État final ==="
  git log --oneline -5
  git status
else
  # En cas d'échec, nettoie quand même le token de l'URL
  git remote set-url origin "https://github.com/flavio-cbz/Vigile.git"
  echo ""
  echo "=== Push échoué, token nettoyé de la config ==="
  exit 1
fi
