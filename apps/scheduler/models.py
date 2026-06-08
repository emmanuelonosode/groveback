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
