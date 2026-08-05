"""Celery worker 生命周期钩子：启动时注册节点，周期上报心跳。

心跳必须在每个 worker 进程内自己上报（后台线程），不能用 beat 派发——
beat 派发的任务会被任意 worker 消费，无法代表"本节点"的负载。
"""

import logging
import socket
import threading

from celery.signals import worker_ready, worker_shutdown

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30  # 秒

_stop = threading.Event()


def _heartbeat_loop(node_name):
    from .services import report_heartbeat

    logger.info("Heartbeat thread started for %s", node_name)
    while not _stop.wait(HEARTBEAT_INTERVAL):
        try:
            report_heartbeat(node_name, hostname=socket.gethostname())
        except Exception:
            logger.exception("Heartbeat report failed for %s", node_name)


@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    from .services import register_node

    node_name = sender.hostname
    register_node(node_name, hostname=socket.gethostname())
    _stop.clear()
    t = threading.Thread(target=_heartbeat_loop, args=(node_name,), daemon=True)
    t.start()


@worker_shutdown.connect
def on_worker_shutdown(sender, **kwargs):
    _stop.set()
