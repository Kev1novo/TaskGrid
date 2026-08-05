from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (("扩展信息", {"fields": ("role",)}),)
    list_display = ("username", "email", "role", "is_active", "created_at")
    list_filter = ("role", "is_active", "created_at")
