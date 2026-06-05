#!/usr/bin/env bash
# Vigile — Test Environment Setup
#
# Automates: start Master → generate tokens → start Workers
#
# Usage:
#   ./scripts/setup_test.sh               # single worker
#   ./scripts/setup_test.sh --workers 3   # multi-node
#   ./scripts/setup_test.sh --clean       # stop everything
#
# Prerequisites: docker, docker compose, jq

set -euo pipefail

WORKERS=1
CLEAN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workers) WORKERS="$2"; shift 2 ;;
    --clean)   CLEAN=true; shift ;;
    *) echo "Usage: $0 [--workers N] [--clean]"; exit 1 ;;
  esac
done

COMPOSE_FILE="docker-compose.yml"

if [ "$CLEAN" = true ]; then
  echo "=== Cleaning up ==="
  # Stop all worker containers
  for i in $(seq 1 10); do
    docker rm -f "vigile-worker-$i" 2>/dev/null || true
  done
  docker compose -f "$COMPOSE_FILE" down -v 2>/dev/null || true
  echo "Done."
  exit 0
fi

# ── 1. Build and start Master ─────────────────────────────────────────
echo "========================================="
echo "  Vigile Test Environment Setup"
echo "========================================="
echo ""
echo "=== Building images ==="
docker compose -f "$COMPOSE_FILE" build master worker

echo "=== Starting Caddy + Master ==="
docker compose -f "$COMPOSE_FILE" up -d caddy master

echo "Waiting for Master to be healthy..."
for i in $(seq 1 30); do
  if curl -sk https://localhost:443/health >/dev/null 2>&1; then
    echo "Master is ready!"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "ERROR: Master failed to start"
    docker compose -f "$COMPOSE_FILE" logs master
    exit 1
  fi
  sleep 2
done

# ── 2. Login as admin ─────────────────────────────────────────────────
echo ""
echo "=== Authenticating as admin ==="
ADMIN_LOGIN=$(curl -sk -X POST https://localhost:443/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo","password":"demo"}')

ACCESS_TOKEN=$(echo "$ADMIN_LOGIN" | jq -r '.access_token')
if [ "$ACCESS_TOKEN" = "null" ] || [ -z "$ACCESS_TOKEN" ]; then
  echo "ERROR: Login failed: $ADMIN_LOGIN"
  exit 1
fi
echo "Access token obtained."

# ── 3. Generate tokens and start workers ──────────────────────────────
echo ""
for i in $(seq 1 "$WORKERS"); do
  NODE="worker-$i"
  echo "=== Setting up $NODE ==="

  # Generate JOIN_TOKEN via Master API
  JOIN=$(curl -sk -X POST https://localhost:443/api/nodes/generate-join \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -d "{\"name\":\"$NODE\"}")

  NODE_ID=$(echo "$JOIN" | jq -r '.node_id')
  TOKEN=$(echo "$JOIN" | jq -r '.token')

  echo "  Node ID: $NODE_ID"

  # Stop existing container if any
  docker rm -f "vigile-$NODE" 2>/dev/null || true

  # Start worker container with the token
  docker compose -f "$COMPOSE_FILE" run -d \
    --name "vigile-$NODE" \
    -e "JOIN_TOKEN=$TOKEN" \
    --rm \
    worker

  echo "  Worker started as vigile-$NODE"
done

# ── 4. Summary ────────────────────────────────────────────────────────
echo ""
echo "========================================="
echo "  Setup Complete"
echo "========================================="
echo ""
echo "Master:    https://localhost:443"
echo "API Docs:  https://localhost:443/api/docs"
echo "Workers:   $WORKERS deployed"
echo ""
echo "Quick checks:"
echo "  docker compose logs -f master    # Watch Master logs"
echo ""
echo "  # List nodes with enrollment status:"
echo "  TOKEN=\$(curl -sk https://localhost:443/api/auth/login \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"username\":\"demo\",\"password\":\"demo\"}' | jq -r '.access_token')"
echo "  curl -sk https://localhost:443/api/nodes \\"
echo "    -H \"Authorization: Bearer \$TOKEN\" | jq '.[] | {id, name, state, hostname}'"
echo ""
echo "  # Get stats for a node:"
echo '  curl -sk https://localhost:443/api/nodes/<NODE_ID>/stats \'
echo "    -H \"Authorization: Bearer \$TOKEN\" | jq"
echo ""
echo "  # Cleanup:"
echo "  ./scripts/setup_test.sh --clean"
