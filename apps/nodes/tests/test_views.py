import pytest
from django.urls import reverse

from apps.nodes.models import Node

pytestmark = pytest.mark.django_db

NODES_URL = reverse("node-list")


class TestNodeViewSetAsAdmin:
    """管理员可查看节点并执行管理操作。"""

    def test_list_nodes(self, admin_client):
        Node.objects.create(name="celery@w1", status=Node.Status.ONLINE)
        Node.objects.create(name="celery@w2", status=Node.Status.OFFLINE)
        resp = admin_client.get(NODES_URL)
        assert resp.status_code == 200
        assert len(resp.data["results"]) == 2

    def test_retrieve_node(self, admin_client):
        node = Node.objects.create(name="celery@w1")
        url = reverse("node-detail", args=[node.pk])
        resp = admin_client.get(url)
        assert resp.status_code == 200
        assert resp.data["name"] == "celery@w1"

    def test_mark_offline_action(self, admin_client):
        node = Node.objects.create(name="celery@w1", status=Node.Status.ONLINE)
        url = reverse("node-mark-offline", args=[node.pk])
        resp = admin_client.post(url)
        assert resp.status_code == 200
        node.refresh_from_db()
        assert node.status == Node.Status.OFFLINE

    def test_create_not_allowed(self, admin_client):
        """节点由 worker 自动注册，API 不支持手动创建。"""
        resp = admin_client.post(NODES_URL, {"name": "manual"}, format="json")
        assert resp.status_code == 405  # Method Not Allowed

    def test_delete_not_allowed(self, admin_client):
        node = Node.objects.create(name="celery@w1")
        url = reverse("node-detail", args=[node.pk])
        resp = admin_client.delete(url)
        assert resp.status_code == 405


class TestNodeViewSetAsAnonymous:
    """匿名用户不能访问节点管理。"""

    def test_list_denied(self, api_client):
        resp = api_client.get(NODES_URL)
        assert resp.status_code == 401

    def test_create_denied(self, api_client):
        resp = api_client.post(NODES_URL, {"name": "x"}, format="json")
        assert resp.status_code == 401  # 认证检查在 HTTP method 检查之前


class TestNodeViewSetAsNormalUser:
    """普通用户不能访问节点管理。"""

    def test_list_denied(self, auth_client):
        resp = auth_client.get(NODES_URL)
        assert resp.status_code == 403

    def test_mark_offline_denied(self, auth_client):
        node = Node.objects.create(name="celery@w1", status=Node.Status.ONLINE)
        url = reverse("node-mark-offline", args=[node.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 403
