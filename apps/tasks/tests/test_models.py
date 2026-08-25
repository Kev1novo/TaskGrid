import pytest

from apps.tasks.models import Task

pytestmark = pytest.mark.django_db


def _task(user, status):
    return Task(name="t", owner=user, status=status)


def test_pending_to_running(user):
    task = _task(user, Task.Status.PENDING)
    task.transit(Task.Status.RUNNING)
    assert task.status == Task.Status.RUNNING


def test_running_to_success(user):
    task = _task(user, Task.Status.RUNNING)
    task.transit(Task.Status.SUCCESS)
    assert task.status == Task.Status.SUCCESS


def test_running_to_failed(user):
    task = _task(user, Task.Status.RUNNING)
    task.transit(Task.Status.FAILED)
    assert task.status == Task.Status.FAILED


def test_running_to_timeout(user):
    task = _task(user, Task.Status.RUNNING)
    task.transit(Task.Status.TIMEOUT)
    assert task.status == Task.Status.TIMEOUT


def test_pending_to_cancelled(user):
    task = _task(user, Task.Status.PENDING)
    task.transit(Task.Status.CANCELLED)
    assert task.status == Task.Status.CANCELLED


def test_running_to_cancelled(user):
    task = _task(user, Task.Status.RUNNING)
    task.transit(Task.Status.CANCELLED)
    assert task.status == Task.Status.CANCELLED


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (Task.Status.PENDING, Task.Status.SUCCESS),
        (Task.Status.PENDING, Task.Status.FAILED),
        (Task.Status.PENDING, Task.Status.TIMEOUT),
        (Task.Status.RUNNING, Task.Status.PENDING),
        (Task.Status.SUCCESS, Task.Status.RUNNING),
        (Task.Status.SUCCESS, Task.Status.FAILED),
        (Task.Status.FAILED, Task.Status.RUNNING),
        (Task.Status.TIMEOUT, Task.Status.RUNNING),
        (Task.Status.CANCELLED, Task.Status.PENDING),
    ],
)
def test_illegal_transitions_raise(user, start, target):
    task = _task(user, start)
    with pytest.raises(ValueError):
        task.transit(target)
