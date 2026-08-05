@echo off
cd /d "%~dp0.."
docker compose -f docker-compose.prod.yml build
echo Prod image built: taskgrid-app:latest
