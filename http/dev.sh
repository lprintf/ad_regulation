#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Starting Ad Regulation HTTP (development mode)..."
docker compose -f docker-compose.yml -f compose.dev.yml up -d

echo ""
echo "✓ Ad Regulation HTTP development environment started"
echo "  Production: http://fb.\${DOMAIN} (with OIDC auth)"
echo "  Development: http://fb-dev.\${DOMAIN} (no auth)"
echo ""
echo "Check status: docker compose -f docker-compose.yml -f compose.dev.yml ps"
echo "View logs:    docker compose -f docker-compose.yml -f compose.dev.yml logs -f backend-dev"
