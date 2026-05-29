from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import VisitorSession


@admin.register(VisitorSession)
class VisitorSessionAdmin(ModelAdmin):
    list_display  = ["created_at", "city", "country_code", "device_type", "browser", "os", "utm_source", "referral_code", "landing_page"]
    list_filter   = ["device_type", "country_code", "utm_source", "utm_medium"]
    search_fields = ["city", "region", "ip_address", "referral_code", "utm_campaign", "landing_page"]
    ordering      = ["-created_at"]
    readonly_fields = [f.name for f in VisitorSession._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
