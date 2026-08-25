import pytest

from apps.sandbox.executor import SandboxResult
from apps.tasks.models import Task

pytestmark = pytest.mark.django_db


def _run(user, result, fake_sandbox, fake_es):
    fake_sandbox.result = result
    task = Task.objects.create(name="t", owner=user, code="print(1)", status=Task.Status.PENDING)
    from apps.tasks.tasks import execute_task

    execute_task.apply(args=[task.id])
    task.refresh_from_db()
    return task


def test_success_path(user, fake_sandbox, fake_es):
    task = _run(user, SandboxResult(exit_code=0, output="ok", duration=0.5), fake_sandbox, fake_es)
    assert task.status == Task.Status.SUCCESS
    assert task.result["output"] == "ok"
    assert task.finished_at is not None


def test_failed_path(user, fake_sandbox, fake_es):
    task = _run(
        user, SandboxResult(exit_code=1, output="boom", duration=0.1), fake_sandbox, fake_es
    )
    assert task.status == Task.Status.FAILED
    assert task.error_message


def test_timeout_path(user, fake_sandbox, fake_es):
    task = _run(
        user,
        SandboxResult(exit_code=-1, timed_out=True, duration=30.0),
        fake_sandbox,
        fake_es,
    )
    assert task.status == Task.Status.TIMEOUT


def test_oom_path(user, fake_sandbox, fake_es):
    task = _run(user, SandboxResult(exit_code=137, oom=True, duration=1.0), fake_sandbox, fake_es)
    assert task.status == Task.Status.FAILED
    assert "内存超限" in task.error_message


def test_skip_non_pending(user, fake_sandbox, fake_es):
    task = Task.objects.create(name="t", owner=user, code="print(1)", status=Task.Status.SUCCESS)
    from apps.tasks.tasks import execute_task

    execute_task.apply(args=[task.id])
    task.refresh_from_db()
    assert task.status == Task.Status.SUCCESS
    assert fake_sandbox.result.exit_code == 0  # execute 未被调用，结果未变


def test_cancelled_path(user, fake_sandbox, fake_es):
    """RUNNING 任务被取消：executor 返回 cancelled=True → 状态变 CANCELLED"""
    task = _run(
        user,
        SandboxResult(exit_code=-1, cancelled=True, duration=0.3),
        fake_sandbox,
        fake_es,
    )
    assert task.status == Task.Status.CANCELLED
    assert task.error_message == "用户手动取消"
