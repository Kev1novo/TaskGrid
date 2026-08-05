import pytest

from apps.tasks.models import Task

pytestmark = pytest.mark.django_db

TASKS = "/api/v1/tasks/"


@pytest.fixture(autouse=True)
def _block_celery(monkeypatch):
    """API 测试里不真的派发/执行 Celery 任务。"""
    monkeypatch.setattr("apps.tasks.views.execute_task.delay", lambda task_id: None)


def _other_user():
    from apps.users.models import User

    return User.objects.create_user(username="bob", password="bobpass123")


def test_create_requires_auth(api_client):
    resp = api_client.post(TASKS, {"name": "t", "code": "print(1)"}, format="json")
    assert resp.status_code == 401


def test_create_success(auth_client, user, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "apps.tasks.views.select_node",
        lambda strategy="least_loaded": SimpleNamespace(name="node1"),
    )
    resp = auth_client.post(TASKS, {"name": "t", "code": "print(1)"}, format="json")
    assert resp.status_code == 201
    assert resp.data["id"]
    assert resp.data["status"] == "pending"
    assert resp.data["owner"] == user.id
    assert resp.data["worker_id"] == "node1"


def test_list_only_own_tasks(auth_client, user):
    Task.objects.create(name="mine", owner=user, code="print(1)")
    Task.objects.create(name="others", owner=_other_user(), code="print(2)")
    resp = auth_client.get(TASKS)
    names = [t["name"] for t in resp.data["results"]]
    assert "mine" in names
    assert "others" not in names


def test_list_admin_sees_all(admin_client, user):
    Task.objects.create(name="mine", owner=user, code="print(1)")
    Task.objects.create(name="others", owner=_other_user(), code="print(2)")
    resp = admin_client.get(TASKS)
    names = [t["name"] for t in resp.data["results"]]
    assert "mine" in names
    assert "others" in names


def test_retrieve_other_task_denied(auth_client, user):
    # get_queryset 按 owner 过滤，别人的任务对普通用户是 404（不泄露存在性）
    task = Task.objects.create(name="secret", owner=_other_user(), code="print(1)")
    assert auth_client.get(f"{TASKS}{task.id}/").status_code == 404


def test_destroy_other_task_denied(auth_client, user):
    task = Task.objects.create(name="secret", owner=_other_user(), code="print(1)")
    assert auth_client.delete(f"{TASKS}{task.id}/").status_code == 404


def test_status_action_valid(auth_client, user):
    task = Task.objects.create(name="t", owner=user, code="print(1)", status=Task.Status.PENDING)
    resp = auth_client.post(f"{TASKS}{task.id}/status/", {"status": "running"}, format="json")
    assert resp.status_code == 200
    task.refresh_from_db()
    assert task.status == Task.Status.RUNNING


def test_status_action_illegal_400(auth_client, user):
    task = Task.objects.create(name="t", owner=user, code="print(1)", status=Task.Status.PENDING)
    resp = auth_client.post(f"{TASKS}{task.id}/status/", {"status": "success"}, format="json")
    assert resp.status_code == 400


def test_cancel_pending(auth_client, user):
    task = Task.objects.create(name="t", owner=user, code="print(1)", status=Task.Status.PENDING)
    resp = auth_client.post(f"{TASKS}{task.id}/cancel/")
    assert resp.status_code == 200
    task.refresh_from_db()
    assert task.status == Task.Status.CANCELLED


def test_cancel_running_400(auth_client, user):
    task = Task.objects.create(name="t", owner=user, code="print(1)", status=Task.Status.RUNNING)
    resp = auth_client.post(f"{TASKS}{task.id}/cancel/")
    assert resp.status_code == 400
