from rest_framework import permissions


class IsAdmin(permissions.BasePermission):
    """仅管理员可访问"""

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_admin()


class IsAdminOrSelf(permissions.BasePermission):
    """管理员可访问，普通用户只能访问自己的资源"""

    def has_object_permission(self, request, view, obj):
        if request.user.is_admin():
            return True
        return obj == request.user


class IsOwnerOrAdmin(permissions.BasePermission):
    """对象级权限：仅对象所有者或管理员可操作"""

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.user.is_admin():
            return True
        return obj.owner == request.user
