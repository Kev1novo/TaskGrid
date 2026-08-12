import uuid

from django.db import models

from apps.users.models import User

# ——————————————————————————————————————————————————————
# Task 模型：项目的核心——一个 Task 就是"一段待执行的代码"
#
# 生命周期：
#   用户提交 → PENDING（排队）
#     → Celery worker 收到 → RUNNING（执行中）
#       → 代码正常跑完 → SUCCESS
#       → 代码报错 / OOM → FAILED
#       → 超过时限 → TIMEOUT
#     用户在排队阶段取消 → CANCELLED
#
# 关键设计：status 不是随便改的字段，只能通过 transit() 改
#   → "状态机收口"：所有状态变更走同一道门，非法转移直接报错
# ——————————————————————————————————————————————————————


class Task(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "待执行"  # 刚提交，等待 worker 取走
        RUNNING = "running", "执行中"  # worker 正在跑
        SUCCESS = "success", "成功"  # 代码正常退出（exit_code=0）
        FAILED = "failed", "失败"  # 代码报错 / OOM 被系统杀死
        TIMEOUT = "timeout", "超时"  # 超过时限，被强制终止
        CANCELLED = "cancelled", "已取消"  # 用户在排队阶段手动取消

    class Priority(models.IntegerChoices):
        LOW = 1, "低"
        NORMAL = 2, "普通"
        HIGH = 3, "高"
        CRITICAL = 4, "紧急"

    # ——— 基本字段 ———
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField("任务名称", max_length=200)  # 给人看的名字，比如 "计算圆周率"
    task_type = models.CharField("任务类型", max_length=50, default="python_script")
    code = models.TextField("执行代码/命令", blank=True)  # 用户提交的 Python 代码
    params = models.JSONField("任务参数", default=dict, blank=True)  # timeout 等参数放这里
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

    # ——— 关联 ———
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,  # 删除用户 → 连任务一起删
        related_name="tasks",  # 反查：user.tasks.all() 拿到这个用户的所有任务
        verbose_name="创建者",
    )
    worker_id = models.CharField(
        "执行节点", max_length=100, blank=True
    )  # 哪个 worker 机器在执行这个任务

    # ——— 执行结果 ———
    result = models.JSONField("执行结果", default=dict, blank=True)  # 存 output + duration
    error_message = models.TextField("错误信息", blank=True)  # 失败时填原因

    # ——— 时间戳 ———
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "tasks"
        ordering = ["-priority", "-created_at"]  # 优先级高的排前面
        verbose_name = "任务"
        verbose_name_plural = "任务"

    def __str__(self):
        return f"{self.name} ({self.status})"

    @property
    def duration(self):
        """任务跑了多久（秒）。只有跑完的任务才有。"""
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def transit(self, new_status):
        """状态机：校验并执行状态转移。
        这是全项目最关键的约束——关卡表控制哪些状态转换是合法的。

        合法转移：
          PENDING  → RUNNING / CANCELLED
          RUNNING  → SUCCESS / FAILED / TIMEOUT
          SUCCESS   → 不可再变（终态）
          FAILED    → 不可再变（终态）
          TIMEOUT   → 不可再变（终态）
          CANCELLED → 不可再变（终态）

        举例：已经 SUCCESS 的任务不能再改成 RUNNING（会抛 ValueError）
        """
        # 关卡表：当前状态 → 允许去的状态列表
        allowed = {
            self.Status.PENDING: [self.Status.RUNNING, self.Status.CANCELLED],
            self.Status.RUNNING: [self.Status.SUCCESS, self.Status.FAILED, self.Status.TIMEOUT],
            # 以下都是终态，不允许再跳走
            self.Status.SUCCESS: [],
            self.Status.FAILED: [],
            self.Status.TIMEOUT: [],
            self.Status.CANCELLED: [],
        }
        if new_status not in allowed.get(self.status, []):
            raise ValueError(f"不允许从 {self.status} 转移到 {new_status}")
        self.status = new_status
