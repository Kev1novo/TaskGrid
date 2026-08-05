from django.apps import AppConfig


class NodesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.nodes"
    verbose_name = "节点管理"

    def ready(self):
        # 注册 Celery worker 心跳信号
        from . import celery_events  # noqa: F401
