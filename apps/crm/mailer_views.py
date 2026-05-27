"""
Mailer Sync API views for Hasker Mail Sender integration.

Endpoints:
  GET  /api/v1/mailer/contacts/   — Export contacts (Leads + Clients + Portal Users) as JSON
  POST /api/v1/mailer/webhook/    — Receive email tracking events from the Mailer
"""

import hmac
import logging

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def _verify_mailer_key(request):
    """Validate the X-Mailer-Key header against MAILER_SYNC_KEY in settings."""
    key = getattr(settings, "MAILER_SYNC_KEY", None)
    if not key:
        logger.error("MAILER_SYNC_KEY is not configured in settings.")
        return False
    provided = request.headers.get("X-Mailer-Key", "")
    # Constant-time comparison to avoid timing attacks
    return hmac.compare_digest(provided, key)


def _build_contact(email, name, phone="", tags=None, source=None, budget_min=None, budget_max=None, location=None):
    """Build a standardised contact dict for the Mailer."""
    return {
        "email": (email or "").lower().strip(),
        "name": (name or "").strip(),
        "phone": phone or "",
        "tags": list(set(tags or [])),
        "notes": f"Source: {source}" if source else "",
        "budget_min": str(budget_min) if budget_min else None,
        "budget_max": str(budget_max) if budget_max else None,
        "preferred_location": location or "",
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def mailer_contacts(request):
    """
    GET /api/v1/mailer/contacts/
    Exports a combined contact list of Leads, Clients, and Portal Users for the Hasker Mailer.

    Query params:
      - page         (int, default 1)
      - page_size    (int, default 500, max 1000)
      - updated_since (ISO datetime — only return contacts updated after this date)
      - type         (all | leads | clients | users — filter by contact source)
    """
    if not _verify_mailer_key(request):
        return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    page = max(1, int(request.GET.get("page", 1)))
    page_size = min(1000, max(1, int(request.GET.get("page_size", 500))))
    updated_since = request.GET.get("updated_since")
    contact_type = request.GET.get("type", "all")

    since_dt = None
    if updated_since:
        since_dt = parse_datetime(updated_since)

    contacts = {}  # keyed by email to deduplicate

    # ── 1. Leads ─────────────────────────────────────────────────────────────
    if contact_type in ("all", "leads"):
        from apps.crm.models import Lead, InterestType, LeadStatus

        INTEREST_TAG_MAP = {
            InterestType.BUY: "Buyer",
            InterestType.RENT: "Renter",
            InterestType.SELL: "Seller",
            InterestType.INVEST: "Investor",
        }

        lead_qs = Lead.objects.exclude(email="")
        
        if since_dt:
            lead_qs = lead_qs.filter(updated_at__gte=since_dt)

        for lead in lead_qs.iterator():
            tags = ["Lead"]
            interest_tag = INTEREST_TAG_MAP.get(lead.interest_type)
            if interest_tag:
                tags.append(interest_tag)
            # Map lead status to useful campaign tags
            if lead.status == LeadStatus.QUALIFIED:
                tags.append("Qualified")
            elif lead.status == LeadStatus.NEGOTIATING:
                tags.append("Negotiating")
            elif lead.status == LeadStatus.CONVERTED:
                tags.append("Client")
            elif lead.status == LeadStatus.LOST:
                tags.append("Cold")

            contacts[lead.email.lower()] = _build_contact(
                email=lead.email,
                name=lead.full_name,
                phone=lead.phone,
                tags=tags,
                source=lead.source,
                budget_min=lead.budget_min,
                budget_max=lead.budget_max,
                location=lead.preferred_location,
            )

    # ── 2. Portal Users (role=CLIENT) ─────────────────────────────────────────
    if contact_type in ("all", "users"):
        from apps.accounts.models import CustomUser, Role

        user_qs = CustomUser.objects.filter(
            role=Role.CLIENT, is_active=True, is_email_verified=True
        ).exclude(email="")
        if since_dt:
            user_qs = user_qs.filter(date_joined__gte=since_dt)

        for user in user_qs.iterator():
            tags = ["Portal User", "Verified"]
            # Preferences-based tags
            prefs = user.preferences or {}
            intent = prefs.get("intent", "")
            if intent == "rent":
                tags.append("Renter")
            elif intent == "buy":
                tags.append("Buyer")

            existing = contacts.get(user.email.lower())
            if existing:
                # Merge: portal user = verified lead, keep merged tags
                existing["tags"] = list(set(existing["tags"] + tags))
            else:
                contacts[user.email.lower()] = _build_contact(
                    email=user.email,
                    name=user.full_name,
                    tags=tags,
                )

    # ── 3. Clients ────────────────────────────────────────────────────────────
    if contact_type in ("all", "clients"):
        from apps.crm.models import Client

        client_qs = Client.objects.select_related("lead").exclude(lead__email="")
            
        if since_dt:
            client_qs = client_qs.filter(created_at__gte=since_dt)

        for client in client_qs.iterator():
            email = client.lead.email.lower().strip()
            tags = ["Client", "Tenant"]
            existing = contacts.get(email)
            if existing:
                existing["tags"] = list(set(existing["tags"] + tags))
            else:
                contacts[email] = _build_contact(
                    email=client.lead.email,
                    name=client.lead.full_name,
                    tags=tags,
                )

    # ── Paginate ──────────────────────────────────────────────────────────────
    all_contacts = list(contacts.values())
    total = len(all_contacts)
    start = (page - 1) * page_size
    end = start + page_size
    page_data = all_contacts[start:end]

    return Response({
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": end < total,
        "contacts": page_data,
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def mailer_webhook(request):
    """
    POST /api/v1/mailer/webhook/
    Receives email engagement events from the Hasker Mailer and logs them
    as LeadActivity records in the Hargrove CRM.

    Body: { event: "email_opened"|"link_clicked", email, campaignId, url?, timestamp }
    """
    if not _verify_mailer_key(request):
        return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    event = request.data.get("event")
    email = (request.data.get("email") or "").lower().strip()
    campaign_id = request.data.get("campaignId", "")
    url = request.data.get("url", "")

    if not event or not email:
        return Response({"error": "Missing event or email"}, status=status.HTTP_400_BAD_REQUEST)

    if event not in ("email_opened", "link_clicked"):
        return Response({"error": "Unknown event"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        from apps.crm.models import Lead, LeadActivity
        from apps.accounts.models import CustomUser

        # Try to find a matching Lead
        lead = Lead.objects.filter(email__iexact=email).order_by("-created_at").first()
        if not lead:
            return Response({"status": "ignored", "reason": "No matching lead found"})

        # Find a staff user to attribute the activity to (use first admin/manager)
        agent = CustomUser.objects.filter(
            is_staff=True, is_active=True
        ).first()
        if not agent:
            return Response({"status": "ignored", "reason": "No staff user found"})

        activity_type = "EMAIL"
        if event == "email_opened":
            note = f"[Mailer] Email opened. Campaign: {campaign_id}"
        else:
            note = f"[Mailer] Link clicked: {url}. Campaign: {campaign_id}"

        LeadActivity.objects.create(
            lead=lead,
            agent=agent,
            activity_type=activity_type,
            note=note,
        )

        logger.info("Mailer webhook: %s event logged for lead %s", event, lead.id)
        return Response({"status": "ok", "lead_id": lead.id})

    except Exception as e:
        logger.error("Mailer webhook error: %s", e)
        return Response({"error": "Internal error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@permission_classes([AllowAny])
def mailer_optout_sync(request):
    """
    POST /api/v1/mailer/optout/
    Receive opt-out notifications from the Mailer and mark the matching Lead
    as email_marketing_opted_out=True.

    Body: { email: "user@example.com" }
    """
    if not _verify_mailer_key(request):
        return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    email = (request.data.get("email") or "").lower().strip()
    if not email:
        return Response({"error": "Missing email"}, status=status.HTTP_400_BAD_REQUEST)

    updated = 0
    try:
        from apps.crm.models import Lead
        updated = Lead.objects.filter(email__iexact=email).update(
            drip_opted_out=True,
        )
        logger.info("Mailer opt-out: %d leads updated for email %s", updated, email)
    except Exception as e:
        logger.error("Mailer opt-out error: %s", e)

    return Response({"status": "ok", "updated": updated})
