from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.users.permissions import IsAdmin

from .models import Node
from .serializers import NodeSerializer


class NodeViewSet(viewsets.ReadOnlyModelViewSet):
    """节点管理（仅管理员，只读——节点由 worker 心跳自动注册）。"""

    queryset = Node.objects.all()
    serializer_class = NodeSerializer
    permission_classes = [IsAdmin]

    @action(detail=True, methods=["post"], url_path="offline")
    def mark_offline(self, request, pk=None):
        """手动下线一个节点（演示故障转移用）"""
        node = self.get_object()
        node.mark_offline()
        return Response(NodeSerializer(node).data)
