from django.db import models
from cloudinary.models import CloudinaryField


class MaintenanceRequest(models.Model):
    class Category(models.TextChoices):
        PLUMBING   = "PLUMBING",   "Plumbing"
        ELECTRICAL = "ELECTRICAL", "Electrical"
        HVAC       = "HVAC",       "HVAC / Climate"
        APPLIANCE  = "APPLIANCE",  "Appliance"
        STRUCTURAL = "STRUCTURAL", "Structural"
        PEST       = "PEST",       "Pest Control"
        SECURITY   = "SECURITY",   "Security / Locks"
        OTHER      = "OTHER",      "Other"

    class Priority(models.TextChoices):
        LOW    = "LOW",    "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH   = "HIGH",   "High"
        URGENT = "URGENT", "Urgent — Safety Risk"

    class ReqStatus(models.TextChoices):
        SUBMITTED    = "SUBMITTED",    "Submitted"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
        IN_PROGRESS  = "IN_PROGRESS",  "In Progress"
        RESOLVED     = "RESOLVED",     "Resolved"
        CLOSED       = "CLOSED",       "Closed"

    client                = models.ForeignKey("crm.Client", on_delete=models.CASCADE, related_name="maintenance_requests")
    title                 = models.CharField(max_length=200)
    description           = models.TextField()
    category              = models.CharField(max_length=20, choices=Category.choices)
    priority              = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status                = models.CharField(max_length=20, choices=ReqStatus.choices, default=ReqStatus.SUBMITTED)
    photo                 = CloudinaryField("photo", blank=True, null=True)
    preferred_access_time = models.CharField(max_length=200, blank=True)
    staff_notes           = models.TextField(blank=True)
    resolved_at           = models.DateTimeField(null=True, blank=True)
    created_at            = models.DateTimeField(auto_now_add=True)
    updated_at            = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} [{self.get_status_display()}] — {self.client}"
