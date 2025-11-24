#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Stopping Ad Regulation HTTPS development mode..."
# HTTPS mode uses overlay pattern, so we restart without dev config
docker compose -f docker-compose.yml -f compose.dev.yml down
docker compose up -d

echo ""
echo "✓ Development mode stopped, switched back to production mode"
echo "  Access: https://fb.\${DOMAIN} (with OIDC auth)"
echo ""
echo "To completely stop: ./stop.sh"
