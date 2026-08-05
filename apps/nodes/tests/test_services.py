from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.nodes import services
from apps.nodes.models import Node

pytestmark = pytest.mark.django_db


def test_register_node_creates():
    node = services.register_node("celery@host1")
    assert Node.objects.count() == 1
    assert node.name == "celery@host1"
    assert node.hostname == "celery@host1"


def test_register_node_idempotent():
    services.register_node("celery@host1")
    services.register_node("celery@host1")
    assert Node.objects.count() == 1


def test_report_heartbeat_updates_load(monkeypatch):
    monkeypatch.setattr("apps.nodes.services.psutil.cpu_percent", lambda interval=None: 12.5)
    monkeypatch.setattr(
        "apps.nodes.services.psutil.virtual_memory",
        lambda: SimpleNamespace(percent=50.0),
    )
    node = services.report_heartbeat("n1")
    assert node.status == Node.Status.ONLINE
    assert node.cpu_percent == 12.5
    assert node.mem_percent == 50.0
    assert node.last_heartbeat is not None


def test_mark_offline_if_stale():
    Node.objects.create(name="fresh", status=Node.Status.ONLINE, last_heartbeat=timezone.now())
    Node.objects.create(
        name="stale",
        status=Node.Status.ONLINE,
        last_heartbeat=timezone.now() - timedelta(seconds=120),
    )
    Node.objects.create(
        name="already-off",
        status=Node.Status.OFFLINE,
        last_heartbeat=timezone.now() - timedelta(seconds=120),
    )
    names = services.mark_offline_if_stale()
    assert "stale" in names
    assert "fresh" not in names
    assert Node.objects.get(name="stale").status == Node.Status.OFFLINE
    assert Node.objects.get(name="fresh").status == Node.Status.ONLINE


def test_select_node_none_when_no_online():
    assert services.select_node() is None


def test_select_node_least_loaded():
    Node.objects.create(name="busy", status=Node.Status.ONLINE, cpu_percent=80.0, mem_percent=70.0)
    Node.objects.create(name="idle", status=Node.Status.ONLINE, cpu_percent=5.0, mem_percent=10.0)
    assert services.select_node().name == "idle"


def test_select_node_round_robin():
    Node.objects.create(name="n1", status=Node.Status.ONLINE)
    Node.objects.create(name="n2", status=Node.Status.ONLINE)
    assert services.select_node("round_robin").name in ("n1", "n2")
