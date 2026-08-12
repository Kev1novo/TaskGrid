"""Celery worker 生命周期钩子：启动时注册节点，运行中周期上报心跳。

心跳必须在每个 worker 进程内自己上报（后台线程），不能用 beat 派发——
beat 派发的任务会被任意 worker 消费，无法代表"本节点"的负载。

实现方式：
  worker 启动 → on_worker_ready 触发 → 注册节点 + 开后台线程
  后台线程 → 每 30 秒调 report_heartbeat() 上报 CPU/内存
  worker 关闭 → on_worker_shutdown 触发 → 停掉后台线程
"""

import logging
import socket
import threading

from celery.signals import worker_ready, worker_shutdown

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30  # 心跳间隔（秒）

_stop = threading.Event()  # 信号量：设为 True 时心跳线程退出


def _heartbeat_loop(node_name):
    """心跳循环：每 30 秒上报一次，直到收到停止信号。"""
    from .services import report_heartbeat

    logger.info("Heartbeat thread started for %s", node_name)
    while not _stop.wait(HEARTBEAT_INTERVAL):  # wait(30) = "睡 30 秒，中间如果收到停止信号就提前醒"
        try:
            report_heartbeat(node_name, hostname=socket.gethostname())
        except Exception:
            logger.exception("Heartbeat report failed for %s", node_name)


# ——— Celery 信号 ———
# 这些函数会在 worker 生命周期事件发生时自动被调用


@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    """worker 启动完成时触发：注册节点 + 启动心跳线程。"""
    from .services import register_node

    node_name = sender.hostname  # Celery 的 hostname，比如 celery@DESKTOP-xxx
    register_node(node_name, hostname=socket.gethostname())
    _stop.clear()  # 重置停止信号（防止重启时残留）
    t = threading.Thread(target=_heartbeat_loop, args=(node_name,), daemon=True)
    t.start()  # daemon=True → 主进程退出时这个线程自动结束


@worker_shutdown.connect
def on_worker_shutdown(sender, **kwargs):
    """worker 关闭时触发：通知心跳线程停止。"""
    _stop.set()
