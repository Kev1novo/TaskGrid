"""故障转移：把分配给已离线节点、仍卡在 running 的任务重置为 pending 并重新入队。

用法: python manage.py reschedule_tasks
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.nodes.models import Node
from apps.nodes.services import mark_offline_if_stale
from apps.tasks.models import Task

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "将分配给离线节点且状态为 running 的任务重新调度"

    def handle(self, *args, **options):
        mark_offline_if_stale()

        # 找出分配给离线节点、且还挂着 running 的任务
        offline_nodes = set(
            Node.objects.filter(status=Node.Status.OFFLINE).values_list("name", flat=True)
        )
        stuck = Task.objects.filter(status=Task.Status.RUNNING, worker_id__in=offline_nodes)

        rescheduled = 0
        for task in stuck:
            task.status = Task.Status.PENDING
            task.worker_id = ""
            task.error_message = f"{timezone.now():%Y-%m-%d %H:%M:%S} 节点离线，任务重新调度"
            task.save(update_fields=["status", "worker_id", "error_message", "updated_at"])

            from apps.tasks.tasks import execute_task

            execute_task.delay(task.id)
            rescheduled += 1
            self.stdout.write(self.style.WARNING(f"重新调度: {task.id}"))

        if rescheduled == 0:
            self.stdout.write(self.style.SUCCESS("没有需要重新调度的任务"))
