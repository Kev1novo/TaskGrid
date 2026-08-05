#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

# 阶段 3 用 solo 池避免 Windows 多进程问题
.venv/Scripts/celery -A config worker -l info -P solo &
WORKER_PID=$!

.venv/Scripts/celery -A config flower --port=5555 &
FLOWER_PID=$!

echo "Worker PID: $WORKER_PID, Flower PID: $FLOWER_PID"
echo "Flower: http://127.0.0.1:5555"
wait
