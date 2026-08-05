"""节点注册、心跳、故障检测与调度选择。"""

import logging
from datetime import timedelta

import psutil
from django.utils import timezone

from .models import Node

logger = logging.getLogger(__name__)

HEARTBEAT_STALE_SECONDS = 60  # 心跳超过 60 秒未更新视为离线


def get_node(node_name):
    try:
        return Node.objects.get(name=node_name)
    except Node.DoesNotExist:
        return None


def register_node(node_name, hostname="", ip=None):
    """节点启动时注册（幂等）。"""
    node, created = Node.objects.get_or_create(
        name=node_name,
        defaults={"hostname": hostname or node_name, "ip": ip},
    )
    if created:
        logger.info("Node registered: %s", node_name)
    return node


def report_heartbeat(node_name, hostname=""):
    """节点心跳上报：更新负载与心跳时间，标记在线。"""
    node = register_node(node_name, hostname)
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory().percent
    node.cpu_percent = cpu
    node.mem_percent = mem
    node.last_heartbeat = timezone.now()
    node.status = Node.Status.ONLINE
    node.save(
        update_fields=["cpu_percent", "mem_percent", "last_heartbeat", "status", "updated_at"]
    )
    return node


def mark_offline_if_stale(timeout_seconds=HEARTBEAT_STALE_SECONDS):
    """故障检测：心跳超时的节点标记为离线，返回被标记的节点名列表。"""
    threshold = timezone.now() - timedelta(seconds=timeout_seconds)
    stale = Node.objects.filter(
        status=Node.Status.ONLINE,
        last_heartbeat__lt=threshold,
    )
    names = list(stale.values_list("name", flat=True))
    stale.update(status=Node.Status.OFFLINE)
    if names:
        logger.warning("Nodes marked offline (stale heartbeat): %s", names)
    return names


def select_node(strategy="least_loaded"):
    """调度策略：选择最适合执行任务的在线节点。"""
    mark_offline_if_stale()  # 选择前先做一次故障检测

    online = Node.objects.filter(status=Node.Status.ONLINE)

    if strategy == "round_robin":
        return online.order_by("updated_at").first()

    # 默认 least_loaded：优先 CPU 和内存占用低的节点
    return online.order_by("cpu_percent", "mem_percent").first()
