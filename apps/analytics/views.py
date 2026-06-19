import logging
import random
import re
from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
from datetime import timedelta
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from django.http import JsonResponse
from .models import Visitor, VisitorSession, PageVisit, TelemetryEvent, RawTelemetryEvent
from .services import process_spool, unprocessed_backlog

from apps.accounts.permissions import IsManagerOrAbove

logger = logging.getLogger(__name__)

# Intake guards
MAX_EVENTS_PER_REQUEST = 50
BACKLOG_VALVE_THRESHOLD = 2000   # if the spool grows past this (cron down), drain inline
_BOT_RE = re.compile(r"(bot|crawl|spider|slurp|bingpreview|headless|lighthouse|pingdom|gtmetrix)", re.I)


def _client_ip(request):
    return (
        request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        or request.META.get("HTTP_X_REAL_IP", "")
        or request.META.get("REMOTE_ADDR", "")
    ) or None


class TelemetryThrottle(SimpleRateThrottle):
    """Per-IP throttle for the open telemetry beacon (rate from settings)."""
    scope = "telemetry"

    def get_cache_key(self, request, view):
        ident = _client_ip(request) or "anon"
        return self.cache_format % {"scope": self.scope, "ident": ident}


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([TelemetryThrottle])
def visitor_session(request):
    """
    POST /api/v1/analytics/visitors/
    Durable, fire-and-forget telemetry intake. Accepts a single event payload
    or a batch {"events": [...]}. Each valid event is appended to the
    RawTelemetryEvent spool (one fast insert); an out-of-band processor
    (manage.py process_telemetry, via cron) links them into the structured
    models. No model linking happens in the request path.
    """
    # Drop obvious bots — they only inflate the data.
    ua = request.META.get("HTTP_USER_AGENT", "")
    if _BOT_RE.search(ua):
        return JsonResponse({"status": "ignored"})

    raw = request.data
    if isinstance(raw, dict) and isinstance(raw.get("events"), list):
        events = raw["events"]
    elif isinstance(raw, list):
        events = raw
    elif isinstance(raw, dict):
        events = [raw]
    else:
        events = []

    if not events:
        return Response({"detail": "no events"}, status=400)

    events = events[:MAX_EVENTS_PER_REQUEST]
    ip = _client_ip(request)
    now_iso = timezone.now().isoformat()
    user_id = request.user.id if (request.user and request.user.is_authenticated) else None

    rows = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if not str(ev.get("session_id") or "").strip():
            continue
        ev["ip_address"] = ip
        # Trust the server clock for ordering, not the client's.
        ev["timestamp"] = now_iso
        if user_id:
            ev["user_id"] = user_id
        rows.append(RawTelemetryEvent(payload=ev))

    if rows:
        try:
            RawTelemetryEvent.objects.bulk_create(rows)
        except Exception:
            logger.exception("Telemetry spool insert failed")

    # Self-healing valve: if the processor (cron) isn't keeping up, drain a
    # little inline. Sampled (~3%) so it adds no per-request cost normally.
    if random.random() < 0.03:
        try:
            if unprocessed_backlog() > BACKLOG_VALVE_THRESHOLD:
                process_spool(batch_size=200)
        except Exception:
            logger.exception("Inline telemetry drain failed")

    return JsonResponse({"status": "received"})


