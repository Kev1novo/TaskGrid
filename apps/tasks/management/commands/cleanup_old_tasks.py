"""清理 N 天前的终态任务及关联 ES 日志。

用法:
  python manage.py cleanup_old_tasks --days=30          # 清理 30 天前的
  python manage.py cleanup_old_tasks --days=7 --dry-run  # 预览，不真删
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tasks.models import Task


class Command(BaseCommand):
    help = "清理 N 天前的终态任务（SUCCESS/FAILED/TIMEOUT/CANCELLED）"

    TERMINAL_STATES = [
        Task.Status.SUCCESS,
        Task.Status.FAILED,
        Task.Status.TIMEOUT,
        Task.Status.CANCELLED,
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="清理 N 天前创建的任务（默认 30）",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="预览模式：只输出将要删除的数量，不真删",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="每批删除数量（默认 500）",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]

        cutoff = timezone.now() - timedelta(days=days)
        qs = Task.objects.filter(
            status__in=self.TERMINAL_STATES,
            created_at__lt=cutoff,
        )

        # 先 count，再分批删，避免一次性删除海量数据锁表太久
        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS(f"没有 {days} 天前的终态任务需要清理"))
            return

        task_ids = list(qs.values_list("id", flat=True)[:total])

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"[DRY-RUN] 将要删除 {total} 个 {days} 天前的终态任务")
            )
            return

        deleted = 0
        for i in range(0, len(task_ids), batch_size):
            batch = task_ids[i : i + batch_size]
            count, _ = Task.objects.filter(id__in=batch).delete()
            deleted += count

        # 清理关联的 ES 日志（ES 挂了不影响）
        try:
            from apps.logs.services import delete_task_logs

            delete_task_logs(task_ids)
        except Exception:
            self.stdout.write(self.style.WARNING("ES 日志清理失败（不影响任务清理）"))

        self.stdout.write(self.style.SUCCESS(f"已清理 {deleted} 个 {days} 天前的终态任务"))
