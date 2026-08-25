"""pytest 全局 fixtures。"""

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    from apps.users.models import User

    return User.objects.create_user(username="alice", password="alicepass123")


@pytest.fixture
def admin(db):
    from apps.users.models import User

    u = User.objects.create_user(username="admin", password="adminpass123")
    u.role = User.Role.ADMIN
    u.save(update_fields=["role"])
    return u


@pytest.fixture
def auth_client(api_client, user):
    """已挂 alice JWT 的 API client。"""
    token = str(RefreshToken.for_user(user).access_token)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client


@pytest.fixture
def admin_client(api_client, admin):
    """已挂 admin JWT 的 API client。"""
    token = str(RefreshToken.for_user(admin).access_token)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client


@pytest.fixture
def fake_sandbox(monkeypatch):
    """把 execute_task 里的 SandboxExecutor 换成可控 fake，测试里改 fake.result。"""
    from apps.sandbox.executor import SandboxResult

    class FakeSandbox:
        def __init__(self):
            self.result = SandboxResult(exit_code=0)

        def execute(self, code, timeout=None, cancel_check=None):
            return self.result

    fake = FakeSandbox()
    monkeypatch.setattr("apps.tasks.tasks.SandboxExecutor", lambda: fake)
    return fake


@pytest.fixture
def fake_es(monkeypatch):
    """mock ES client，避免真实连接。"""
    from unittest.mock import MagicMock

    client = MagicMock()
    monkeypatch.setattr("apps.logs.services.get_client", lambda: client)
    return client
