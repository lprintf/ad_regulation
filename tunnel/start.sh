#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Starting Ad Regulation HTTP (production mode)..."
docker compose up -d

echo ""
echo "✓ Ad Regulation HTTP started successfully"
echo "  Access: http://fb.\${DOMAIN}"
echo ""
echo "Check status: docker compose ps"
echo "View logs:    docker compose logs -f"
