#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Starting Ad Regulation HTTPS (production mode)..."
docker compose up -d

echo ""
echo "✓ Ad Regulation HTTPS started successfully"
echo "  Access: https://fb.\${DOMAIN}"
echo ""
echo "Check status: docker compose ps"
echo "View logs:    docker compose logs -f"
