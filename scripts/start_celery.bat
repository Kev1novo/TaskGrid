@echo off
cd /d "%~dp0.."
set FLOWER_PASSWORD=%FLOWER_PASSWORD:taskgrid-flower%
start "Celery Worker" cmd /k ".venv\Scripts\celery.exe -A config worker -l info -P solo -Q critical,high,default,low"
start "Flower Monitor" cmd /k ".venv\Scripts\celery.exe -A config flower --port=5555 --basic_auth=admin:%FLOWER_PASSWORD%"
echo Worker and Flower started. Flower: http://127.0.0.1:5555 (admin / %%FLOWER_PASSWORD%%)
