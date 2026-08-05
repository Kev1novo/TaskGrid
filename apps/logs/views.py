from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import search_logs


class LogSearchView(APIView):
    """任务日志检索。

    查询参数：
      q        全文关键词（output/error/task_name）
      task_id  按任务过滤
      status   按状态过滤（pending/running/success/failed/timeout）
    权限：普通用户只能搜自己任务的日志，管理员可搜全部。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = request.query_params.get("q")
        task_id = request.query_params.get("task_id")
        # 注意：局部变量不要命名为 status，会遮蔽 rest_framework 的 status 模块
        status_filter = request.query_params.get("status")
        owner_id = None if request.user.is_admin() else request.user.id

        try:
            hits = search_logs(
                q=q,
                task_id=task_id,
                owner_id=owner_id,
                status=status_filter,
            )
        except Exception as exc:
            return Response(
                {"detail": f"日志服务暂不可用: {exc}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({"count": len(hits), "results": hits})
