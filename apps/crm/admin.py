import logging

from django.contrib import admin
from django.db.models import Sum
from django.utils.html import format_html
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline
from .models import (
    Lead, LeadActivity, Client, LeadStatus, RentalApplication, ApplicationStatus,
    MoveInTimeline, Referrer, ReferralPayout, ReferralStatus,
)

logger = logging.getLogger(__name__)


class LeadActivityInline(TabularInline):
    model = LeadActivity
    extra = 1
    fields = ["activity_type", "agent", "note", "created_at"]
    readonly_fields = ["created_at"]


class RentalApplicationInline(TabularInline):
    model = RentalApplication
    extra = 0
    fields = ["full_name_display", "rental_property", "status", "move_in_date", "submitted_at", "pdf_link"]
    readonly_fields = ["full_name_display", "rental_property", "submitted_at", "pdf_link"]
    can_delete = False
    verbose_name = "Rental Application"
    verbose_name_plural = "Rental Applications"

    def full_name_display(self, obj):
        return obj.full_name
    full_name_display.short_description = "Applicant"

    def pdf_link(self, obj):
        if obj.application_pdf:
            return format_html('<a href="{}" target="_blank">Download PDF</a>', obj.application_pdf)
        return "—"
    pdf_link.short_description = "PDF"


@admin.register(Lead)
class LeadAdmin(ModelAdmin):
    list_display = [
        "full_name", "email", "phone",
        "interest_type", "budget_display", "preferred_location",
        "timeline_badge", "occupants_display", "pets_display",
        "property_interest", "source", "status_badge", "score_badge",
        "assigned_agent", "last_contacted_at", "created_at",
    ]
    list_display_links = ["full_name", "email"]
    list_filter = [
        "status", "source", "interest_type",
        "move_in_timeline", "has_pets", "preferred_contact",
        "assigned_agent", "drip_opted_out",
    ]
    search_fields = ["full_name", "email", "phone", "preferred_location", "message",
                     "property_interest__title", "utm_source", "utm_campaign", "referral_source"]
    ordering = ["-created_at"]
    inlines = [LeadActivityInline, RentalApplicationInline]
    actions = ["mark_contacted", "mark_qualified", "mark_lost", "send_acknowledgment_email"]

    fieldsets = (
        ("Contact", {
            "fields": ("full_name", "email", "phone", "preferred_contact"),
        }),
        ("Interest & Intent", {
            "fields": (
                "source", "interest_type", "move_in_timeline",
                "budget_min", "budget_max", "preferred_location",
                "property_interest", "agent_interest",
                "occupants_count", "has_pets",
                "services_requested", "message",
            ),
        }),
        ("Pipeline", {
            "fields": ("status", "assigned_agent", "last_contacted_at", "drip_opted_out"),
        }),
        ("Attribution", {
            "fields": ("detected_city", "referral_source", "referral_code", "utm_source", "utm_medium", "utm_campaign"),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
    readonly_fields = ["created_at", "updated_at"]

    def timeline_badge(self, obj):
        if not obj.move_in_timeline:
            return "—"
        colors = {
            MoveInTimeline.ASAP:          "#16a34a",
            MoveInTimeline.ONE_THREE:     "#0891b2",
            MoveInTimeline.THREE_SIX:     "#7c3aed",
            MoveInTimeline.SIX_PLUS:      "#6b7280",
            MoveInTimeline.JUST_BROWSING: "#9ca3af",
        }
        color = colors.get(obj.move_in_timeline, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:9999px;font-size:11px;white-space:nowrap">{}</span>',
            color, obj.get_move_in_timeline_display()
        )
    timeline_badge.short_description = "Timeline"

    def occupants_display(self, obj):
        if obj.occupants_count is None:
            return "—"
        return f"{obj.occupants_count} person{'s' if obj.occupants_count != 1 else ''}"
    occupants_display.short_description = "Occupants"

    def pets_display(self, obj):
        if obj.has_pets is None:
            return "—"
        return "🐾 Yes" if obj.has_pets else "No"
    pets_display.short_description = "Pets"

    def budget_display(self, obj):
        if obj.budget_min and obj.budget_max:
            return f"${int(obj.budget_min):,} – ${int(obj.budget_max):,}"
        if obj.budget_min:
            return f"${int(obj.budget_min):,}+"
        if obj.budget_max:
            return f"up to ${int(obj.budget_max):,}"
        return "—"
    budget_display.short_description = "Budget"

    def score_badge(self, obj):
        s = obj.lead_score
        color = "#16a34a" if s >= 70 else "#d97706" if s >= 40 else "#dc2626"
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600">{}/100</span>',
            color, s
        )
    score_badge.short_description = "Score"

    def status_badge(self, obj):
        colors = {
            LeadStatus.NEW: "#2563eb",
            LeadStatus.CONTACTED: "#7c3aed",
            LeadStatus.QUALIFIED: "#0891b2",
            LeadStatus.VIEWING: "#d97706",
            LeadStatus.NEGOTIATING: "#ea580c",
            LeadStatus.CONVERTED: "#16a34a",
            LeadStatus.LOST: "#dc2626",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:9999px;font-size:11px">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = "Status"

    @admin.action(description="Mark as Contacted")
    def mark_contacted(self, request, queryset):
        updated = queryset.update(status=LeadStatus.CONTACTED, last_contacted_at=timezone.now())
        self.message_user(request, f"{updated} leads marked as Contacted.")

    @admin.action(description="Mark as Qualified")
    def mark_qualified(self, request, queryset):
        updated = queryset.update(status=LeadStatus.QUALIFIED)
        self.message_user(request, f"{updated} leads marked as Qualified.")

    @admin.action(description="Mark as Lost")
    def mark_lost(self, request, queryset):
        updated = queryset.update(status=LeadStatus.LOST)
        self.message_user(request, f"{updated} leads marked as Lost.")

    @admin.action(description="Send Inquiry Acknowledgment Email")
    def send_acknowledgment_email(self, request, queryset):
        from django.contrib import messages
        from apps.notifications.tasks import send_lead_acknowledgment_email
        queued = 0
        failed = 0
        for lead in queryset:
            try:
                send_lead_acknowledgment_email(lead.pk)
                queued += 1
            except Exception as e:
                logger.error("Failed to queue acknowledgment email for lead %s: %s", lead.pk, e)
                failed += 1
        if queued:
            self.message_user(request, f"Acknowledgment email queued for {queued} lead(s).")
        if failed:
            self.message_user(
                request,
                f"{failed} email(s) could not be queued — check that Celery is running.",
                level=messages.ERROR,
            )


@admin.register(LeadActivity)
class LeadActivityAdmin(ModelAdmin):
    list_display = ["lead", "activity_type", "agent", "created_at"]
    list_filter = ["activity_type", "agent"]
    search_fields = ["lead__full_name", "note"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at"]

    fieldsets = (
        ("Activity", {
            "fields": ("lead", "agent", "activity_type"),
        }),
        ("Detail", {
            "fields": ("note",),
        }),
        ("Timestamps", {
            "fields": ("created_at",),
            "classes": ("collapse",),
        }),
    )


@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ["full_name", "email", "preferred_agent", "kyc_verified", "created_at"]
    list_filter = ["kyc_verified", "preferred_agent"]
    search_fields = ["lead__full_name", "lead__email"]
    readonly_fields = ["created_at"]

    fieldsets = (
        ("Client Info", {
            "fields": ("lead", "user", "preferred_agent", "kyc_verified"),
        }),
        ("Timestamps", {
            "fields": ("created_at",),
        }),
    )


@admin.register(RentalApplication)
class RentalApplicationAdmin(ModelAdmin):
    list_display    = ["full_name", "email", "rental_property", "status_badge", "ssn_masked", "recovery_email_sent", "submitted_at", "pdf_download"]
    list_filter     = ["status", "has_pets", "has_kids", "smokes", "drinks"]
    search_fields   = ["first_name", "last_name", "email", "cell_phone", "present_address"]
    ordering        = ["-submitted_at"]
    readonly_fields = ["submitted_at", "ip_address", "lead", "application_pdf", "pdf_download", "certification_text", "animals", "ssn_view"]
    actions         = ["mark_reviewed", "mark_approved", "mark_rejected", "regenerate_pdf",
                      "send_approval_email", "send_rejection_email", "send_move_in_email",
                      "send_recovery_email_action"]

    def get_queryset(self, request):
        self._request = request
        return super().get_queryset(request)

    def ssn_masked(self, obj):
        """List column — always masked."""
        return "●●●-●●-" + obj.ssn_last4 if obj.ssn_last4 else ("●●●-●●-●●●●" if obj.ssn_encrypted else "—")
    ssn_masked.short_description = "SSN"

    def ssn_view(self, obj):
        """Detail read-only field — decrypted for superadmins, masked otherwise."""
        if not obj.ssn_encrypted:
            return format_html('<span style="color:#aaa">Not provided</span>')
        request = getattr(self, "_request", None)
        if request and request.user.is_superuser:
            try:
                from apps.notifications.encryption import decrypt_ssn
                decrypted = decrypt_ssn(obj.ssn_encrypted)
                return format_html(
                    '<code style="background:#f4f4f4;padding:4px 12px;border-radius:3px;'
                    'font-size:13px;letter-spacing:1px">{}</code>', decrypted
                )
            except Exception:
                return format_html('<span style="color:#c62828">⚠ Decryption error</span>')
        return format_html(
            '<span style="color:#999;font-style:italic">●●●-●●-●●●● — Superadmin access only</span>'
        )
    ssn_view.short_description = "SSN (Full — Superadmin Only)"

    fieldsets = (
        ("Applicant", {
            "fields": (
                "first_name", "middle_name", "last_name",
                "email", "cell_phone", "home_phone",
                "marital_status", "preferred_contact", "phone_type",
            ),
        }),
        ("Emergency Contact", {
            "fields": (
                "emergency_contact_name", "emergency_contact_relationship",
                "emergency_contact_phone", "emergency_contact_phone_type",
            ),
            "classes": ("collapse",),
        }),
        ("Identity", {
            "fields": (
                "date_of_birth", "id_type", "ssn_view", "ssn_last4", "ein",
                "has_drivers_license", "drivers_license_number", "drivers_license_state",
            ),
            "classes": ("collapse",),
            "description": "Full SSN is AES-encrypted at rest. Superadmins see the decrypted value; all others see only the last 4 digits.",
        }),
        ("Income & Employment", {
            "fields": (
                "gross_monthly_income", "employer_name", "employer_phone",
                "job_title", "employment_start_date",
            ),
            "classes": ("collapse",),
        }),
        ("Current Address", {
            "fields": (
                "present_address", "city", "state", "zip_code",
                "how_long_at_address", "reason_for_leaving",
                "current_landlord_name", "current_landlord_phone",
            ),
        }),
        ("Rental Details", {
            "fields": ("rental_property", "move_in_date", "intended_stay_duration", "months_rent_upfront"),
        }),
        ("Household", {
            "fields": (
                "has_kids", "number_of_kids",
                "has_vehicles", "number_of_vehicles",
                "has_pets", "pet_description", "animals",
                "smokes", "drinks",
            ),
        }),
        ("Background & Status", {
            "fields": (
                "has_felony_eviction_bankruptcy", "is_active_military", "has_housing_assistance",
            ),
        }),
        ("Status & Documents", {
            "fields": ("status", "lead", "submitted_at", "ip_address", "certification_text", "pdf_download"),
        }),
        ("Recovery & Attribution", {
            "fields": ("recovery_email_sent", "utm_source", "utm_medium", "utm_campaign"),
            "classes": ("collapse",),
        }),
    )

    def status_badge(self, obj):
        colors = {
            ApplicationStatus.DRAFT:                "#9ca3af",
            ApplicationStatus.PENDING_PAYMENT:      "#f59e0b",
            ApplicationStatus.PENDING_VERIFICATION: "#2563eb",
            ApplicationStatus.SUBMITTED:            "#8b5cf6",
            ApplicationStatus.REVIEWED:             "#14b8a6",
            ApplicationStatus.APPROVED:             "#10b981",
            ApplicationStatus.REJECTED:             "#ef4444",
            ApplicationStatus.PAYMENT_FAILED:       "#ef4444",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:9999px;font-size:11px">{}</span>',
            color, obj.get_status_display(),
        )
    status_badge.short_description = "Status"

    def pdf_download(self, obj):
        if obj.application_pdf:
            return format_html(
                '<a href="{}" target="_blank" style="color:#1A56DB;font-weight:600">Download PDF</a>',
                obj.application_pdf,
            )
        return "PDF not yet generated"
    pdf_download.short_description = "Application PDF"

    @admin.action(description="Mark selected as Reviewed")
    def mark_reviewed(self, request, queryset):
        count = 0
        for app in queryset:
            app.status = ApplicationStatus.REVIEWED
            app.save()
            try:
                from apps.notifications.tasks import send_application_under_review_email
                send_application_under_review_email(app.pk)
            except Exception:
                pass
            count += 1
        self.message_user(request, f"{count} application(s) marked as Reviewed.")

    @admin.action(description="Mark selected as Approved")
    def mark_approved(self, request, queryset):
        count = 0
        for app in queryset:
            app.status = ApplicationStatus.APPROVED
            app.save()
            try:
                from apps.notifications.tasks import send_application_approved_email
                send_application_approved_email(app.pk)
            except Exception:
                pass
            count += 1
        self.message_user(request, f"{count} application(s) approved — approval emails queued.")

    @admin.action(description="Mark selected as Rejected")
    def mark_rejected(self, request, queryset):
        count = 0
        for app in queryset:
            app.status = ApplicationStatus.REJECTED
            app.save()
            try:
                from apps.notifications.tasks import send_application_rejected_email
                send_application_rejected_email(app.pk)
            except Exception:
                pass
            count += 1
        self.message_user(request, f"{count} application(s) rejected — rejection emails queued.")

    @admin.action(description="Re-generate application PDF")
    def regenerate_pdf(self, request, queryset):
        from apps.notifications.tasks import generate_rental_application_pdf
        count = 0
        for app in queryset:
            try:
                generate_rental_application_pdf(app.id)
            except Exception:
                generate_rental_application_pdf(app.id)
            count += 1
        self.message_user(request, f"PDF generation queued for {count} application(s).")

    @admin.action(description="Send Approval Email to Applicant(s)")
    def send_approval_email(self, request, queryset):
        from apps.notifications.tasks import send_application_approved_email
        count = 0
        for app in queryset:
            try:
                send_application_approved_email(app.pk)
            except Exception:
                send_application_approved_email(app.pk)
            count += 1
        self.message_user(request, f"Approval email sent for {count} applicant(s).")

    @admin.action(description="Send Rejection Email to Applicant(s)")
    def send_rejection_email(self, request, queryset):
        from apps.notifications.tasks import send_application_rejected_email
        count = 0
        for app in queryset:
            try:
                send_application_rejected_email(app.pk)
            except Exception:
                send_application_rejected_email(app.pk)
            count += 1
        self.message_user(request, f"Rejection email sent for {count} applicant(s).")

    @admin.action(description="Send Move-In Instructions Email")
    def send_move_in_email(self, request, queryset):
        from apps.notifications.tasks import send_move_in_instructions_email
        count = 0
        for app in queryset:
            try:
                send_move_in_instructions_email(app.pk)
            except Exception:
                send_move_in_instructions_email(app.pk)
            count += 1
        self.message_user(request, f"Move-in instructions sent for {count} applicant(s).")

    @admin.action(description="Send Recovery Email (re-engage abandoned applicants)")
    def send_recovery_email_action(self, request, queryset):
        from apps.notifications.tasks import send_abandoned_application_email
        count = 0
        for app in queryset:
            app.recovery_email_sent = False
            app.save(update_fields=["recovery_email_sent"])
            try:
                send_abandoned_application_email(app.pk)
            except Exception:
                send_abandoned_application_email(app.pk)
            count += 1
        self.message_user(request, f"Recovery email queued for {count} applicant(s).")


# ── Referral Program ──────────────────────────────────────────────────────────

class ReferralPayoutInline(TabularInline):
    model = ReferralPayout
    extra = 0
    fields = ["lead", "rental_application", "status", "monthly_rent", "commission_amount", "paid_at"]
    readonly_fields = ["commission_amount"]
    can_delete = False
    verbose_name = "Payout"
    verbose_name_plural = "Payouts"


@admin.register(Referrer)
class ReferrerAdmin(ModelAdmin):
    list_display  = ["name", "email", "phone", "code_badge", "payout_count", "total_earned_display", "is_active", "created_at"]
    list_filter   = ["is_active"]
    search_fields = ["name", "email", "code"]
    readonly_fields = ["code", "created_at", "referral_link"]
    ordering      = ["-created_at"]
    inlines       = [ReferralPayoutInline]

    fieldsets = (
        ("Referrer", {
            "fields": ("name", "email", "phone", "is_active", "notes"),
        }),
        ("Referral Link", {
            "fields": ("code", "referral_link"),
            "description": "Share this link with the referrer. It auto-tracks who sent the lead.",
        }),
        ("Timestamps", {
            "fields": ("created_at",),
            "classes": ("collapse",),
        }),
    )

    def referral_link(self, obj):
        path = f"/?ref={obj.code}"
        return format_html(
            '<code style="background:#f4f4f4;padding:4px 10px;border-radius:4px">{}</code>',
            path,
        )
    referral_link.short_description = "Referral Path"

    def code_badge(self, obj):
        return format_html(
            '<code style="background:#eff6ff;color:#1d4ed8;padding:2px 8px;border-radius:4px;font-weight:700">{}</code>',
            obj.code,
        )
    code_badge.short_description = "Code"

    def payout_count(self, obj):
        return obj.payouts.count()
    payout_count.short_description = "Referrals"

    def total_earned_display(self, obj):
        result = obj.payouts.filter(status=ReferralStatus.PAID).aggregate(t=Sum("commission_amount"))
        total = result["t"] or 0
        return format_html('<strong style="color:#16a34a">${:,.2f}</strong>', total)
    total_earned_display.short_description = "Total Paid Out"


@admin.register(ReferralPayout)
class ReferralPayoutAdmin(ModelAdmin):
    list_display  = ["referrer", "lead_name", "property_display", "status_badge", "monthly_rent", "commission_display", "created_at", "paid_at"]
    list_filter   = ["status", "referrer"]
    search_fields = ["referrer__name", "referrer__code", "lead__full_name", "lead__email"]
    ordering      = ["-created_at"]
    readonly_fields = ["commission_amount", "created_at"]
    actions       = ["mark_converted", "mark_paid", "mark_void"]

    fieldsets = (
        ("Referral", {
            "fields": ("referrer", "lead", "rental_application"),
        }),
        ("Commission", {
            "fields": ("status", "monthly_rent", "commission_rate", "commission_months", "commission_amount"),
            "description": "Commission = monthly_rent × commission_months × commission_rate. Auto-calculated on save.",
        }),
        ("Dates & Notes", {
            "fields": ("converted_at", "paid_at", "notes"),
        }),
        ("Timestamps", {
            "fields": ("created_at",),
            "classes": ("collapse",),
        }),
    )

    def lead_name(self, obj):
        return obj.lead.full_name if obj.lead else "—"
    lead_name.short_description = "Lead"

    def property_display(self, obj):
        if obj.rental_application and obj.rental_application.rental_property:
            return obj.rental_application.rental_property.title
        return "—"
    property_display.short_description = "Property"

    def status_badge(self, obj):
        colors = {
            ReferralStatus.PENDING:   "#f59e0b",
            ReferralStatus.CONVERTED: "#2563eb",
            ReferralStatus.PAID:      "#16a34a",
            ReferralStatus.VOID:      "#9ca3af",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:9999px;font-size:11px">{}</span>',
            color, obj.get_status_display(),
        )
    status_badge.short_description = "Status"

    def commission_display(self, obj):
        if obj.commission_amount:
            return format_html('<strong>${:,.2f}</strong>', obj.commission_amount)
        return "—"
    commission_display.short_description = "Commission"

    @admin.action(description="Mark selected as Tenant Converted")
    def mark_converted(self, request, queryset):
        updated = queryset.update(status=ReferralStatus.CONVERTED, converted_at=timezone.now())
        self.message_user(request, f"{updated} payout(s) marked as Converted.")

    @admin.action(description="Mark selected as Commission Paid")
    def mark_paid(self, request, queryset):
        updated = queryset.update(status=ReferralStatus.PAID, paid_at=timezone.now())
        self.message_user(request, f"{updated} payout(s) marked as Paid.")

    @admin.action(description="Mark selected as Void")
    def mark_void(self, request, queryset):
        updated = queryset.update(status=ReferralStatus.VOID)
        self.message_user(request, f"{updated} payout(s) voided.")
