#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
docker compose -f docker-compose.dev.yml up -d
echo ""
echo "开发容器已启动："
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
