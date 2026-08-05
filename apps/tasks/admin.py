from django.contrib import admin

from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["name", "task_type", "status", "priority", "owner", "worker_id", "created_at"]
    list_filter = ["status", "priority", "task_type", "created_at"]
    search_fields = ["name", "code"]
    readonly_fields = ["id", "created_at", "updated_at", "duration"]
