#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
docker build -t taskgrid-sandbox:latest -f docker/sandbox/Dockerfile docker/sandbox
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
