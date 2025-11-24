#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Stopping Ad Regulation HTTP..."
docker compose down

echo ""
echo "✓ Ad Regulation HTTP stopped"
echo "  To remove volumes: docker compose down -v"
