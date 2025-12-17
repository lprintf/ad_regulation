#!/bin/bash
set -e

cd "$(dirname "$0")"

# 读取 .env 文件中的变量
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# 解析参数
DUAL_DOMAIN=false
while [[ $# -gt 0 ]]; do
  case $1 in
    --dual-domain|-d)
      DUAL_DOMAIN=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--dual-domain|-d]"
      exit 1
      ;;
  esac
done

# 选择域名配置文件
if [ "$DUAL_DOMAIN" = true ]; then
  PROD_DOMAIN_CONFIG="compose.dual-domain.yml"
  DEV_DOMAIN_CONFIG="compose.dev-dual.yml"
  echo "Starting Ad Regulation (development mode with dual domains)..."
else
  PROD_DOMAIN_CONFIG="compose.single-domain.yml"
  DEV_DOMAIN_CONFIG="compose.dev-single.yml"
  echo "Starting Ad Regulation (development mode)..."
fi

# 启动服务
docker compose -f docker-compose.yml -f "$PROD_DOMAIN_CONFIG" -f compose.dev.yml -f "$DEV_DOMAIN_CONFIG" up -d

echo ""
echo "✓ Ad Regulation development environment started"
if [ "$DUAL_DOMAIN" = true ]; then
  echo "  Production: https://${COMPOSE_PROJECT_NAME}.${DOMAIN} or https://${COMPOSE_PROJECT_NAME}.${DOMAIN2} (with OIDC auth)"
  echo "  Development: https://${COMPOSE_PROJECT_NAME}-dev.${DOMAIN} or https://${COMPOSE_PROJECT_NAME}-dev.${DOMAIN2} (no auth)"
else
  echo "  Production: https://${COMPOSE_PROJECT_NAME}.${DOMAIN} (with OIDC auth)"
  echo "  Development: https://${COMPOSE_PROJECT_NAME}-dev.${DOMAIN} (no auth)"
fi
echo "  Local test: curl --resolve ${COMPOSE_PROJECT_NAME}-dev.${DOMAIN}:8080:127.0.0.1 http://${COMPOSE_PROJECT_NAME}-dev.${DOMAIN}:8080"
echo ""
echo "Check status: docker compose ps"
echo "View logs:    docker compose logs -f backend-dev"
