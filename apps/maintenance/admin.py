from django.contrib import admin
from .models import MaintenanceRequest


@admin.register(MaintenanceRequest)
class MaintenanceRequestAdmin(admin.ModelAdmin):
    list_display  = ["title", "client", "category", "priority", "status", "created_at"]
    list_filter   = ["status", "category", "priority"]
    search_fields = ["title", "description", "client__lead__first_name", "client__lead__last_name"]
    readonly_fields = ["created_at", "updated_at", "resolved_at"]
    ordering = ["-created_at"]
