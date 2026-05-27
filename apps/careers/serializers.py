from rest_framework import serializers
from .models import JobApplication


class JobApplicationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobApplication
        fields = [
            "role_id", "role_title",
            "full_name", "email", "phone", "linkedin_url",
            "motivation",
            "extra_field_label", "extra_field_value",
        ]


class JobApplicationAdminSerializer(serializers.ModelSerializer):
    reviewed_by_name = serializers.SerializerMethodField()

    def get_reviewed_by_name(self, obj):
        if obj.reviewed_by:
            return obj.reviewed_by.get_full_name() or obj.reviewed_by.email
        return None

    class Meta:
        model = JobApplication
        fields = "__all__"
        read_only_fields = ["applied_at"]
