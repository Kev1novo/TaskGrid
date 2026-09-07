from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.tasks.models import Task

pytestmark = pytest.mark.django_db


def _create_task_at(owner, name, status, days_ago):
    """创建一个 created_at 为 days_ago 天前的任务。
    auto_now_add 阻止直接赋值，所以先创建再用 QuerySet.update() 绕过。"""
    task = Task.objects.create(name=name, owner=owner, code="print(1)", status=status)
    Task.objects.filter(id=task.id).update(created_at=timezone.now() - timedelta(days=days_ago))
    return task


def test_no_old_tasks(user):
    """没有旧任务时输出成功信息。"""
    out = StringIO()
    call_command("cleanup_old_tasks", stdout=out)
    assert "没有" in out.getvalue()


def test_skips_recent_terminal(user):
    """昨天的终态任务不应被清理。"""
    _create_task_at(user, "recent", Task.Status.SUCCESS, days_ago=1)
    call_command("cleanup_old_tasks", days=7)
    assert Task.objects.count() == 1


def test_cleans_old_terminal(user):
    """31 天前的终态任务应被清理。"""
    _create_task_at(user, "s1", Task.Status.SUCCESS, days_ago=31)
    _create_task_at(user, "f1", Task.Status.FAILED, days_ago=31)
    _create_task_at(user, "t1", Task.Status.TIMEOUT, days_ago=31)
    _create_task_at(user, "c1", Task.Status.CANCELLED, days_ago=31)
    call_command("cleanup_old_tasks", days=30)
    assert Task.objects.count() == 0


def test_preserves_pending_and_running(user):
    """PENDING 和 RUNNING 的任务无论多老都不删。"""
    _create_task_at(user, "p1", Task.Status.PENDING, days_ago=60)
    _create_task_at(user, "r1", Task.Status.RUNNING, days_ago=60)
    call_command("cleanup_old_tasks", days=30)
    assert Task.objects.count() == 2


def test_dry_run_does_not_delete(user):
    """--dry-run 只预览不删除。"""
    _create_task_at(user, "old", Task.Status.SUCCESS, days_ago=31)
    out = StringIO()
    call_command("cleanup_old_tasks", days=30, dry_run=True, stdout=out)
    assert "DRY-RUN" in out.getvalue()
    assert Task.objects.count() == 1


def test_custom_days(user):
    """--days 参数改变清理阈值。"""
    _create_task_at(user, "old", Task.Status.SUCCESS, days_ago=10)
    call_command("cleanup_old_tasks", days=7)
    assert Task.objects.count() == 0
