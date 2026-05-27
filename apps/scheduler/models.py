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
    notes = models.TextField(blank=True)
    reminder_sent = models.BooleanField(default=False)
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
