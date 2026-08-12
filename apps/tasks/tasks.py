import logging
import traceback

from celery import shared_task
from django.apps import apps
from django.utils import timezone

from apps.logs.services import index_task_log
from apps.sandbox.executor import SandboxExecutor

logger = logging.getLogger(__name__)


# ——————————————————————————————————————————————————————
# Celery 异步任务：这是 worker 进程"干活"的入口
#
# 流程：
#   API 调了 execute_task.delay(task_id)
#     → 任务进入 Redis 队列
#     → Celery worker 从队列取走
#     → 调用这个函数
#     → PENDING → RUNNING → (SUCCESS / FAILED / TIMEOUT)
#     → 结果写入 ES（失败不阻塞主流程）
#
# @shared_task 参数：
#   bind=True       → self 代表任务实例，可以用 self.retry() 重试
#   max_retries=3   → 最多重试 3 次（基础设施异常才会触发重试）
#   default_retry_delay=10 → 重试间隔 10 秒
# ——————————————————————————————————————————————————————


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def execute_task(self, task_id):
    """异步执行任务：在 Docker 沙箱中运行用户代码"""

    # 用 apps.get_model 而不是直接 import Task，避免 Celery 启动时的循环导入
    Task = apps.get_model("tasks", "Task")

    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        logger.error("Task %s not found", task_id)
        return  # 任务不存在就不重试了，直接返回

    # 守门：只处理 PENDING 状态的任务，防止重复执行
    if task.status != Task.Status.PENDING:
        logger.warning("Task %s status is %s, skip", task_id, task.status)
        return

    try:
        # ——— 状态：排队 → 执行中 ———
        task.transit(Task.Status.RUNNING)
        task.started_at = timezone.now()
        task.worker_id = self.request.hostname or "unknown-worker"  # 记录是哪个 worker 在跑
        task.save()

        logger.info("Start executing task %s on %s", task_id, task.worker_id)

        # ——— 核心：在 Docker 沙箱里跑用户代码 ———
        result = SandboxExecutor().execute(
            code=task.code,
            timeout=task.params.get("timeout") or None,  # 用户可选自定义超时
        )

        # ——— 把沙箱结果翻译成任务状态 ———
        task.result = {
            "output": result.output,  # stdout + stderr 合并
            "duration": round(result.duration, 2),  # 执行耗时（秒）
        }

        if result.timed_out:
            task.transit(Task.Status.TIMEOUT)  # 超过时限被强杀
        elif result.oom:
            task.error_message = "内存超限，任务被强制终止"  # 退出码 137 = OOM killed
            task.transit(Task.Status.FAILED)
        elif result.success:
            task.transit(Task.Status.SUCCESS)  # exit_code=0，正常结束
        else:
            task.error_message = result.output or f"退出码 {result.exit_code}"
            task.transit(Task.Status.FAILED)  # exit_code != 0，代码报错

        task.finished_at = timezone.now()
        task.save()
        logger.info("Task %s done, status=%s", task_id, task.status)

        # ——— 写入 ES（辅助功能，失败了只记日志，不影响任务主流程） ———
        index_task_log(task)

    except Exception as exc:
        # ——— 异常处理 ———
        # 到这里说明整个 try 块里出了意外（不是代码报错，是系统级异常）
        # 比如 Docker daemon 挂了、DB 连不上了
        logger.exception("Task %s failed: %s", task_id, exc)
        try:
            task.refresh_from_db()  # 刷一下以防状态被其他线程改了
            task.error_message = f"{exc}\n{traceback.format_exc()}"
            task.transit(Task.Status.FAILED)
            task.finished_at = timezone.now()
            task.save()
        except Exception:
            logger.exception("Failed to update task %s status", task_id)

        # 自动重试：还没到最大重试次数就再试一次
        # 注意：只对基础设施异常（DB/Redis/Docker 挂）重试，用户代码报错不会进这个分支
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
