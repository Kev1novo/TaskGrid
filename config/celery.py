import os

from celery import Celery
from celery.schedules import crontab
from kombu import Queue

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
# ⚠️ 生产部署时 docker-compose 必须显式设置 DJANGO_SETTINGS_MODULE=config.settings.prod

app = Celery("taskgrid")

app.config_from_object("django.conf:settings", namespace="CELERY")

# ——— 4 级优先级队列 ———
# CRITICAL / HIGH / NORMAL / LOW，worker 按队列优先级消费。
# 不设 task_acks_late（默认 False）= 任务失败不重试（幂等性靠 DB 守门）。
# 不指定 -Q 时 worker 会自动监听所有定义的队列。
app.conf.task_queues = [
    Queue("critical", routing_key="critical.#"),
    Queue("high", routing_key="high.#"),
    Queue("default", routing_key="default.#"),
    Queue("low", routing_key="low.#"),
]

# ——— 定时任务 ———
# Celery Beat 调度：每天凌晨 3 点清理 30 天前的终态任务。
# 生产环境需额外启动 beat 进程：celery -A config beat -l info
app.conf.beat_schedule = {
    "cleanup-old-tasks-daily": {
        "task": "apps.tasks.tasks.cleanup_old_tasks",
        "schedule": crontab(hour=3, minute=7),  # 凌晨 3:07，避整点尖峰
        "kwargs": {"days": 30, "batch_size": 500},
    },
}

app.autodiscover_tasks()
