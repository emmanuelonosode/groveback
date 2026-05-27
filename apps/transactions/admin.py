from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from .models import Transaction, Payment, Invoice, TransactionStatus, InvoiceStatus, PaymentMethodConfig


@admin.register(PaymentMethodConfig)
class PaymentMethodConfigAdmin(ModelAdmin):
    list_display = ["method", "display_name", "handle_or_recipient", "is_active", "updated_at"]
    list_editable = ["display_name", "is_active"]
    list_display_links = ["method"]
    ordering = ["method"]

    fieldsets = (
        ("Basic Settings", {
            "fields": ("method", "display_name", "handle", "is_active", "extra_instructions"),
        }),
        ("Bank Transfer Details", {
            "description": (
                "Fill these in when Method = Bank Transfer. "
                "All fields are displayed to the applicant on the payment screen."
            ),
            "fields": (
                "recipient_name",
                "bank_name",
                "account_type",
                "account_number",
                "routing_number",
                "swift_bic",
                "bank_address",
                "recipient_address",
            ),
        }),
    )

    def handle_or_recipient(self, obj):
        return obj.handle or obj.recipient_name or "—"
    handle_or_recipient.short_description = "Handle / Recipient"


class PaymentInline(TabularInline):
    model = Payment
    extra = 0
    fields = ["amount", "payment_method", "status", "paid_at", "receipt_sent"]
    readonly_fields = ["paid_at"]


class InvoiceInline(TabularInline):
    model = Invoice
    extra = 1
    fields = ["invoice_number", "issued_date", "due_date", "subtotal", "tax_rate", "tax_amount", "total", "status"]
    readonly_fields = ["invoice_number"]


