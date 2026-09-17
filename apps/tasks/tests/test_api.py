import pytest

from apps.tasks.models import Task

pytestmark = pytest.mark.django_db

TASKS = "/api/v1/tasks/"


@pytest.fixture(autouse=True)
def _block_celery(monkeypatch):
    """API 测试里不真的派发/执行 Celery 任务。"""
    monkeypatch.setattr(
        "apps.tasks.views.execute_task.apply_async",
        lambda args, queue=None, **kw: None,
    )


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


def test_cancel_running_sets_marker(auth_client, user):
    task = Task.objects.create(name="t", owner=user, code="print(1)", status=Task.Status.RUNNING)
    resp = auth_client.post(f"{TASKS}{task.id}/cancel/")
    assert resp.status_code == 202
    task.refresh_from_db()
    # 状态保持 RUNNING，但标记了 cancel_requested_at，等 worker 轮询后异步取消
    assert task.status == Task.Status.RUNNING
    assert task.cancel_requested_at is not None


def test_cancel_terminal_400(auth_client, user):
    task = Task.objects.create(name="t", owner=user, code="print(1)", status=Task.Status.SUCCESS)
    resp = auth_client.post(f"{TASKS}{task.id}/cancel/")
    assert resp.status_code == 400


def test_retry_creates_new_task(auth_client, user, monkeypatch):
    """重试终态任务 → 201，新任务复用原参数，id 不同，status=pending"""
    from types import SimpleNamespace

    monkeypatch.setattr(
        "apps.tasks.views.select_node",
        lambda strategy="least_loaded": SimpleNamespace(name="node1"),
    )
    original = Task.objects.create(
        name="t",
        owner=user,
        code="print(1)",
        params={"timeout": 10},
        priority=Task.Priority.HIGH,
        status=Task.Status.SUCCESS,
    )
    resp = auth_client.post(f"{TASKS}{original.id}/retry/")
    assert resp.status_code == 201
    assert resp.data["id"] != str(original.id)
    assert resp.data["name"] == "t"
    assert resp.data["code"] == "print(1)"
    assert resp.data["status"] == "pending"
    assert resp.data["priority"] == Task.Priority.HIGH
    assert resp.data["params"] == {"timeout": 10}
    assert resp.data["worker_id"] == "node1"


def test_retry_pending_400(auth_client, user):
    task = Task.objects.create(name="t", owner=user, code="print(1)", status=Task.Status.PENDING)
    resp = auth_client.post(f"{TASKS}{task.id}/retry/")
    assert resp.status_code == 400


def test_retry_running_400(auth_client, user):
    task = Task.objects.create(name="t", owner=user, code="print(1)", status=Task.Status.RUNNING)
    resp = auth_client.post(f"{TASKS}{task.id}/retry/")
    assert resp.status_code == 400


def test_retry_other_denied(auth_client, user):
    task = Task.objects.create(
        name="t", owner=_other_user(), code="print(1)", status=Task.Status.FAILED
    )
    resp = auth_client.post(f"{TASKS}{task.id}/retry/")
    assert resp.status_code == 404


def test_create_no_node_still_creates(auth_client, user, monkeypatch):
    """无可用节点时任务仍创建成功，worker_id 为空，排队等待 worker 上线。"""
    monkeypatch.setattr("apps.tasks.views.select_node", lambda strategy="least_loaded": None)
    monkeypatch.setattr(
        "apps.tasks.views.execute_task.apply_async", lambda args, queue=None, **kw: None
    )
    resp = auth_client.post(TASKS, {"name": "t", "code": "print(1)"}, format="json")
    assert resp.status_code == 201
    assert resp.data["worker_id"] == ""


def test_cancel_running_idempotent(auth_client, user):
    """重复取消同一个 RUNNING 任务，第二次返回 202 且 cancel_requested_at 保持不变。"""
    task = Task.objects.create(name="t", owner=user, code="print(1)", status=Task.Status.RUNNING)
    resp1 = auth_client.post(f"{TASKS}{task.id}/cancel/")
    assert resp1.status_code == 202
    task.refresh_from_db()
    first_marker = task.cancel_requested_at

    resp2 = auth_client.post(f"{TASKS}{task.id}/cancel/")
    assert resp2.status_code == 202
    task.refresh_from_db()
    assert task.cancel_requested_at == first_marker


def test_throttle_user(auth_client, monkeypatch):
    """已认证用户超过限流后返回 429。"""
    from rest_framework.throttling import UserRateThrottle

    original = UserRateThrottle.allow_request

    def throttled(self, request, view):
        throttled.calls += 1
        if throttled.calls >= 2:
            self.history = [0]
            self.wait = lambda: 60
            return False
        return original(self, request, view)

    throttled.calls = 0

    monkeypatch.setattr(UserRateThrottle, "allow_request", throttled)

    resp1 = auth_client.get(TASKS)
    assert resp1.status_code == 200
    resp2 = auth_client.get(TASKS)
    assert resp2.status_code == 429
