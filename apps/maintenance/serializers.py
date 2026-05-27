from rest_framework import serializers
from .models import MaintenanceRequest


class MaintenanceRequestListSerializer(serializers.ModelSerializer):
    class Meta:
        model  = MaintenanceRequest
        fields = ["id", "title", "category", "priority", "status", "created_at", "updated_at"]


class MaintenanceRequestDetailSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model  = MaintenanceRequest
        fields = [
            "id", "title", "description", "category", "priority", "status",
            "photo_url", "preferred_access_time", "resolved_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "resolved_at", "created_at", "updated_at"]

    def get_photo_url(self, obj):
        try:
            return obj.photo.url if obj.photo else None
        except Exception:
            return None
