from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
from datetime import timedelta
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.accounts.permissions import IsManagerOrAbove


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
