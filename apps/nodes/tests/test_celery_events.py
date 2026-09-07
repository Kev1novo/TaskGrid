import threading

import pytest

pytestmark = pytest.mark.django_db


class TestWorkerReadySignal:
    def test_registers_node_and_starts_heartbeat(self, monkeypatch):
        """on_worker_ready 应该注册节点。"""
        from apps.nodes import celery_events

        calls = []

        def fake_register(node_name, hostname=None):
            calls.append(("register", node_name, hostname))

        monkeypatch.setattr("apps.nodes.services.register_node", fake_register)

        # 阻止心跳线程真的启动——设 stop 让它立即退出
        old_stop = celery_events._stop
        celery_events._stop = threading.Event()
        celery_events._stop.set()

        try:

            class FakeSender:
                hostname = "celery@test-host"

            celery_events.on_worker_ready(FakeSender())
            assert len(calls) == 1
            assert calls[0][1] == "celery@test-host"
        finally:
            celery_events._stop = old_stop  # 恢复原始 _stop


class TestWorkerShutdownSignal:
    def test_sets_stop_event(self):
        """on_worker_shutdown 应该设置 _stop 事件。"""
        from apps.nodes import celery_events

        old_stop = celery_events._stop
        celery_events._stop = threading.Event()
        celery_events._stop.clear()
        try:
            assert not celery_events._stop.is_set()
            celery_events.on_worker_shutdown(sender=None)
            assert celery_events._stop.is_set()
        finally:
            celery_events._stop = old_stop


class TestHeartbeatLoop:
    def test_calls_report_heartbeat(self, monkeypatch):
        """心跳循环应该调用 report_heartbeat。"""
        from apps.nodes import celery_events

        old_stop = celery_events._stop
        stop_event = threading.Event()
        celery_events._stop = stop_event

        # patch 心跳间隔为 0.01s，避免测试等 30 秒
        monkeypatch.setattr(celery_events, "HEARTBEAT_INTERVAL", 0.01)

        calls = []

        def fake_report(node_name, hostname=None):
            calls.append(node_name)
            stop_event.set()  # 第一次调用后就停

        monkeypatch.setattr("apps.nodes.services.report_heartbeat", fake_report)

        try:
            t = threading.Thread(
                target=celery_events._heartbeat_loop,
                args=("celery@test",),
                daemon=True,
            )
            t.start()
            t.join(timeout=5)

            assert len(calls) == 1
            assert calls[0] == "celery@test"
        finally:
            celery_events._stop = old_stop

    def test_heartbeat_continues_on_error(self, monkeypatch):
        """心跳上报失败不应该中断循环。"""
        from apps.nodes import celery_events

        old_stop = celery_events._stop
        stop_event = threading.Event()
        celery_events._stop = stop_event

        # patch 心跳间隔为 0.01s，避免测试等 30 秒
        monkeypatch.setattr(celery_events, "HEARTBEAT_INTERVAL", 0.01)

        call_count = 0

        def fake_report(node_name, hostname=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("boom")
            stop_event.set()

        monkeypatch.setattr("apps.nodes.services.report_heartbeat", fake_report)

        try:
            t = threading.Thread(
                target=celery_events._heartbeat_loop,
                args=("celery@test",),
                daemon=True,
            )
            t.start()
            t.join(timeout=5)

            assert call_count == 2
        finally:
            celery_events._stop = old_stop
