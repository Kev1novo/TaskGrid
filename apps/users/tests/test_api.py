import pytest

pytestmark = pytest.mark.django_db

REGISTER = "/api/v1/auth/register/"
LOGIN = "/api/v1/auth/login/"
REFRESH = "/api/v1/auth/refresh/"
PROFILE = "/api/v1/auth/profile/"
USERS = "/api/v1/auth/users/"


def test_register_success(api_client):
    resp = api_client.post(
        REGISTER,
        {"username": "newuser", "email": "n@e.com", "password": "password123"},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["username"] == "newuser"


def test_register_short_password(api_client):
    resp = api_client.post(REGISTER, {"username": "u1", "password": "short"}, format="json")
    assert resp.status_code == 400


def test_register_duplicate_username(api_client, user):
    resp = api_client.post(
        REGISTER,
        {"username": user.username, "password": "password123"},
        format="json",
    )
    assert resp.status_code == 400


def test_login_success(api_client, user):
    resp = api_client.post(
        LOGIN,
        {"username": user.username, "password": "alicepass123"},
        format="json",
    )
    assert resp.status_code == 200
    assert "access" in resp.data
    assert "refresh" in resp.data
    assert resp.data["user"]["username"] == user.username


def test_login_wrong_password(api_client, user):
    resp = api_client.post(
        LOGIN,
        {"username": user.username, "password": "wrongpass"},
        format="json",
    )
    assert resp.status_code == 401


def test_refresh(auth_client, user):
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = str(RefreshToken.for_user(user))
    resp = auth_client.post(REFRESH, {"refresh": refresh}, format="json")
    assert resp.status_code == 200
    assert "access" in resp.data


def test_profile_requires_auth(api_client):
    assert api_client.get(PROFILE).status_code == 401


def test_profile_returns_current_user(auth_client, user):
    resp = auth_client.get(PROFILE)
    assert resp.status_code == 200
    assert resp.data["username"] == user.username


def test_user_list_requires_admin(auth_client):
    assert auth_client.get(USERS).status_code == 403


def test_user_list_admin_ok(admin_client, user):
    resp = admin_client.get(USERS)
    assert resp.status_code == 200
