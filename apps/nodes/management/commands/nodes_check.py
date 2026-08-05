"""手动触发节点故障检测：把心跳超时的节点标记为离线。

用法: python manage.py nodes_check
"""

from django.core.management.base import BaseCommand

from apps.nodes.services import mark_offline_if_stale


class Command(BaseCommand):
    help = "将心跳超时的节点标记为离线"

    def handle(self, *args, **options):
        stale = mark_offline_if_stale()
        if stale:
            self.stdout.write(self.style.WARNING(f"标记离线: {stale}"))
        else:
            self.stdout.write(self.style.SUCCESS("所有节点心跳正常"))
