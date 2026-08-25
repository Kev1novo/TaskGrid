from django_filters import rest_framework as filters
from rest_framework import serializers

from .models import Task


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = [
            "id",
            "name",
            "task_type",
            "code",
            "params",
            "status",
            "priority",
            "owner",
            "worker_id",
            "result",
            "error_message",
            "cancel_requested_at",
            "duration",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "owner",
            "worker_id",
            "result",
            "error_message",
            "cancel_requested_at",
            "duration",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ]


class TaskCreateSerializer(serializers.ModelSerializer):
    params = serializers.JSONField(default=dict)

    class Meta:
        model = Task
        fields = ["name", "task_type", "code", "params", "priority"]

    def validate_params(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("params 必须是 JSON 对象")
        return value


class TaskStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Task.Status.choices)

    def update(self, instance, validated_data):
        instance.transit(validated_data["status"])
        instance.save()
        return instance


class TaskFilter(filters.FilterSet):
    status = filters.ChoiceFilter(choices=Task.Status.choices)
    priority = filters.ChoiceFilter(choices=Task.Priority.choices)
    task_type = filters.CharFilter(lookup_expr="icontains")
    created_at_after = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at_before = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Task
        fields = ["status", "priority", "task_type"]
