@echo off
cd /d "%~dp0.."
start "Celery Worker" cmd /k ".venv\Scripts\celery.exe -A config worker -l info -P solo"
start "Flower Monitor" cmd /k ".venv\Scripts\celery.exe -A config flower --port=5555"
echo Worker and Flower started. Flower: http://127.0.0.1:5555
