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

# ——————————————————————————————————————————————————————
# TaskViewSet：任务 API 的入口（CRUD + 状态变更 + 取消）
#
# 完整链路（提交一个任务的背后发生了什么）：
#   1. create() → select_node() 选一个空闲 worker
#   2. create() → execute_task.delay() 把任务推进 Redis 队列
#   3. Celery worker 从队列取走任务 → 起 Docker 容器隔离执行
#   4. 执行完 → transit() 更新状态 → 结果写入 ES
#
# 数据隔离：普通用户只看到自己提交的任务（get_queryset 兜底过滤）
# ——————————————————————————————————————————————————————


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    permission_classes = [IsOwnerOrAdmin]  # 不是自己的任务 → 404（不是 403，更安全）
    filterset_class = TaskFilter  # 支持 ?status=pending&priority=3 等筛选
    ordering_fields = ["priority", "created_at", "status"]
    search_fields = ["name", "task_type"]

    def get_queryset(self):
        """数据隔离兜底：普通用户只查自己的任务，管理员查全部。
        为什么在这里再过滤一遍（而不是全靠 permission_classes）？
          → DRF 的 list 先执行 get_queryset，再对每个对象调 has_object_permission。
          如果不过滤 queryset，普通用户 list 会拿到全部任务的 QuerySet，
          然后逐个调 has_object_permission 检查 —— 低效，且不安全的实现会泄露总数。
          直接在 SQL 层按 owner 过滤，一步到位。
        """
        user = self.request.user
        if user.is_admin():
            return Task.objects.all()
        return Task.objects.filter(owner=user)

    def get_serializer_class(self):
        """创建任务用精简版（TaskCreateSerializer），其他操作用完整版（TaskSerializer）。"""
        if self.action == "create":
            return TaskCreateSerializer
        return TaskSerializer

    def create(self, request, *args, **kwargs):
        """创建任务：选节点 → 写库 → 入队 Celery → 返回完整对象。
        之所以重写 create 而不是用默认的 CreateModelMixin：
          DRF 默认只返回创建 serializer 的数据（没有 id），
          我们返回完整序列化对象（含 id、status="pending"），方便前端立即拿到任务 ID 去轮询。
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 第一步：用调度策略选一个在线 worker 节点
        node = select_node()
        task = serializer.save(
            owner=request.user,
            status=Task.Status.PENDING,
            worker_id=node.name if node else "",  # 没在线节点也能创建，等 worker 上线了再被取走
        )

        # 第二步：把任务推进 Redis 队列，等待 Celery worker 消费
        execute_task.delay(task.id)

        # 第三步：返回完整对象（不是只返回创建字段）
        headers = self.get_success_headers(serializer.data)
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED, headers=headers)

    def get_object(self):
        """取单个对象后立即做权限检查（所以在访问别人的任务时会返回 404）。"""
        obj = super().get_object()
        self.check_object_permissions(self.request, obj)
        return obj

    @action(detail=True, methods=["post"], url_path="status")
    def update_status(self, request, pk=None):
        """手动更新任务状态（比如 worker 执行完回调改状态）。
        注意：状态变更必须走 transit()，非法跳转会返回 400。
        """
        task = self.get_object()
        serializer = TaskStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            task.transit(serializer.validated_data["status"])
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # 自动记录开始/结束时间
        if task.status == Task.Status.RUNNING and not task.started_at:
            task.started_at = timezone.now()
        if task.status in [Task.Status.SUCCESS, Task.Status.FAILED, Task.Status.TIMEOUT]:
            task.finished_at = timezone.now()

        task.save()
        return Response(TaskSerializer(task).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """取消任务——只能在 PENDING 时取消，已经开始跑的就拦不住啦。"""
        task = self.get_object()
        try:
            task.transit(Task.Status.CANCELLED)
            task.save()
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TaskSerializer(task).data)