@admin.register(Transaction)
class TransactionAdmin(ModelAdmin):
    list_display = [
        "id", "client", "property_link", "agent",
        "transaction_type", "agreed_price_display",
        "commission_display", "status_badge", "created_at",
    ]
    list_filter = ["transaction_type", "status", "agent"]
    search_fields = ["client__lead__full_name", "property__title", "agent__email"]
    ordering = ["-created_at"]
    inlines = [PaymentInline, InvoiceInline]
    readonly_fields = ["commission_amount", "created_at", "updated_at"]
    actions = ["mark_completed", "mark_cancelled"]

    fieldsets = (
        ("Parties", {
            "fields": ("client", "property", "agent"),
        }),
        ("Deal", {
            "fields": ("transaction_type", "agreed_price", "commission_rate", "commission_amount"),
        }),
        ("Status", {
            "fields": ("status", "notes"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at", "completed_at"),
            "classes": ("collapse",),
        }),
    )

    def property_link(self, obj):
        return format_html('<a href="/admin/properties/property/{}/change/">{}</a>', obj.property.pk, obj.property.title)
    property_link.short_description = "Property"

    def agreed_price_display(self, obj):
        return f"${obj.agreed_price:,.0f}"
    agreed_price_display.short_description = "Price"

    def commission_display(self, obj):
        return f"${obj.commission_amount:,.0f} ({obj.commission_rate}%)"
    commission_display.short_description = "Commission"

    def status_badge(self, obj):
        colors = {
            TransactionStatus.PENDING: "#6b7280",
            TransactionStatus.DEPOSIT_PAID: "#2563eb",
            TransactionStatus.IN_PROGRESS: "#d97706",
            TransactionStatus.COMPLETED: "#16a34a",
            TransactionStatus.CANCELLED: "#dc2626",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:9999px;font-size:11px">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = "Status"

    @admin.action(description="Mark as Completed")
    def mark_completed(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(status=TransactionStatus.COMPLETED, completed_at=timezone.now())
        self.message_user(request, f"{updated} transactions marked as Completed.")

    @admin.action(description="Mark as Cancelled")
    def mark_cancelled(self, request, queryset):
        updated = queryset.update(status=TransactionStatus.CANCELLED)
        self.message_user(request, f"{updated} transactions cancelled.")


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = [
        "id", "payment_method", "amount", "status_badge", 
        "reference_id", "rental_application_link", "invoice_link", "proof_preview", "created_at"
    ]
    list_filter = ["status", "payment_method", "created_at"]
    search_fields = ["reference_id", "rental_application__first_name", "rental_application__last_name", "invoice__invoice_number"]
    readonly_fields = ["proof_preview_large", "verified_by", "verified_at", "created_at"]
    actions = ["verify_payment", "reject_payment"]

    fieldsets = (
        ("Payment Context", {
            "fields": ("transaction", "rental_application", "invoice", "amount", "payment_method", "status"),
        }),
        ("Manual Verification", {
            "fields": ("reference_id", "proof_preview_large"),
        }),
        ("Audit Trail", {
            "fields": ("verified_by", "verified_at", "rejection_reason"),
        }),
        ("Receipt & Notes", {
            "fields": ("receipt_sent", "receipt_pdf", "notes"),
        }),
    )

    def rental_application_link(self, obj):
        if obj.rental_application:
            return format_html(
                '<a href="/admin/crm/rentalapplication/{}/change/" style="color:#1A56DB;font-weight:600">App #{}</a>',
                obj.rental_application.pk, obj.rental_application.pk
            )
        return "—"
    rental_application_link.short_description = "Application"

    def invoice_link(self, obj):
        if obj.invoice:
            return format_html(
                '<a href="/admin/transactions/invoice/{}/change/" style="color:#1A56DB;font-weight:600">{}</a>',
                obj.invoice.pk, obj.invoice.invoice_number
            )
        return "—"
    invoice_link.short_description = "Invoice"

    def status_badge(self, obj):
        from .models import PaymentStatus
        colors = {
            PaymentStatus.PENDING: "#6b7280",
            PaymentStatus.PENDING_VERIFICATION: "#2563eb",
            PaymentStatus.VERIFIED: "#16a34a",
            PaymentStatus.REJECTED: "#dc2626",
            PaymentStatus.SUCCESSFUL: "#16a34a",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:9999px;font-size:11px">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = "Status"

    def proof_preview(self, obj):
        if obj.proof_image:
            return format_html(
                '<a href="{}" target="_blank"><img src="{}" style="width:40px;height:40px;object-fit:cover;border-radius:4px" /></a>',
                obj.proof_image, obj.proof_image
            )
        return "—"
    proof_preview.short_description = "Proof"

    def proof_preview_large(self, obj):
        if obj.proof_image:
            return format_html(
                '<a href="{}" target="_blank"><img src="{}" style="max-width:400px;border-radius:8px;border:1px solid #ddd" /></a>',
                obj.proof_image, obj.proof_image
            )
        return "Upload proof image to see preview."
    proof_preview_large.short_description = "Proof Image"

    @admin.action(description="Verify Selected Payments")
    def verify_payment(self, request, queryset):
        from django.utils import timezone
        from .models import PaymentStatus, InvoiceStatus
        from apps.crm.models import ApplicationStatus
        
        count = 0
        for payment in queryset.filter(status=PaymentStatus.PENDING_VERIFICATION):
            payment.status = PaymentStatus.VERIFIED
            payment.verified_by = request.user
            payment.verified_at = timezone.now()
            payment.save()
            
            # Update linked rental application
            if payment.rental_application:
                app = payment.rental_application
                app.is_fee_paid = True
                app.status = ApplicationStatus.SUBMITTED
                app.save()

            # Update linked invoice
            if payment.invoice:
                inv = payment.invoice
                inv.status = InvoiceStatus.PAID
                inv.save()
            
            count += 1
        self.message_user(request, f"{count} payments verified successfully.")

    @admin.action(description="Reject Selected Payments")
    def reject_payment(self, request, queryset):
        from .models import PaymentStatus, InvoiceStatus
        from apps.crm.models import ApplicationStatus

        count = 0
        for payment in queryset:
            payment.status = PaymentStatus.REJECTED
            payment.rejection_reason = payment.rejection_reason or "Proof could not be verified. Please re-submit a clear screenshot."
            payment.save()

            if payment.rental_application:
                app = payment.rental_application
                app.status = ApplicationStatus.PAYMENT_FAILED
                app.save()

            # Revert invoice back to SENT so the tenant can re-submit
            if payment.invoice and payment.invoice.status == InvoiceStatus.PAID:
                payment.invoice.status = InvoiceStatus.SENT
                payment.invoice.save()

            count += 1
        self.message_user(request, f"{count} payments rejected.")


@admin.register(Invoice)
class InvoiceAdmin(ModelAdmin):
    list_display  = ["invoice_number", "title", "user_or_client", "total_display", "status_badge", "issued_date", "due_date", "pdf_link"]
    list_filter   = ["status", "issued_date"]
    search_fields = ["invoice_number", "title", "user__email", "transaction__client__lead__full_name"]
    ordering      = ["-created_at"]
    readonly_fields = ["invoice_number", "pdf", "created_at", "pdf_link"]
    actions = ["generate_pdf_action", "send_invoice_action"]

    fieldsets = (
        ("Invoice Info", {
            "fields": ("user", "transaction", "invoice_number", "status"),
        }),
        ("Details", {
            "fields": ("title", "description"),
        }),
        ("Dates", {
            "fields": ("issued_date", "due_date"),
        }),
        ("Line Items & Totals", {
            "fields": ("line_items", "subtotal", "tax_rate", "tax_amount", "total"),
        }),
        ("Documents & Integration", {
            "fields": ("pdf", "pdf_link"),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("created_at",),
            "classes": ("collapse",),
        }),
    )

    def user_or_client(self, obj):
        if obj.user:
            return obj.user.full_name
        if obj.transaction:
            return obj.transaction.client.full_name
        return "—"
    user_or_client.short_description = "Recipient"

    def total_display(self, obj):
        return f"${obj.total:,.2f}"
    total_display.short_description = "Total"

    def status_badge(self, obj):
        colors = {
            InvoiceStatus.DRAFT: "#6b7280",
            InvoiceStatus.SENT: "#2563eb",
            InvoiceStatus.PAID: "#16a34a",
            InvoiceStatus.VOID: "#dc2626",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:9999px;font-size:11px">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = "Status"

    def pdf_link(self, obj):
        if obj.pdf:
            return format_html(
                '<a href="{}" target="_blank" style="color:#1A56DB;font-weight:600">Download</a>',
                obj.pdf,
            )
        return "—"
    pdf_link.short_description = "PDF"

    @admin.action(description="Generate PDF Invoice")
    def generate_pdf_action(self, request, queryset):
        from apps.notifications.tasks import generate_invoice_pdf
        count = 0
        for invoice in queryset:
            try:
                generate_invoice_pdf(invoice.pk)
            except Exception:
                pass
            count += 1
        self.message_user(
            request,
            f"PDF generation queued for {count} invoice(s). Refresh in a moment to see the download link.",
        )

    @admin.action(description="Send Invoice to Client (email PDF)")
    def send_invoice_action(self, request, queryset):
        from apps.notifications.tasks import send_invoice_email
        sent = skipped = 0
        for invoice in queryset:
            if invoice.pdf:
                try:
                    send_invoice_email(invoice.pk)
                except Exception:
                    pass
                sent += 1
            else:
                skipped += 1
        msg = f"Email sent for {sent} invoice(s)."
        if skipped:
            msg += f" {skipped} skipped — generate PDF first."
        self.message_user(request, msg)
