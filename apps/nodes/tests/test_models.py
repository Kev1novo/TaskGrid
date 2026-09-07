import pytest
from django.db import IntegrityError

from apps.nodes.models import Node

pytestmark = pytest.mark.django_db


class TestNodeModel:
    def test_default_status_offline(self):
        """新注册的节点默认离线，等心跳上报后才变 ONLINE。"""
        node = Node.objects.create(name="celery@worker1")
        assert node.status == Node.Status.OFFLINE

    def test_mark_offline(self):
        """mark_offline() 把节点状态改为离线。"""
        node = Node.objects.create(name="celery@worker1", status=Node.Status.ONLINE)
        node.mark_offline()
        node.refresh_from_db()
        assert node.status == Node.Status.OFFLINE

    def test_str_method(self):
        """__str__ 显示节点名和中文状态。"""
        node = Node.objects.create(name="celery@worker1", status=Node.Status.ONLINE)
        assert str(node) == "celery@worker1 (在线)"

    def test_unique_name(self):
        """节点名必须唯一。"""
        Node.objects.create(name="celery@worker1")
        with pytest.raises(IntegrityError):
            Node.objects.create(name="celery@worker1")

    def test_ordering_by_last_heartbeat_desc(self):
        """默认按最后心跳时间倒序排列。"""
        from datetime import timedelta

        from django.utils import timezone

        n1 = Node.objects.create(
            name="older", last_heartbeat=timezone.now() - timedelta(seconds=60)
        )
        n2 = Node.objects.create(name="newer", last_heartbeat=timezone.now())
        nodes = list(Node.objects.all())
        assert nodes[0] == n2
        assert nodes[1] == n1

    def test_cpu_mem_defaults(self):
        """CPU 和内存默认值都是 0.0。"""
        node = Node.objects.create(name="celery@worker1")
        assert node.cpu_percent == 0.0
        assert node.mem_percent == 0.0
