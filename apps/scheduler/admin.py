from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from .models import Viewing, ViewingStatus


@admin.register(Viewing)
class ViewingAdmin(ModelAdmin):
    list_display = [
        "lead", "property", "agent",
        "scheduled_at", "status_badge", "reminder_sent",
    ]
    list_filter = ["status", "agent", "reminder_sent"]
    search_fields = [
        "lead__full_name", "property__title",
        "agent__first_name", "agent__last_name",
    ]
    ordering = ["scheduled_at"]
    date_hierarchy = "scheduled_at"
    readonly_fields = ["reminder_sent", "created_at", "updated_at"]
    actions = ["mark_completed", "mark_cancelled", "mark_confirmed"]

    fieldsets = (
        ("Details", {
            "fields": ("lead", "property", "agent", "scheduled_at"),
        }),
        ("Status", {
            "fields": ("status", "notes", "reminder_sent"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def status_badge(self, obj):
        colors = {
            ViewingStatus.SCHEDULED: "#2563eb",
            ViewingStatus.CONFIRMED: "#16a34a",
            ViewingStatus.COMPLETED: "#0891b2",
            ViewingStatus.CANCELLED: "#dc2626",
            ViewingStatus.NO_SHOW: "#6b7280",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:9999px;font-size:11px">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = "Status"

    @admin.action(description="Mark as Confirmed")
    def mark_confirmed(self, request, queryset):
        updated = queryset.update(status=ViewingStatus.CONFIRMED)
        self.message_user(request, f"{updated} viewings confirmed.")

    @admin.action(description="Mark as Completed")
    def mark_completed(self, request, queryset):
        from apps.notifications.tasks import send_post_viewing_followup
        count = 0
        for viewing in queryset:
            viewing.status = ViewingStatus.COMPLETED
            viewing.save(update_fields=["status"])
            # Schedule follow-up 2 hours after marking complete
            try:
                send_post_viewing_followup.apply_async(args=[viewing.pk], countdown=7200)
            except Exception:
                pass  # Never block admin action if Celery/Redis is down
            count += 1
        self.message_user(request, f"{count} viewings marked completed. Follow-up emails scheduled for 2 hours.")

    @admin.action(description="Mark as Cancelled")
    def mark_cancelled(self, request, queryset):
        updated = queryset.update(status=ViewingStatus.CANCELLED)
        self.message_user(request, f"{updated} viewings cancelled.")
