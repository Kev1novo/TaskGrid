import logging
import traceback

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
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


@shared_task(bind=True, max_retries=3, default_retry_delay=10, soft_time_limit=33, time_limit=38)
def execute_task(self, task_id):
    """异步执行任务：在 Docker 沙箱中运行用户代码。
    soft_time_limit=33: 沙箱默认超时 30s，给 3s 余量触发 SoftTimeLimitException
    time_limit=38:    硬限 38s（soft 之后 5s 强杀），兜底容器启动卡死等极端情况
    """

    # 用 apps.get_model 而不是直接 import Task，避免 Celery 启动时的循环导入
    Task = apps.get_model("tasks", "Task")

    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        logger.error("Task %s not found", task_id)
        return  # 任务不存在就不重试了，直接返回

    # 原子守门：UPDATE tasks SET status='running' WHERE id=task_id AND status='pending'
    # 如果同一个任务被两个 worker 同时取到，只有一个 worker 的 UPDATE 会成功（受影响行数=1），
    # 另一个受影响行数=0，直接跳过——避免了两个 worker 同时执行同一个任务。
    updated = Task.objects.filter(id=task_id, status=Task.Status.PENDING).update(
        status=Task.Status.RUNNING, started_at=timezone.now()
    )
    if not updated:
        logger.warning(
            "Task %s is no longer PENDING (already picked up by another worker or cancelled), skip",
            task_id,
        )
        return

    # 刷一下内存里的 task 对象，拿到数据库里最新的状态
    task.refresh_from_db()
    task.worker_id = self.request.hostname or "unknown-worker"

    try:
        logger.info("Start executing task %s on %s", task_id, task.worker_id)

        # ——— 取消检测回调：executor 轮询时调这个，判断用户是否请求了取消 ———
        # 不能直接读内存里的 task 对象（web 进程改的是数据库），必须每次查库。
        def _cancel_requested():
            try:
                return Task.objects.filter(id=task_id, cancel_requested_at__isnull=False).exists()
            except Exception:
                return False  # 查库失败就当没取消，别误杀

        # ——— 核心：在 Docker 沙箱里跑用户代码 ———
        result = SandboxExecutor().execute(
            code=task.code,
            timeout=task.params.get("timeout") or None,  # 用户可选自定义超时
            cancel_check=_cancel_requested,
        )

        # ——— 把沙箱结果翻译成任务状态 ———
        task.result = {
            "output": result.output,  # stdout + stderr 合并
            "duration": round(result.duration, 2),  # 执行耗时（秒）
        }

        if result.cancelled:
            task.error_message = "用户手动取消"  # 用户请求了取消，executor 强杀了容器
            task.transit(Task.Status.CANCELLED)
        elif result.timed_out:
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
        task.save(
            update_fields=[
                "status",
                "result",
                "error_message",
                "finished_at",
                "updated_at",
            ]
        )
        logger.info("Task %s done, status=%s", task_id, task.status)

        # ——— 写入 ES（辅助功能，失败了只记日志，不影响任务主流程） ———
        index_task_log(task)

    except SoftTimeLimitExceeded:
        # SoftTimeLimitException 是 Celery 层面的超时信号（soft_time_limit=33s 触发），
        # 与 Docker 沙箱超时不同——这个说明 celery 任务本身卡住了（比如 Docker daemon 无响应）。
        logger.warning("Task %s soft time limit exceeded", task_id)
        try:
            task.refresh_from_db()
            task.transit(Task.Status.TIMEOUT)
            task.error_message = "任务执行超时（Celery 软超时）"
            task.finished_at = timezone.now()
            task.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
        except Exception:
            logger.exception("Failed to update task %s after soft timeout", task_id)

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
            task.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
        except Exception:
            logger.exception("Failed to update task %s status", task_id)

        # 自动重试：还没到最大重试次数就再试一次
        # 注意：只对基础设施异常（DB/Redis/Docker 挂）重试，用户代码报错不会进这个分支
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
