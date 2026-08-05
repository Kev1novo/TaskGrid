@echo off
cd /d "%~dp0.."
docker-compose -f docker-compose.dev.yml up -d
echo.
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
pause
