import uuid

from django.db import models


class ViewingStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", "Scheduled"
    CONFIRMED = "CONFIRMED", "Confirmed"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"
    NO_SHOW = "NO_SHOW", "No Show"


class Viewing(models.Model):
    lead = models.ForeignKey(
        "crm.Lead",
        on_delete=models.CASCADE,
        related_name="viewings",
    )
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="viewings",
    )
    agent = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.PROTECT,
        related_name="viewings",
    )
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=ViewingStatus.choices, default=ViewingStatus.SCHEDULED)
    lease_term = models.CharField(
        max_length=50, blank=True,
        help_text='Shown in the confirmation email, e.g. "24 months". Leave blank to hide.',
    )
    access_code = models.CharField(
        max_length=20, blank=True,
        help_text="Self-tour entry code. If set, it appears in the confirmation email; "
                  "if blank, the email says the code will be sent before the tour.",
    )
    notes = models.TextField(blank=True)
    reminder_sent = models.BooleanField(default=False)
    confirmation_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_at"]
        indexes = [
            models.Index(fields=["scheduled_at", "status"]),
            models.Index(fields=["agent", "scheduled_at"]),
        ]

    def __str__(self):
        return f"Viewing: {self.lead.full_name} @ {self.property.title} on {self.scheduled_at:%Y-%m-%d %H:%M}"


class TourRequestStatus(models.TextChoices):
    AWAITING_ID = "AWAITING_ID", "Awaiting ID"          # lead captured, ID not yet uploaded
    PENDING_REVIEW = "PENDING_REVIEW", "Pending Review"  # ID uploaded, awaiting admin
    APPROVED = "APPROVED", "Approved"                    # identity verified, viewing booked
    REJECTED = "REJECTED", "Rejected"


class TourRequest(models.Model):
    """
    A visitor's request to tour a property. The lead is captured immediately
    (step 1) so it's never lost; identity verification (ID upload) is required
    only to actually schedule the self-tour. An admin reviews the ID and, on
    approval, books a Viewing (which sends the self-tour confirmation email).
    """
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    lead = models.ForeignKey(
        "crm.Lead", on_delete=models.SET_NULL, null=True, blank=True, related_name="tour_requests",
    )
    property = models.ForeignKey(
        "properties.Property", on_delete=models.CASCADE, related_name="tour_requests",
    )

    # Contact (denormalized so the request stands on its own)
    full_name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)

    # Schedule
    preferred_date = models.DateField(null=True, blank=True)
    preferred_time = models.CharField(max_length=60, blank=True, help_text="Requested time slot")
    tour_type = models.CharField(max_length=30, blank=True, default="self-tour")
    notes = models.TextField(blank=True)

    # Identity verification (sensitive — government ID images, stored on Cloudinary)
    id_front = models.URLField(max_length=600, blank=True)
    id_back = models.URLField(max_length=600, blank=True)

    status = models.CharField(
        max_length=20, choices=TourRequestStatus.choices, default=TourRequestStatus.AWAITING_ID, db_index=True,
    )
    reviewed_by = models.ForeignKey(
        "accounts.CustomUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_tour_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    viewing = models.ForeignKey(
        "scheduler.Viewing", on_delete=models.SET_NULL, null=True, blank=True, related_name="tour_requests",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Tour Request"
        verbose_name_plural = "Tour Requests"
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self):
        return f"Tour request: {self.full_name} @ {self.property.title} ({self.get_status_display()})"
