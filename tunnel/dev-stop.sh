#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Stopping Ad Regulation HTTP development containers..."
# Only stop dev containers, keep infrastructure running
docker compose -f docker-compose.yml -f compose.dev.yml stop backend-dev frontend-dev
docker compose -f docker-compose.yml -f compose.dev.yml rm -f backend-dev frontend-dev

echo ""
echo "✓ Development containers stopped (infrastructure still running)"
echo "  To stop all containers including mongodb: docker compose -f docker-compose.yml -f compose.dev.yml down"
