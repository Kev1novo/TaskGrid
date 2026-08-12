"""节点注册、心跳、故障检测与调度选择。"""

import logging
from datetime import timedelta

import psutil
from django.utils import timezone

from .models import Node

logger = logging.getLogger(__name__)

HEARTBEAT_STALE_SECONDS = 60  # 心跳超过 60 秒未更新视为离线


def get_node(node_name):
    """按名称查找一个节点。"""
    try:
        return Node.objects.get(name=node_name)
    except Node.DoesNotExist:
        return None


def register_node(node_name, hostname="", ip=None):
    """节点启动时注册（幂等——重复调用不会创建重复记录）。
    get_or_create：有则返回已有记录，没有才创建。
    """
    node, created = Node.objects.get_or_create(
        name=node_name,
        defaults={"hostname": hostname or node_name, "ip": ip},
    )
    if created:
        logger.info("Node registered: %s", node_name)
    return node


def report_heartbeat(node_name, hostname=""):
    """节点心跳上报：更新 CPU/内存负载，刷新心跳时间，标记在线。
    每 30 秒由 worker 后台线程调用一次。
    """
    node = register_node(node_name, hostname)  # 先确保节点存在（幂等）

    # 采集本机实时负载（这就是为什么心跳必须在 worker 进程内上报！）
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
    """故障检测：扫描所有 ONLINE 节点，心跳超过 60 秒没更新的标记为离线。
    返回被标记的节点名列表（用于日志和告警）。
    """
    threshold = timezone.now() - timedelta(seconds=timeout_seconds)
    stale = Node.objects.filter(
        status=Node.Status.ONLINE,
        last_heartbeat__lt=threshold,  # 最后心跳早于阈值 → 失联
    )
    names = list(stale.values_list("name", flat=True))
    stale.update(status=Node.Status.OFFLINE)
    if names:
        logger.warning("Nodes marked offline (stale heartbeat): %s", names)
    return names


def select_node(strategy="least_loaded"):
    """调度策略：从在线节点中选出最适合执行任务的那台。

    支持两种策略：
      least_loaded（默认）→ 选 CPU 和内存占用最低的节点（"能者多劳"）
      round_robin         → 按更新时间轮询（简单公平）

    调用时机：每次创建任务时（TaskViewSet.create）。
    """
    # 选节点前先做一次故障检测，把失联的踢掉
    mark_offline_if_stale()

    online = Node.objects.filter(status=Node.Status.ONLINE)

    if strategy == "round_robin":
        return online.order_by("updated_at").first()  # 最久没被选中的优先

    # 默认 least_loaded：优先选 CPU 低和内存低的节点
    return online.order_by("cpu_percent", "mem_percent").first()
