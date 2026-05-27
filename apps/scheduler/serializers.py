from rest_framework import serializers
from .models import Viewing


class ViewingSerializer(serializers.ModelSerializer):
    lead_name = serializers.CharField(source="lead.full_name", read_only=True)
    property_title = serializers.CharField(source="property.title", read_only=True)
    property_address = serializers.CharField(source="property.address", read_only=True)
    agent_name = serializers.CharField(source="agent.full_name", read_only=True)

    class Meta:
        model = Viewing
        fields = [
            "id", "lead", "lead_name",
            "property", "property_title", "property_address",
            "agent", "agent_name",
            "scheduled_at", "status", "notes", "reminder_sent",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "reminder_sent", "created_at", "updated_at"]