@api_view(["GET"])
@permission_classes([IsManagerOrAbove])
def analytics_overview(request):
    """
    GET /api/v1/analytics/overview/
    KPI cards for the ERP dashboard header.
    """
    from apps.crm.models import Lead, LeadStatus, Client
    from apps.transactions.models import Transaction, TransactionStatus
    from apps.properties.models import Property

    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    prev_period_start = thirty_days_ago - timedelta(days=30)

    # --- Leads ---
    new_leads_this_month = Lead.objects.filter(created_at__gte=thirty_days_ago).count()
    new_leads_prev_month = Lead.objects.filter(
        created_at__gte=prev_period_start, created_at__lt=thirty_days_ago
    ).count()

    # --- Revenue ---
    completed_txns = Transaction.objects.filter(status=TransactionStatus.COMPLETED)
    revenue_this_month = (
        completed_txns.filter(completed_at__gte=thirty_days_ago)
        .aggregate(total=Sum("agreed_price"))["total"] or 0
    )
    revenue_prev_month = (
        completed_txns.filter(
            completed_at__gte=prev_period_start, completed_at__lt=thirty_days_ago
        )
        .aggregate(total=Sum("agreed_price"))["total"] or 0
    )
    commission_this_month = (
        completed_txns.filter(completed_at__gte=thirty_days_ago)
        .aggregate(total=Sum("commission_amount"))["total"] or 0
    )

    # --- Pipeline counts ---
    pipeline_counts = dict(
        Lead.objects.values("status").annotate(count=Count("id")).values_list("status", "count")
    )

    # --- Properties ---
    active_listings = Property.objects.filter(is_published=True, status="available").count()

    # --- Conversions ---
    total_leads = Lead.objects.count()
    converted = Lead.objects.filter(status=LeadStatus.CONVERTED).count()
    conversion_rate = round((converted / total_leads * 100) if total_leads else 0, 1)

    def pct_change(current, previous):
        if previous == 0:
            return None
        return round((current - previous) / previous * 100, 1)

    return Response({
        "leads": {
            "this_month": new_leads_this_month,
            "change_pct": pct_change(new_leads_this_month, new_leads_prev_month),
        },
        "revenue": {
            "this_month": float(revenue_this_month),
            "prev_month": float(revenue_prev_month),
            "change_pct": pct_change(revenue_this_month, revenue_prev_month),
        },
        "commission": {
            "this_month": float(commission_this_month),
        },
        "pipeline": pipeline_counts,
        "active_listings": active_listings,
        "conversion_rate": conversion_rate,
    })


@api_view(["GET"])
@permission_classes([IsManagerOrAbove])
def analytics_pipeline(request):
    """
    GET /api/v1/analytics/pipeline/
    Lead funnel metrics — counts and conversion rates between stages.
    """
    from apps.crm.models import Lead, LeadStatus
    from django.db.models import Count

    counts = {
        row["status"]: row["count"]
        for row in Lead.objects.values("status").annotate(count=Count("id"))
    }

    stages = [s[0] for s in LeadStatus.choices]
    funnel = []
    for i, stage in enumerate(stages):
        count = counts.get(stage, 0)
        prev_count = funnel[i - 1]["count"] if i > 0 else count
        funnel.append({
            "stage": stage,
            "label": LeadStatus(stage).label,
            "count": count,
            "drop_off_pct": round((1 - count / prev_count) * 100, 1) if prev_count > 0 and i > 0 else 0,
        })

    return Response({"funnel": funnel, "total_leads": sum(counts.values())})


@api_view(["GET"])
@permission_classes([IsManagerOrAbove])
def analytics_revenue(request):
    """
    GET /api/v1/analytics/revenue/?months=12
    Monthly revenue breakdown, optionally filtered by agent.
    """
    from apps.transactions.models import Transaction, TransactionStatus
    from django.db.models.functions import TruncMonth

    months = int(request.query_params.get("months", 12))
    agent_id = request.query_params.get("agent_id")

    cutoff = timezone.now() - timedelta(days=30 * months)

    qs = Transaction.objects.filter(
        status=TransactionStatus.COMPLETED,
        completed_at__gte=cutoff,
    )

    if agent_id:
        qs = qs.filter(agent_id=agent_id)

    monthly = (
        qs.annotate(month=TruncMonth("completed_at"))
        .values("month")
        .annotate(
            revenue=Sum("agreed_price"),
            commission=Sum("commission_amount"),
            deals=Count("id"),
        )
        .order_by("month")
    )

    return Response({
        "months": [
            {
                "month": row["month"].strftime("%Y-%m"),
                "revenue": float(row["revenue"]),
                "commission": float(row["commission"]),
                "deals": row["deals"],
            }
            for row in monthly
        ]
    })
