#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Starting Ad Regulation HTTPS (development mode)..."
docker compose -f docker-compose.yml -f compose.dev.yml up -d

echo ""
echo "✓ Ad Regulation HTTPS development environment started"
echo "  Production: https://fb.\${DOMAIN} (with OIDC auth)"
echo "  Development: https://fb-dev.\${DOMAIN} (direct backend access, no auth)"
echo ""
echo "Check status: docker compose -f docker-compose.yml -f compose.dev.yml ps"
echo "View logs:    docker compose -f docker-compose.yml -f compose.dev.yml logs -f backend"
