from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import ClientDocument


@admin.register(ClientDocument)
class ClientDocumentAdmin(ModelAdmin):
    list_display = ["name", "client", "document_type", "is_signed", "uploaded_by", "created_at", "expires_at"]
    list_filter = ["document_type", "is_signed"]
    search_fields = ["name", "client__lead__full_name", "uploaded_by__email"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at"]

    fieldsets = (
        ("Document", {
            "fields": ("client", "name", "file", "document_type"),
        }),
        ("Status", {
            "fields": ("is_signed", "uploaded_by", "expires_at"),
        }),
        ("Timestamps", {
            "fields": ("created_at",),
        }),
    )
