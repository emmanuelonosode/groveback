from datetime import datetime, time

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from .models import Viewing, ViewingStatus, TourRequest, TourRequestStatus


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
    readonly_fields = ["reminder_sent", "confirmation_sent", "created_at", "updated_at"]
    actions = ["mark_completed", "mark_cancelled", "mark_confirmed"]

    fieldsets = (
        ("Details", {
            "fields": ("lead", "property", "agent", "scheduled_at"),
        }),
        ("Confirmation email", {
            "fields": ("lease_term", "access_code"),
            "description": "These appear in the self-tour confirmation email sent to the "
                           "tenant. When/Where/Lease price come from the scheduled time and "
                           "the selected property.",
        }),
        ("Status", {
            "fields": ("status", "notes", "reminder_sent", "confirmation_sent"),
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
        from apps.notifications.tasks import send_tour_confirmation_email
        updated = queryset.update(status=ViewingStatus.CONFIRMED)
        sent = 0
        # Send the self-tour confirmation for any not yet emailed.
        for viewing in queryset.filter(confirmation_sent=False):
            try:
                send_tour_confirmation_email(viewing.pk)
                sent += 1
            except Exception:
                pass  # Never block the admin action if email fails.
        self.message_user(
            request,
            f"{updated} viewings confirmed. {sent} confirmation email(s) sent.",
        )

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


def _parse_tour_datetime(tour) -> datetime:
    """Best-effort combine preferred_date + preferred_time into an aware datetime."""
    d = tour.preferred_date or timezone.localdate()
    t = time(10, 0)  # sensible default if the time can't be parsed
    raw = (tour.preferred_time or "").strip()
    for fmt in ("%I:%M %p", "%I %p", "%H:%M", "%I:%M%p"):
        try:
            t = datetime.strptime(raw, fmt).time()
            break
        except ValueError:
            continue
    naive = datetime.combine(d, t)
    return timezone.make_aware(naive, timezone.get_current_timezone())


@admin.register(TourRequest)
class TourRequestAdmin(ModelAdmin):
    list_display = ["full_name", "property", "preferred_date", "preferred_time", "status_badge", "id_uploaded", "created_at"]
    list_filter = ["status", "created_at", "tour_type"]
    search_fields = ["full_name", "email", "phone", "property__title"]
    ordering = ["-created_at"]
    readonly_fields = [
        "public_id", "lead", "property", "full_name", "email", "phone",
        "preferred_date", "preferred_time", "tour_type", "notes", "id_preview",
        "status", "reviewed_by", "reviewed_at", "viewing", "created_at", "updated_at",
    ]
    actions = ["approve_and_book", "reject_requests"]
    fieldsets = (
        ("Request", {"fields": ("full_name", "phone", "email", "property", "preferred_date", "preferred_time", "tour_type", "notes")}),
        ("Identity verification", {
            "fields": ("id_preview", "status"),
            "description": "Sensitive: government ID photos. Approve only after confirming the ID matches the applicant. "
                           "Approving books the self-tour and emails the visitor.",
        }),
        ("Outcome", {"fields": ("viewing", "reviewed_by", "reviewed_at", "rejection_reason"), "classes": ("collapse",)}),
        ("Meta", {"fields": ("lead", "public_id", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def has_add_permission(self, request):
        return False

    def status_badge(self, obj):
        colors = {
            TourRequestStatus.AWAITING_ID: "#6b7280",
            TourRequestStatus.PENDING_REVIEW: "#d97706",
            TourRequestStatus.APPROVED: "#16a34a",
            TourRequestStatus.REJECTED: "#dc2626",
        }
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:9999px;font-size:11px">{}</span>',
            colors.get(obj.status, "#6b7280"), obj.get_status_display(),
        )
    status_badge.short_description = "Status"

    def id_uploaded(self, obj):
        return bool(obj.id_front)
    id_uploaded.boolean = True
    id_uploaded.short_description = "ID"

    def id_preview(self, obj):
        if not obj.id_front:
            return format_html('<span style="color:#999">No ID uploaded yet.</span>')
        imgs = format_html(
            '<a href="{}" target="_blank"><img src="{}" style="max-height:220px;border:1px solid #ddd;border-radius:6px;margin-right:10px"/></a>',
            obj.id_front, obj.id_front,
        )
        if obj.id_back:
            imgs += format_html(
                '<a href="{}" target="_blank"><img src="{}" style="max-height:220px;border:1px solid #ddd;border-radius:6px"/></a>',
                obj.id_back, obj.id_back,
            )
        return imgs
    id_preview.short_description = "ID document(s)"

    @admin.action(description="Approve identity & book self-tour")
    def approve_and_book(self, request, queryset):
        booked, skipped = 0, 0
        for tour in queryset:
            if tour.status == TourRequestStatus.APPROVED and tour.viewing_id:
                skipped += 1
                continue
            if not tour.lead_id:
                self.message_user(request, f"{tour.full_name}: no linked lead — can't book.", level="warning")
                skipped += 1
                continue
            agent = tour.property.agent
            viewing = Viewing.objects.create(
                lead=tour.lead,
                property=tour.property,
                agent=agent,
                scheduled_at=_parse_tour_datetime(tour),
                status=ViewingStatus.CONFIRMED,
                notes=f"Booked from verified tour request {tour.public_id}.",
            )  # post_save signal sends the self-tour confirmation email
            tour.status = TourRequestStatus.APPROVED
            tour.viewing = viewing
            tour.reviewed_by = request.user
            tour.reviewed_at = timezone.now()
            tour.save(update_fields=["status", "viewing", "reviewed_by", "reviewed_at", "updated_at"])
            booked += 1
        self.message_user(request, f"{booked} self-tour(s) booked and confirmation emailed. {skipped} skipped.")

    @admin.action(description="Reject request")
    def reject_requests(self, request, queryset):
        updated = queryset.exclude(status=TourRequestStatus.APPROVED).update(
            status=TourRequestStatus.REJECTED, reviewed_by=request.user, reviewed_at=timezone.now(),
        )
        self.message_user(request, f"{updated} request(s) rejected.")
