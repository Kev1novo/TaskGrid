import pytest
from rest_framework_simplejwt.tokens import RefreshToken

pytestmark = pytest.mark.django_db

SEARCH = "/api/v1/logs/search/"


def test_search_requires_auth(api_client):
    assert api_client.get(SEARCH).status_code == 401


def test_normal_user_gets_owner_filter(api_client, user, monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "apps.logs.views.search_logs",
        lambda **kwargs: captured.update(kwargs) or [],
    )
    token = str(RefreshToken.for_user(user).access_token)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    resp = api_client.get(SEARCH, {"q": "hello", "status": "success"})
    assert resp.status_code == 200
    assert captured["owner_id"] == user.id
    assert captured["q"] == "hello"
    assert captured["status"] == "success"


def test_admin_gets_no_owner_filter(api_client, admin, monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "apps.logs.views.search_logs",
        lambda **kwargs: captured.update(kwargs) or [],
    )
    token = str(RefreshToken.for_user(admin).access_token)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    resp = api_client.get(SEARCH, {"q": "hello"})
    assert resp.status_code == 200
    assert captured["owner_id"] is None


def test_es_error_returns_503(api_client, user, monkeypatch):
    def boom(**kwargs):
        raise Exception("es down")

    monkeypatch.setattr("apps.logs.views.search_logs", boom)
    token = str(RefreshToken.for_user(user).access_token)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    resp = api_client.get(SEARCH)
    assert resp.status_code == 503
