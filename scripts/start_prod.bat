@echo off
cd /d "%~dp0.."
docker build -t taskgrid-sandbox:latest -f docker/sandbox/Dockerfile docker/sandbox
docker compose -f docker-compose.prod.yml up -d --build
echo.
docker compose -f docker-compose.prod.yml ps
pause
