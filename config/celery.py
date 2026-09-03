import os

from celery import Celery
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

app.autodiscover_tasks()
