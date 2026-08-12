from rest_framework import permissions

# ——————————————————————————————————————————————————————
# DRF 权限类：决定"谁能访问什么"
# 逻辑分两层：
#   has_permission      → 能不能进（登录校验、角色校验）
#   has_object_permission → 能不能操作"这一个"对象（是不是你的？你是不是管理员？）
# ——————————————————————————————————————————————————————


class IsAdmin(permissions.BasePermission):
    """仅管理员可访问。
    用法：配在 ViewSet 的 permission_classes 里，所有人里只有 role=admin 的过。
    实际场景：节点管理接口（/api/v1/nodes/）只有管理员看到。
    """

    def has_permission(self, request, view):
        # 三步校验：有用户对象、已登录、且 role=ADMIN
        return request.user and request.user.is_authenticated and request.user.is_admin()


class IsAdminOrSelf(permissions.BasePermission):
    """管理员可访问；普通用户只能访问"自己"的 User 对象。
    用法：用户列表 / 用户详情 —— 管理员能看所有人，你只能看/改自己的资料。
    """

    def has_object_permission(self, request, view, obj):
        # obj 在这里是 User 实例
        if request.user.is_admin():
            return True  # 管理员：随便看
        return obj == request.user  # 不是自己的 → 拒绝（返回 404，不暴露"有人叫这个"）


class IsOwnerOrAdmin(permissions.BasePermission):
    """对象级权限：任务/Task 的创建者或管理员可操作。
    用法：TaskViewSet —— 你只能增删改查你自己提交的任务，admin 能看到全部。
    注意 has_permission 也必须返回登录校验，否则匿名用户会打到 500 而不是 401。
    """

    def has_permission(self, request, view):
        # 这一行必须写！不写的话匿名用户直接穿透，后续代码读 request.user 抛异常
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # obj 在这里是 Task 实例，obj.owner 是创建它的用户
        if request.user.is_admin():
            return True  # 管理员：可以操作任意任务
        return obj.owner == request.user  # 不是你的任务 → 拒绝
