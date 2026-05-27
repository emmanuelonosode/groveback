from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from .models import JobApplication, ApplicationStatus


@admin.register(JobApplication)
class JobApplicationAdmin(ModelAdmin):
    list_display = [
        "full_name", "role_title", "status_badge",
        "phone", "email", "applied_at",
    ]
    list_filter  = ["status", "role_id", "applied_at"]
    search_fields = ["full_name", "email", "phone", "role_title"]
    ordering = ["-applied_at"]
    readonly_fields = ["applied_at", "reviewed_by"]
    actions = [
        "mark_under_review",
        "mark_interview_scheduled",
        "mark_hired",
        "mark_rejected",
        "send_rejection_email_action",
    ]

    fieldsets = (
        ("Applicant", {
            "fields": ("full_name", "email", "phone", "linkedin_url"),
        }),
        ("Role & Application", {
            "fields": ("role_id", "role_title", "motivation",
                       "extra_field_label", "extra_field_value"),
        }),
        ("Status & Notes", {
            "fields": ("status", "interview_date", "reviewed_by", "staff_notes"),
        }),
        ("Timestamps", {
            "fields": ("applied_at",),
            "classes": ("collapse",),
        }),
    )

    def status_badge(self, obj):
        colors = {
            ApplicationStatus.SUBMITTED:           "#2563eb",  # blue
            ApplicationStatus.UNDER_REVIEW:        "#d97706",  # amber
            ApplicationStatus.INTERVIEW_SCHEDULED: "#7c3aed",  # purple
            ApplicationStatus.HIRED:               "#16a34a",  # green
            ApplicationStatus.REJECTED:            "#dc2626",  # red
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;border-radius:9999px;font-size:11px;font-weight:600">{}</span>',
            color, obj.get_status_display(),
        )
    status_badge.short_description = "Status"

    @admin.action(description="Mark selected as Under Review")
    def mark_under_review(self, request, queryset):
        updated = queryset.update(status=ApplicationStatus.UNDER_REVIEW)
        self.message_user(request, f"{updated} application(s) marked as Under Review.")

    @admin.action(description="Mark selected as Interview Scheduled")
    def mark_interview_scheduled(self, request, queryset):
        updated = queryset.update(status=ApplicationStatus.INTERVIEW_SCHEDULED)
        self.message_user(request, f"{updated} application(s) marked as Interview Scheduled.")

    @admin.action(description="Mark selected as Hired")
    def mark_hired(self, request, queryset):
        updated = queryset.update(status=ApplicationStatus.HIRED)
        self.message_user(request, f"{updated} application(s) marked as Hired.")

    @admin.action(description="Mark selected as Rejected")
    def mark_rejected(self, request, queryset):
        updated = queryset.update(status=ApplicationStatus.REJECTED)
        self.message_user(request, f"{updated} application(s) marked as Rejected.")

    @admin.action(description="Send rejection email to selected applicants")
    def send_rejection_email_action(self, request, queryset):
        try:
            from apps.notifications.tasks import send_job_rejection_email
            count = 0
            for app in queryset:
                send_job_rejection_email(app.pk)
                count += 1
            self.message_user(request, f"Rejection email queued for {count} applicant(s).")
        except Exception as e:
            self.message_user(request, f"Error queuing emails: {e}", level="error")
