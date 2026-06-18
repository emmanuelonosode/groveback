from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
from datetime import timedelta
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.http import JsonResponse
from .models import Visitor, VisitorSession, PageVisit, TelemetryEvent

from apps.accounts.permissions import IsManagerOrAbove


@api_view(["POST"])
@permission_classes([AllowAny])
def visitor_session(request):
    """
    POST /api/v1/analytics/visitors/
    Silently captures anonymous visitor context on first page interaction.
    Uses session_id to deduplicate — safe to call multiple times.
    """
    payload = request.data.copy()
    
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return Response({"detail": "session_id required."}, status=400)

    # Capture the real IP server-side
    ip = (
        request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        or request.META.get("HTTP_X_REAL_IP", "")
        or request.META.get("REMOTE_ADDR", "")
    ) or None

    payload["ip_address"] = ip
    payload["timestamp"] = timezone.now().isoformat()
    
    # If a user is logged in, attach their ID for mapping
    if request.user and request.user.is_authenticated:
        payload["user_id"] = request.user.id

    # Process synchronously
    process_single_payload(payload)

    return JsonResponse({"status": "received"})


def process_single_payload(data: dict):
    fingerprint = data.get("fingerprint_id")
    if not fingerprint:
        return
        
    user_id = data.get("user_id")
    
    visitor, _ = Visitor.objects.get_or_create(fingerprint_id=fingerprint)
    if user_id and not visitor.user_id:
        visitor.user_id = user_id
        visitor.save(update_fields=["user_id"])
        
    session_id = data.get("session_id")
    if not session_id:
        return
        
    session, created = VisitorSession.objects.get_or_create(
        session_id=session_id,
        defaults={
            "visitor": visitor,
            "ip_address": data.get("ip_address"),
            "city": data.get("city", ""),
            "region": data.get("region", ""),
            "country_code": data.get("country_code", ""),
            "browser": data.get("browser", ""),
            "os": data.get("os", ""),
            "device_type": data.get("device_type", ""),
            "screen": data.get("screen", ""),
            "language": data.get("language", ""),
            "timezone": data.get("timezone", ""),
            "landing_page": data.get("landing_page", ""),
            "referrer": data.get("referrer", ""),
            "utm_source": data.get("utm_source", ""),
            "utm_medium": data.get("utm_medium", ""),
            "utm_campaign": data.get("utm_campaign", ""),
            "referral_code": data.get("referral_code", ""),
        }
    )
    
    if not created and visitor != session.visitor:
        session.visitor = visitor
        session.save(update_fields=["visitor"])

    event_type = data.get("event_type")
    
    # Handle end session
    if event_type == "session_end":
        session.end_time = data.get("timestamp")
        session.total_dwell_time = data.get("dwell_time", 0.0)
        session.save(update_fields=["end_time", "total_dwell_time"])
        
    # Handle page visits
    path = data.get("path")
    if path and event_type == "page_view":
        PageVisit.objects.create(
            session=session,
            path=path,
            entry_time=data.get("timestamp")
        )
        
    # Handle engagement updates
    if event_type == "engagement" and path:
        visit = PageVisit.objects.filter(session=session, path=path).order_by("-entry_time").first()
        if visit:
            if "max_scroll_depth" in data:
                visit.max_scroll_depth = max(visit.max_scroll_depth, data["max_scroll_depth"])
            if "idle_time" in data:
                visit.idle_time = data["idle_time"]
            visit.save(update_fields=["max_scroll_depth", "idle_time"])
            
    # Handle arbitrary events (clicks, etc.)
    if event_type not in ["session_end", "page_view", "engagement", "init", None]:
        visit = None
        if path:
            visit = PageVisit.objects.filter(session=session, path=path).order_by("-entry_time").first()
            
        TelemetryEvent.objects.create(
            session=session,
            page_visit=visit,
            event_type=event_type,
            event_data=data.get("event_data", {}),
        )


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
