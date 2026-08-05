import uuid

from django.db import models

from apps.users.models import User


class Task(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "待执行"
        RUNNING = "running", "执行中"
        SUCCESS = "success", "成功"
        FAILED = "failed", "失败"
        TIMEOUT = "timeout", "超时"
        CANCELLED = "cancelled", "已取消"

    class Priority(models.IntegerChoices):
        LOW = 1, "低"
        NORMAL = 2, "普通"
        HIGH = 3, "高"
        CRITICAL = 4, "紧急"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField("任务名称", max_length=200)
    task_type = models.CharField("任务类型", max_length=50, default="python_script")
    code = models.TextField("执行代码/命令", blank=True)
    params = models.JSONField("任务参数", default=dict, blank=True)
    status = models.CharField(
        "状态",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    priority = models.IntegerField(
        "优先级",
        choices=Priority.choices,
        default=Priority.NORMAL,
    )
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="tasks",
        verbose_name="创建者",
    )
    worker_id = models.CharField("执行节点", max_length=100, blank=True)
    result = models.JSONField("执行结果", default=dict, blank=True)
    error_message = models.TextField("错误信息", blank=True)
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "tasks"
        ordering = ["-priority", "-created_at"]
        verbose_name = "任务"
        verbose_name_plural = "任务"

    def __str__(self):
        return f"{self.name} ({self.status})"

    @property
    def duration(self):
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def transit(self, new_status):
        """状态机：校验并执行状态转移"""
        allowed = {
            self.Status.PENDING: [self.Status.RUNNING, self.Status.CANCELLED],
            self.Status.RUNNING: [self.Status.SUCCESS, self.Status.FAILED, self.Status.TIMEOUT],
            self.Status.SUCCESS: [],
            self.Status.FAILED: [],
            self.Status.TIMEOUT: [],
            self.Status.CANCELLED: [],
        }
        if new_status not in allowed.get(self.status, []):
            raise ValueError(f"不允许从 {self.status} 转移到 {new_status}")
        self.status = new_status
