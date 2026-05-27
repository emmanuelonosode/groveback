from django.db import models


class ApplicationStatus(models.TextChoices):
    SUBMITTED            = "SUBMITTED",            "Submitted"
    UNDER_REVIEW         = "UNDER_REVIEW",         "Under Review"
    INTERVIEW_SCHEDULED  = "INTERVIEW_SCHEDULED",  "Interview Scheduled"
    HIRED                = "HIRED",                "Hired"
    REJECTED             = "REJECTED",             "Rejected"


class JobApplication(models.Model):
    # Role info
    role_id    = models.CharField(max_length=100)   # slug: "remote-listing-specialist"
    role_title = models.CharField(max_length=200)   # display: "Remote Listing & Client Communication Specialist"

    # Applicant info
    full_name    = models.CharField(max_length=200)
    email        = models.EmailField()
    phone        = models.CharField(max_length=20)
    linkedin_url = models.URLField(blank=True)
    motivation   = models.TextField()

    # Role-specific Q&A (label/value pair from the dynamic form field)
    extra_field_label = models.CharField(max_length=200, blank=True)
    extra_field_value = models.CharField(max_length=300, blank=True)

    # Status tracking
    status     = models.CharField(
        max_length=30,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.SUBMITTED,
    )
    applied_at     = models.DateTimeField(auto_now_add=True)
    reviewed_by    = models.ForeignKey(
        "accounts.CustomUser",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_job_applications",
    )
    staff_notes    = models.TextField(blank=True)
    interview_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-applied_at"]
        verbose_name = "Job Application"
        verbose_name_plural = "Job Applications"

    def __str__(self):
        return f"{self.full_name} — {self.role_title} ({self.status})"
