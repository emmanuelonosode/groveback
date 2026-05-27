from django.db import models
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

#not commited yet
class TransactionType(models.TextChoices):
    SALE = "SALE", "Sale"
    RENT = "RENT", "Rent"
    LEASE = "LEASE", "Lease"


class TransactionStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    DEPOSIT_PAID = "DEPOSIT_PAID", "Deposit Paid"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class PaymentMethod(models.TextChoices):
    BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer"
    CASH = "CASH", "Cash"
    CHECK = "CHECK", "Check"
    PAYPAL = "PAYPAL", "PayPal"
    VENMO = "VENMO", "Venmo"
    CASHAPP = "CASHAPP", "CashApp"
    CHIME = "CHIME", "Chime"


class PaymentMethodConfig(models.Model):
    method = models.CharField(max_length=20, choices=PaymentMethod.choices, unique=True)
    display_name = models.CharField(max_length=50, help_text='e.g. "Venmo", "Cash App"')
    handle = models.CharField(max_length=200, blank=True, help_text='e.g. "@HaskerRealty" or "payments@haskerrealtygroup.com"')
    is_active = models.BooleanField(default=True)
    extra_instructions = models.TextField(blank=True, help_text="Optional note shown to tenants (e.g. 'Use Friends & Family')")
    updated_at = models.DateTimeField(auto_now=True)

    # Bank Transfer specific fields
    recipient_name = models.CharField(max_length=200, blank=True, help_text="e.g. Jerry Michael Skelton")
    bank_name = models.CharField(max_length=100, blank=True, help_text="e.g. Renasant Bank")
    account_type = models.CharField(max_length=50, blank=True, help_text="e.g. Checking Account")
    account_number = models.CharField(max_length=50, blank=True)
    routing_number = models.CharField(max_length=20, blank=True, help_text="Wire / ABA routing number")
    swift_bic = models.CharField(max_length=20, blank=True, verbose_name="SWIFT / BIC Code")
    bank_address = models.TextField(blank=True, help_text="Full bank branch address")
    recipient_address = models.TextField(blank=True, help_text="Recipient's mailing address")

    class Meta:
        ordering = ["method"]
        verbose_name = "Payment Method Config"
        verbose_name_plural = "Payment Method Configs"

    def __str__(self):
        return f"{self.display_name} — {self.handle or self.recipient_name or self.method}"


class PaymentStatus(models.TextChoices):
    # ... (rest of choices remain the same)
    PENDING = "PENDING", "Pending"
    PENDING_VERIFICATION = "PENDING_VERIFICATION", "Pending Verification"
    SUCCESSFUL = "SUCCESSFUL", "Successful"
    VERIFIED = "VERIFIED", "Verified"
    FAILED = "FAILED", "Failed"
    REJECTED = "REJECTED", "Rejected"
    REFUNDED = "REFUNDED", "Refunded"


class InvoiceStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SENT = "SENT", "Sent"
    PAID = "PAID", "Paid"
    VOID = "VOID", "Void"


class Transaction(models.Model):
    # ... (existing Transaction model fields)
    client = models.ForeignKey(
        "crm.Client",
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    agent = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    transaction_type = models.CharField(max_length=10, choices=TransactionType.choices)
    agreed_price = models.DecimalField(max_digits=12, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=3.00)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=TransactionStatus.choices, default=TransactionStatus.PENDING)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Transaction #{self.pk} — {self.client} / {self.property}"

    def save(self, *args, **kwargs):
        # Auto-calculate commission if not manually set
        if not self.commission_amount:
            self.commission_amount = self.agreed_price * (self.commission_rate / 100)
        super().save(*args, **kwargs)


