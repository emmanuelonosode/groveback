from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin, TabularInline

from .models import Visitor, VisitorSession, PageVisit, TelemetryEvent, RawTelemetryEvent


def _fmt_duration(seconds) -> str:
    s = int(seconds or 0)
    if s >= 3600:
        return f"{s // 3600}h {(s % 3600) // 60}m"
    if s >= 60:
        return f"{s // 60}m {s % 60}s"
    return f"{s}s"


def _returning_badge(is_returning: bool):
    label = "Returning" if is_returning else "New"
    bg = "#1d4ed8" if is_returning else "#16a34a"
    return format_html(
        '<span style="background:{};color:#fff;padding:2px 8px;border-radius:9999px;'
        'font-size:11px;font-weight:600;white-space:nowrap;">{}</span>',
        bg, label,
    )


# ── Inlines ───────────────────────────────────────────────────────────────────

class PageVisitInline(TabularInline):
    model = PageVisit
    extra = 0
    max_num = 0
    can_delete = False
    fields = ["path", "entry_time", "max_scroll_depth", "idle_time"]
    readonly_fields = fields
    ordering = ["entry_time"]

    def has_add_permission(self, request, obj=None):
        return False


class TelemetryEventInline(TabularInline):
    model = TelemetryEvent
    extra = 0
    max_num = 0
    can_delete = False
    fields = ["created_at", "event_type", "event_data"]
    readonly_fields = fields
    ordering = ["created_at"]

    def has_add_permission(self, request, obj=None):
        return False


class SessionInline(TabularInline):
    """Read-only summary of a visitor's sessions — shows the return history."""
    model = VisitorSession
    fk_name = "visitor"
    extra = 0
    max_num = 0
    can_delete = False
    fields = ["start_time", "where", "device_type", "browser", "dwell", "landing_page"]
    readonly_fields = fields
    ordering = ["-start_time"]

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Location")
    def where(self, obj):
        return ", ".join([p for p in [obj.city, obj.region, obj.country_code] if p]) or "—"

    @admin.display(description="Dwell")
    def dwell(self, obj):
        return _fmt_duration(obj.total_dwell_time)


# ── Visitor ─────────────────────────────────────────────────────────────────

@admin.register(Visitor)
class VisitorAdmin(ModelAdmin):
    list_display = ["who", "status", "sessions_count", "first_seen", "last_seen"]
    search_fields = ["fingerprint_id", "user__email", "user__first_name", "user__last_name"]
    ordering = ["-last_seen"]
    list_filter = ["first_seen", "last_seen"]
    inlines = [SessionInline]
    readonly_fields = [f.name for f in Visitor._meta.fields]

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related("user")
            .annotate(_sessions=Count("sessions", distinct=True))
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Visitor")
    def who(self, obj):
        if obj.user_id:
            return obj.user.get_full_name() or obj.user.email
        return format_html('<span style="color:#64748b;">anon · {}</span>', obj.fingerprint_id[:10])

    @admin.display(description="Status")
    def status(self, obj):
        return _returning_badge(getattr(obj, "_sessions", 0) > 1)

    @admin.display(description="Sessions", ordering="_sessions")
    def sessions_count(self, obj):
        return getattr(obj, "_sessions", 0)


# ── Visitor Session (the journey view) ────────────────────────────────────────

