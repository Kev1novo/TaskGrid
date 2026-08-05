from .base import *  # noqa: F401,F403

DEBUG = False

# 测试环境：Celery 同步执行，不真的发 Redis 队列
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
