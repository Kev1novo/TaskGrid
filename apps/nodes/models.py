from django.db import models


class Node(models.Model):
    class Status(models.TextChoices):
        ONLINE = "online", "在线"
        OFFLINE = "offline", "离线"

    name = models.CharField("节点名称", max_length=100, unique=True)
    hostname = models.CharField("主机名", max_length=255, blank=True)
    ip = models.GenericIPAddressField("IP 地址", null=True, blank=True)
    status = models.CharField(
        "状态",
        max_length=20,
        choices=Status.choices,
        default=Status.OFFLINE,
    )
    cpu_percent = models.FloatField("CPU 使用率(%)", default=0.0)
    mem_percent = models.FloatField("内存使用率(%)", default=0.0)
    last_heartbeat = models.DateTimeField("最后心跳", null=True, blank=True)
    created_at = models.DateTimeField("注册时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "nodes"
        ordering = ["-last_heartbeat"]
        verbose_name = "工作节点"
        verbose_name_plural = "工作节点"

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    def mark_offline(self):
        self.status = self.Status.OFFLINE
        self.save(update_fields=["status", "updated_at"])
