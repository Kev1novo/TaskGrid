from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.nodes.services import select_node
from apps.users.permissions import IsOwnerOrAdmin

from .models import Task
from .serializers import (
    TaskCreateSerializer,
    TaskFilter,
    TaskSerializer,
    TaskStatusUpdateSerializer,
)
from .tasks import execute_task


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    permission_classes = [IsOwnerOrAdmin]
    filterset_class = TaskFilter
    ordering_fields = ["priority", "created_at", "status"]
    search_fields = ["name", "task_type"]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin():
            return Task.objects.all()
        return Task.objects.filter(owner=user)

    def get_serializer_class(self):
        if self.action == "create":
            return TaskCreateSerializer
        return TaskSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # 按调度策略选择节点并记录到 worker_id
        node = select_node()
        task = serializer.save(
            owner=request.user,
            status=Task.Status.PENDING,
            worker_id=node.name if node else "",
        )
        execute_task.delay(task.id)
        headers = self.get_success_headers(serializer.data)
        # 返回完整对象（含 id/status/result），而不是只返回创建字段
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED, headers=headers)

    def get_object(self):
        obj = super().get_object()
        self.check_object_permissions(self.request, obj)
        return obj

    @action(detail=True, methods=["post"], url_path="status")
    def update_status(self, request, pk=None):
        """更新任务状态（供调度器和节点调用）"""
        task = self.get_object()
        serializer = TaskStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            task.transit(serializer.validated_data["status"])
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if task.status == Task.Status.RUNNING and not task.started_at:
            task.started_at = timezone.now()
        if task.status in [Task.Status.SUCCESS, Task.Status.FAILED, Task.Status.TIMEOUT]:
            task.finished_at = timezone.now()

        task.save()
        return Response(TaskSerializer(task).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """取消待执行的任务"""
        task = self.get_object()
        try:
            task.transit(Task.Status.CANCELLED)
            task.save()
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TaskSerializer(task).data)
