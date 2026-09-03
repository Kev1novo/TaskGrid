from django.db import models

# ——————————————————————————————————————————————————————
# Node 模型：一台 worker 机器就是一个 Node
#
# 每台 worker 启动时注册自己，然后每 30 秒上报一次心跳（带 CPU/内存数据）
# 调度器选节点时会看：
#   1. 节点是否在线（last_heartbeat 不超过 60 秒）
#   2. CPU 和内存谁更低（least_loaded 策略）
#
# 心跳超时 → 自动标记 OFFLINE → 不再分配新任务
# ——————————————————————————————————————————————————————


class Node(models.Model):
    class Status(models.TextChoices):
        ONLINE = "online", "在线"  # 心跳正常，可以接任务
        OFFLINE = "offline", "离线"  # 心跳超时或主动下线

    name = models.CharField("节点名称", max_length=100, unique=True)  # Celery hostname
    hostname = models.CharField("主机名", max_length=255, blank=True)
    ip = models.GenericIPAddressField("IP 地址", null=True, blank=True)
    status = models.CharField(
        "状态",
        max_length=20,
        choices=Status.choices,
        default=Status.OFFLINE,  # 刚注册默认离线，等心跳上报后改 ONLINE
        db_index=True,  # select_node / mark_offline_if_stale 都按 status 查询
    )
    cpu_percent = models.FloatField("CPU 使用率(%)", default=0.0)  # 调度用：CPU 越低越优先
    mem_percent = models.FloatField("内存使用率(%)", default=0.0)  # 调度用：内存越低越优先
    last_heartbeat = models.DateTimeField(
        "最后心跳",
        null=True,
        blank=True,
        db_index=True,  # mark_offline_if_stale 按心跳时间过滤超时节点
    )
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
        """主动下线（比如 worker 进程关闭时调用）。"""
        self.status = self.Status.OFFLINE
        self.save(update_fields=["status", "updated_at"])
