@echo off
cd /d "%~dp0.."
start "Celery Beat" cmd /k ".venv\Scripts\celery.exe -A config beat -l info"
echo Celery Beat started. Scheduled tasks: cleanup_old_tasks (daily 3:07 AM)