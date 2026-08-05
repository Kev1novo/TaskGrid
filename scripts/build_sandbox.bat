@echo off
cd /d "%~dp0.."
docker build -t taskgrid-sandbox:latest -f docker/sandbox/Dockerfile docker/sandbox
echo Sandbox image built: taskgrid-sandbox:latest
