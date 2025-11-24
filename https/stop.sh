#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Stopping Ad Regulation HTTPS..."
docker compose down

echo ""
echo "✓ Ad Regulation HTTPS stopped"
echo "  To remove volumes: docker compose down -v"
