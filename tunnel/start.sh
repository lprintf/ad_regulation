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
  DOMAIN_CONFIG="compose.dual-domain.yml"
  echo "Starting Ad Regulation (production mode with dual domains)..."
else
  DOMAIN_CONFIG="compose.single-domain.yml"
  echo "Starting Ad Regulation (production mode)..."
fi

# 启动服务
docker compose -f docker-compose.yml -f "$DOMAIN_CONFIG" up -d

echo ""
echo "✓ Ad Regulation started successfully"
if [ "$DUAL_DOMAIN" = true ]; then
  echo "  Access: https://${COMPOSE_PROJECT_NAME}.${DOMAIN} or https://${COMPOSE_PROJECT_NAME}.${DOMAIN2}"
else
  echo "  Access: https://${COMPOSE_PROJECT_NAME}.${DOMAIN}"
fi
echo ""
echo "Check status: docker compose ps"
echo "View logs:    docker compose logs -f"

