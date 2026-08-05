from rest_framework import serializers

from .models import Node


class NodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Node
        fields = [
            "id",
            "name",
            "hostname",
            "ip",
            "status",
            "cpu_percent",
            "mem_percent",
            "last_heartbeat",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
