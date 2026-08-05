import logging
import traceback

from celery import shared_task
from django.apps import apps
from django.utils import timezone

from apps.logs.services import index_task_log
from apps.sandbox.executor import SandboxExecutor

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def execute_task(self, task_id):
    """异步执行任务：在 Docker 沙箱中运行用户代码"""
    Task = apps.get_model("tasks", "Task")

    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        logger.error("Task %s not found", task_id)
        return

    # 只允许 pending 状态进入执行
    if task.status != Task.Status.PENDING:
        logger.warning("Task %s status is %s, skip", task_id, task.status)
        return

    try:
        task.transit(Task.Status.RUNNING)
        task.started_at = timezone.now()
        task.worker_id = self.request.hostname or "unknown-worker"
        task.save()

        logger.info("Start executing task %s on %s", task_id, task.worker_id)

        result = SandboxExecutor().execute(
            code=task.code,
            timeout=task.params.get("timeout") or None,
        )

        task.result = {
            "output": result.output,
            "duration": round(result.duration, 2),
        }

        if result.timed_out:
            task.transit(Task.Status.TIMEOUT)
        elif result.oom:
            task.error_message = "内存超限，任务被强制终止"
            task.transit(Task.Status.FAILED)
        elif result.success:
            task.transit(Task.Status.SUCCESS)
        else:
            task.error_message = result.output or f"退出码 {result.exit_code}"
            task.transit(Task.Status.FAILED)

        task.finished_at = timezone.now()
        task.save()
        logger.info("Task %s done, status=%s", task_id, task.status)

        # 写入 ES（失败不影响任务主流程）
        index_task_log(task)

    except Exception as exc:
        logger.exception("Task %s failed: %s", task_id, exc)
        try:
            task.refresh_from_db()
            task.error_message = f"{exc}\n{traceback.format_exc()}"
            task.transit(Task.Status.FAILED)
            task.finished_at = timezone.now()
            task.save()
        except Exception:
            logger.exception("Failed to update task %s status", task_id)

        # 基础设施类异常（非代码逻辑错误）自动重试
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
