from django.db import models
from django.conf import settings
from django.utils import timezone

class Visitor(models.Model):
    """
    Represents a unique device/browser across multiple sessions.
    Mapped to an authenticated user when they log in or register.
    """
    fingerprint_id = models.CharField(max_length=128, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="visitors"
    )
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    # Aggregate User Profiling / Intelligence
    total_sessions_count = models.PositiveIntegerField(default=0)
    total_dwell_time = models.FloatField(default=0.0, help_text="Cumulative active time across all sessions in seconds")
    primary_device = models.CharField(max_length=50, blank=True)
    primary_city = models.CharField(max_length=100, blank=True)
    first_ip = models.GenericIPAddressField(null=True, blank=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    associated_email = models.EmailField(blank=True)
    searched_locations = models.JSONField(default=list, blank=True)
    viewed_property_ids = models.JSONField(default=list, blank=True)
    is_lead = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-last_seen"]
        verbose_name = "Visitor"
        verbose_name_plural = "Visitors"

    def __str__(self):
        if self.associated_email:
            return f"{self.associated_email} ({self.fingerprint_id[:8]})"
        if self.user:
            return f"{self.user.email} ({self.fingerprint_id[:8]})"
        return f"Visitor {self.fingerprint_id[:8]}..."


class VisitorSession(models.Model):
    """
    Represents a single continuous browsing session for a Visitor.
    """
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name="sessions", null=True, blank=True)
    session_id = models.CharField(max_length=64, unique=True, db_index=True)
    
    # IP & location
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    city = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=100, blank=True)
    country_code = models.CharField(max_length=10, blank=True)

    # Device & Hardware Context
    browser = models.CharField(max_length=100, blank=True)
    os = models.CharField(max_length=50, blank=True)
    device_type = models.CharField(max_length=20, blank=True)
    screen = models.CharField(max_length=30, blank=True)
    viewport = models.CharField(max_length=30, blank=True)
    pixel_ratio = models.FloatField(default=1.0)
    connection_type = models.CharField(max_length=30, blank=True)
    hardware_concurrency = models.PositiveSmallIntegerField(default=0)
    device_memory = models.FloatField(default=0.0)
    max_touch_points = models.PositiveSmallIntegerField(default=0)
    orientation = models.CharField(max_length=50, blank=True)
    language = models.CharField(max_length=20, blank=True)
    timezone = models.CharField(max_length=60, blank=True)

    # Attribution & Real Estate Intent
    landing_page = models.CharField(max_length=500, blank=True)
    referrer = models.TextField(blank=True)
    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=200, blank=True)
    referral_code = models.CharField(max_length=20, blank=True)
    searched_cities = models.JSONField(default=list, blank=True)
    properties_viewed_count = models.PositiveIntegerField(default=0)
    price_range_min = models.IntegerField(null=True, blank=True)
    price_range_max = models.IntegerField(null=True, blank=True)

    # Lifecycle
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    
    # Denormalization for quick querying
    total_dwell_time = models.FloatField(default=0.0, help_text="Total active time in seconds")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Visitor Session"
        verbose_name_plural = "Visitor Sessions"

    def __str__(self):
        return f"{self.city or 'Unknown'} · {self.browser} · {self.created_at:%Y-%m-%d %H:%M}"


class PageVisit(models.Model):
    """
    Represents an exact page view within a session.
    """
    session = models.ForeignKey(VisitorSession, on_delete=models.CASCADE, related_name="page_visits")
    path = models.CharField(max_length=500)
    
    entry_time = models.DateTimeField(default=timezone.now)
    exit_time = models.DateTimeField(null=True, blank=True)
    
    # Engagement
    max_scroll_depth = models.FloatField(default=0.0, help_text="Percentage 0.0 to 100.0")
    idle_time = models.FloatField(default=0.0, help_text="Idle time in seconds")

    class Meta:
        ordering = ["entry_time"]
        verbose_name = "Page Visit"
        verbose_name_plural = "Page Visits"

    def __str__(self):
        return f"Visit {self.path} at {self.entry_time:%Y-%m-%d %H:%M}"


class TelemetryEvent(models.Model):
    """
    Granular events (clicks, form submits, etc.) linked to a session or specific page visit.
    """
    session = models.ForeignKey(VisitorSession, on_delete=models.CASCADE, related_name="events")
    page_visit = models.ForeignKey(PageVisit, on_delete=models.SET_NULL, null=True, blank=True, related_name="events")
    
    event_type = models.CharField(max_length=100, db_index=True)
    event_data = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Telemetry Event"
        verbose_name_plural = "Telemetry Events"
        indexes = [
            models.Index(fields=["event_type", "created_at"]),
        ]

    def __str__(self):
        return f"Event {self.event_type} at {self.created_at:%Y-%m-%d %H:%M}"


class RawTelemetryEvent(models.Model):
    """
    Durable intake spool. The public beacon endpoint does a single fast insert
    here; an out-of-band processor (manage.py process_telemetry, via cron) turns
    these rows into Visitor / VisitorSession / PageVisit / TelemetryEvent.
    Decouples DB linking from the request path and survives restarts (no Redis).
    """
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed = models.BooleanField(default=False, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["received_at"]
        indexes = [
            # Fast "oldest unprocessed first" scan for the processor.
            models.Index(fields=["processed", "received_at"]),
        ]
        verbose_name = "Raw Telemetry Event"
        verbose_name_plural = "Raw Telemetry Events (spool)"

    def __str__(self):
        state = "processed" if self.processed else "pending"
        return f"RawEvent #{self.pk} ({state}, {self.received_at:%Y-%m-%d %H:%M})"
