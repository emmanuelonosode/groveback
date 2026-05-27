from rest_framework import serializers
from .models import ClientDocument


class ClientDocumentSerializer(serializers.ModelSerializer):
    file_url         = serializers.SerializerMethodField()
    uploaded_by_name = serializers.CharField(source="uploaded_by.full_name", read_only=True, default="")

    class Meta:
        model  = ClientDocument
        fields = [
            "id", "name", "document_type", "is_signed",
            "file_url", "uploaded_by_name", "created_at", "expires_at",
        ]

    def get_file_url(self, obj):
        try:
            return obj.file.url
        except Exception:
            return None
