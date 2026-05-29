from django.db import models


class VisitorSession(models.Model):
    session_id   = models.CharField(max_length=64, unique=True, db_index=True)

    # IP & location (IP captured server-side from request headers)
    ip_address   = models.GenericIPAddressField(null=True, blank=True)
    city         = models.CharField(max_length=100, blank=True)
    region       = models.CharField(max_length=100, blank=True)
    country_code = models.CharField(max_length=10,  blank=True)

    # Device
    browser      = models.CharField(max_length=100, blank=True)
    os           = models.CharField(max_length=50,  blank=True)
    device_type  = models.CharField(max_length=20,  blank=True)  # Mobile / Desktop
    screen       = models.CharField(max_length=30,  blank=True)
    language     = models.CharField(max_length=20,  blank=True)
    timezone     = models.CharField(max_length=60,  blank=True)

    # Attribution
    landing_page  = models.CharField(max_length=500, blank=True)
    referrer      = models.TextField(blank=True)
    utm_source    = models.CharField(max_length=100, blank=True)
    utm_medium    = models.CharField(max_length=100, blank=True)
    utm_campaign  = models.CharField(max_length=200, blank=True)
    referral_code = models.CharField(max_length=20,  blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Visitor Session"
        verbose_name_plural = "Visitor Sessions"

    def __str__(self):
        return f"{self.city or 'Unknown'} · {self.browser} · {self.created_at:%Y-%m-%d %H:%M}"
