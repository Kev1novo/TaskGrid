from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIRequestFactory

from apps.users.models import User
from apps.users.permissions import IsAdmin, IsAdminOrSelf, IsOwnerOrAdmin

factory = APIRequestFactory()


def _request(user=None):
    request = factory.get("/")
    request.user = user or AnonymousUser()
    return request


# --- IsAdmin ---


def test_is_admin_anonymous_denied():
    assert IsAdmin().has_permission(_request(), None) is False


def test_is_admin_normal_user_denied(user):
    assert IsAdmin().has_permission(_request(user), None) is False


def test_is_admin_admin_allowed(admin):
    assert IsAdmin().has_permission(_request(admin), None) is True


# --- IsAdminOrSelf ---


def test_is_admin_or_self_admin_allowed(admin):
    other = User.objects.create_user(username="bob", password="bobpass123")
    assert IsAdminOrSelf().has_object_permission(_request(admin), None, other) is True


def test_is_admin_or_self_owner_allowed(user):
    assert IsAdminOrSelf().has_object_permission(_request(user), None, user) is True


def test_is_admin_or_self_other_denied(user):
    other = User.objects.create_user(username="bob", password="bobpass123")
    assert IsAdminOrSelf().has_object_permission(_request(user), None, other) is False


# --- IsOwnerOrAdmin ---


def test_is_owner_or_admin_anonymous_denied():
    assert IsOwnerOrAdmin().has_permission(_request(), None) is False


def test_is_owner_or_admin_authenticated_allowed(user):
    assert IsOwnerOrAdmin().has_permission(_request(user), None) is True


def test_is_owner_or_admin_owner_allowed(user):
    from apps.tasks.models import Task

    task = Task(owner=user)
    assert IsOwnerOrAdmin().has_object_permission(_request(user), None, task) is True


def test_is_owner_or_admin_other_denied(user):
    from apps.tasks.models import Task

    other = User.objects.create_user(username="bob", password="bobpass123")
    task = Task(owner=other)
    assert IsOwnerOrAdmin().has_object_permission(_request(user), None, task) is False


def test_is_owner_or_admin_admin_allowed(admin):
    from apps.tasks.models import Task

    other = User.objects.create_user(username="bob", password="bobpass123")
    task = Task(owner=other)
    assert IsOwnerOrAdmin().has_object_permission(_request(admin), None, task) is True