@admin.register(VisitorSession)
class VisitorSessionAdmin(ModelAdmin):
    list_display = ["when", "visitor_label", "status", "location", "device", "pages", "events", "dwell", "source"]
    list_filter = ["device_type", "country_code", "utm_source", "start_time"]
    search_fields = ["city", "region", "ip_address", "referral_code", "utm_campaign", "landing_page", "session_id", "visitor__fingerprint_id", "visitor__user__email"]
    date_hierarchy = "start_time"
    ordering = ["-start_time"]
    inlines = [PageVisitInline, TelemetryEventInline]

    fieldsets = (
        ("Session journey", {"fields": ("journey",)}),
        ("Visitor", {"fields": ("visitor", "ip_address", "city", "region", "country_code")}),
        ("Acquisition", {"fields": ("landing_page", "referrer", "utm_source", "utm_medium", "utm_campaign", "referral_code"), "classes": ("collapse",)}),
        ("Device", {"fields": ("device_type", "browser", "os", "screen", "language", "timezone"), "classes": ("collapse",)}),
        ("Timing", {"fields": ("start_time", "end_time", "total_dwell_time", "session_id"), "classes": ("collapse",)}),
    )
    readonly_fields = ["journey"] + [f.name for f in VisitorSession._meta.fields]

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related("visitor", "visitor__user")
            .prefetch_related("page_visits", "events")
            .annotate(
                _pages=Count("page_visits", distinct=True),
                _events=Count("events", distinct=True),
                _visitor_sessions=Count("visitor__sessions", distinct=True),
            )
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False  # read-only; view permission still allows opening the detail

    # ── list columns ──────────────────────────────────────────────────────────
    @admin.display(description="When", ordering="start_time")
    def when(self, obj):
        return obj.start_time.strftime("%b %d, %Y · %H:%M") if obj.start_time else "—"

    @admin.display(description="Visitor")
    def visitor_label(self, obj):
        v = obj.visitor
        if v and v.user_id:
            return v.user.get_full_name() or v.user.email
        if v:
            return format_html('<span style="color:#64748b;">anon · {}</span>', v.fingerprint_id[:8])
        return "—"

    @admin.display(description="Type")
    def status(self, obj):
        return _returning_badge(getattr(obj, "_visitor_sessions", 0) > 1)

    @admin.display(description="Location")
    def location(self, obj):
        return ", ".join([p for p in [obj.city, obj.region, obj.country_code] if p]) or "—"

    @admin.display(description="Device")
    def device(self, obj):
        return f"{obj.device_type or '?'} · {obj.browser or '?'}"

    @admin.display(description="Pages", ordering="_pages")
    def pages(self, obj):
        return getattr(obj, "_pages", 0)

    @admin.display(description="Events", ordering="_events")
    def events(self, obj):
        return getattr(obj, "_events", 0)

    @admin.display(description="Dwell")
    def dwell(self, obj):
        return _fmt_duration(obj.total_dwell_time)

    @admin.display(description="Source")
    def source(self, obj):
        if obj.utm_source:
            return obj.utm_source
        if obj.referrer:
            return (obj.referrer[:34] + "…") if len(obj.referrer) > 34 else obj.referrer
        return "Direct"

    # ── the journey timeline ────────────────────────────────────────────────────
    @admin.display(description="What this visitor did")
    def journey(self, obj):
        items = []
        for pv in obj.page_visits.all():
            detail = pv.path or "(page)"
            if pv.max_scroll_depth:
                detail += f"   ·   scrolled {pv.max_scroll_depth:.0f}%"
            items.append((pv.entry_time, "Page view", "#1d4ed8", detail))

        for ev in obj.events.all():
            data = ev.event_data if isinstance(ev.event_data, dict) else {}
            detail = data.get("element") or ", ".join(f"{k}: {v}" for k, v in list(data.items())[:3])
            items.append((ev.created_at, ev.event_type.replace("_", " ").title(), "#16a34a", detail or "—"))

        items = [i for i in items if i[0] is not None]
        items.sort(key=lambda x: x[0])

        header = format_html(
            '<div style="margin-bottom:12px;font-size:13px;color:#475569;">'
            '<b>{}</b> page views · <b>{}</b> events · <b>{}</b> on site'
            '{}</div>',
            getattr(obj, "_pages", obj.page_visits.count()),
            getattr(obj, "_events", obj.events.count()),
            _fmt_duration(obj.total_dwell_time),
            mark_safe(' · <span style="color:#1d4ed8;font-weight:600;">returning visitor</span>'
                      if getattr(obj, "_visitor_sessions", 0) > 1 else ''),
        )

        if not items:
            return format_html(
                '{}<em style="color:#94a3b8;">No page views or events recorded yet for this session.</em>',
                header,
            )

        rows = format_html_join(
            "",
            '<div style="display:flex;gap:12px;align-items:baseline;padding:7px 0;border-bottom:1px solid #eef2f6;">'
            '<span style="color:#94a3b8;font-size:12px;width:70px;flex:none;font-variant-numeric:tabular-nums;">{}</span>'
            '<span style="font-size:11px;font-weight:700;color:{};width:90px;flex:none;text-transform:uppercase;letter-spacing:.04em;">{}</span>'
            '<span style="font-size:13px;color:#1e293b;word-break:break-word;">{}</span>'
            '</div>',
            ((t.strftime("%H:%M:%S"), color, kind, detail) for (t, kind, color, detail) in items[:400]),
        )
        return format_html('<div style="max-width:820px;">{}{}</div>', header, rows)


# ── Raw tables (still browsable directly) ─────────────────────────────────────

@admin.register(PageVisit)
class PageVisitAdmin(ModelAdmin):
    list_display = ["path", "session", "entry_time", "max_scroll_depth", "idle_time"]
    search_fields = ["path", "session__session_id"]
    ordering = ["-entry_time"]
    list_filter = ["entry_time"]
    readonly_fields = [f.name for f in PageVisit._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TelemetryEvent)
class TelemetryEventAdmin(ModelAdmin):
    list_display = ["event_type", "session", "created_at"]
    search_fields = ["event_type", "session__session_id"]
    list_filter = ["event_type", "created_at"]
    ordering = ["-created_at"]
    readonly_fields = [f.name for f in TelemetryEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RawTelemetryEvent)
class RawTelemetryEventAdmin(ModelAdmin):
    """Intake-spool health: how many events are waiting to be processed."""
    list_display = ["id", "processed", "attempts", "received_at"]
    list_filter = ["processed", "received_at"]
    ordering = ["-received_at"]
    readonly_fields = [f.name for f in RawTelemetryEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
