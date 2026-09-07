@echo off
cd /d "%~dp0.."
start "Celery Worker" cmd /k ".venv\Scripts\celery.exe -A config worker -l info -P solo -Q critical,high,default,low"
start "Flower Monitor" cmd /k ".venv\Scripts\celery.exe -A config flower --port=5555 --basic_auth=admin:taskgrid-flower"
echo Worker and Flower started. Flower: http://127.0.0.1:5555 (admin / taskgrid-flower)
echo Hint: run scripts\start_beat.bat to start Celery Beat (scheduled cleanup)