class Payment(models.Model):
    transaction = models.ForeignKey(
        Transaction, 
        on_delete=models.CASCADE, 
        related_name="payments",
        null=True, blank=True
    )
    rental_application = models.ForeignKey(
        "crm.RentalApplication",
        on_delete=models.CASCADE,
        related_name="payments",
        null=True, blank=True
    )
    invoice = models.ForeignKey(
        "Invoice",
        on_delete=models.CASCADE,
        related_name="payments",
        null=True, blank=True
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    
    # Manual Verification Fields
    reference_id = models.CharField(
        max_length=100, 
        blank=True, 
        help_text="User-provided Ref ID, CashTag, or PayPal email"
    )
    proof_image = models.CharField(
        max_length=500, 
        blank=True, 
        help_text="Cloudinary URL of the receipt/screenshot"
    )
    
    verified_by = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="verified_payments"
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    paid_at = models.DateTimeField(null=True, blank=True)
    receipt_sent = models.BooleanField(default=False)
    receipt_pdf = models.CharField(max_length=500, blank=True, help_text="Cloudinary URL of generated PDF receipt")
    notes = models.TextField(blank=True)
    allocated_items = models.JSONField(
        default=list,
        blank=True,
        help_text='Line item descriptions covered by this payment, e.g. ["Security Deposit", "Pet Fee"]',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_at", "-id"]

    def __str__(self):
        return f"Payment ${self.amount} ({self.get_status_display()})"


class Invoice(models.Model):
    user = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.CASCADE,
        related_name="invoices",
        null=True, blank=True,
        help_text="Directly assign an invoice to a user profile."
    )
    transaction = models.ForeignKey(
        Transaction, 
        on_delete=models.CASCADE, 
        related_name="invoices",
        null=True, blank=True
    )
    invoice_number = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200, help_text='e.g. "Monthly Rent - August 2026"')
    description = models.TextField(blank=True, help_text="Detailed breakdown of the charges.")
    issued_date = models.DateField()
    due_date = models.DateField()
    line_items = models.JSONField(
        default=list,
        help_text='[{"description": "...", "quantity": 1, "unit_price": 100.00, "total": 100.00}]',
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    pdf = models.CharField(max_length=500, blank=True, help_text="Cloudinary URL of generated PDF invoice")
    status = models.CharField(max_length=10, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invoice {self.invoice_number} — {self.get_status_display()}"

    @classmethod
    def generate_invoice_number(cls):
        from django.utils import timezone
        year = timezone.now().year
        last = cls.objects.filter(invoice_number__startswith=f"HRG-{year}-").order_by("-id").first()
        if last:
            try:
                seq = int(last.invoice_number.split("-")[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f"HRG-{year}-{seq:04d}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        super().save(*args, **kwargs)


# ── Signals ───────────────────────────────────────────────────────────────────

def _send(task_fn, pk):
    try:
        task_fn(pk)
    except Exception:
        pass


@receiver(pre_save, sender=Payment)
def auto_stamp_payment_timestamps(sender, instance, **kwargs):
    """Auto-set verified_at when status transitions to VERIFIED or REJECTED."""
    if not instance.pk:
        return
    try:
        old = Payment.objects.get(pk=instance.pk)
        if old.status != instance.status:
            if instance.status == "VERIFIED" and not instance.verified_at:
                instance.verified_at = timezone.now()
            if instance.status == "REJECTED" and not instance.verified_at:
                instance.verified_at = timezone.now()
    except Payment.DoesNotExist:
        pass


@receiver(post_save, sender=Invoice)
def trigger_invoice_notification(sender, instance, created, **kwargs):
    """Trigger email when invoice is marked as SENT."""
    if instance.status == "SENT":
        try:
            from apps.notifications.tasks import send_invoice_email
            _send(send_invoice_email, instance.pk)
        except Exception:
            pass


@receiver(post_save, sender=Payment)
def trigger_payment_notifications(sender, instance, created, **kwargs):
    """Trigger emails for payment submission, verification, and rejection."""
    try:
        from apps.notifications.tasks import (
            send_payment_submitted_email,
            send_payment_verified_email,
            send_payment_rejected_email,
        )

        if created and instance.status == "PENDING_VERIFICATION":
            _send(send_payment_submitted_email, instance.pk)

        # Only fire verification email once — gate on receipt_sent flag
        if not created and instance.status == "VERIFIED" and instance.verified_at and not instance.receipt_sent:
            Payment.objects.filter(pk=instance.pk).update(receipt_sent=True)
            _send(send_payment_verified_email, instance.pk)

        # Rejection notification
        if not created and instance.status == "REJECTED" and not instance.receipt_sent:
            Payment.objects.filter(pk=instance.pk).update(receipt_sent=True)
            _send(send_payment_rejected_email, instance.pk)

    except Exception:
        pass
