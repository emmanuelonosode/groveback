from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Visitor, VisitorSession, PageVisit, TelemetryEvent


@admin.register(Visitor)
class VisitorAdmin(ModelAdmin):
    list_display = ["fingerprint_id", "user", "first_seen", "last_seen"]
    search_fields = ["fingerprint_id", "user__email", "user__first_name", "user__last_name"]
    ordering = ["-last_seen"]
    readonly_fields = [f.name for f in Visitor._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(VisitorSession)
class VisitorSessionAdmin(ModelAdmin):
    list_display  = ["visitor", "start_time", "city", "device_type", "browser", "total_dwell_time"]
    list_filter   = ["device_type", "country_code", "utm_source"]
    search_fields = ["city", "region", "ip_address", "referral_code", "utm_campaign", "landing_page", "session_id"]
    ordering      = ["-created_at"]
    readonly_fields = [f.name for f in VisitorSession._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PageVisit)
class PageVisitAdmin(ModelAdmin):
    list_display = ["session", "path", "entry_time", "max_scroll_depth", "idle_time"]
    search_fields = ["path", "session__session_id"]
    ordering = ["-entry_time"]
    list_filter = ["path"]
    readonly_fields = [f.name for f in PageVisit._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TelemetryEvent)
class TelemetryEventAdmin(ModelAdmin):
    list_display = ["event_type", "session", "created_at"]
    search_fields = ["event_type", "session__session_id"]
    list_filter = ["event_type"]
    ordering = ["-created_at"]
    readonly_fields = [f.name for f in TelemetryEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
