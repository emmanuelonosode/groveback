import logging

from rest_framework import serializers

from apps.properties.models import Property
from .models import Viewing, TourRequest

logger = logging.getLogger(__name__)


class ViewingSerializer(serializers.ModelSerializer):
    lead_name = serializers.CharField(source="lead.full_name", read_only=True)
    property_title = serializers.CharField(source="property.title", read_only=True)
    property_address = serializers.CharField(source="property.address", read_only=True)
    agent_name = serializers.CharField(source="agent.full_name", read_only=True)

    class Meta:
        model = Viewing
        fields = [
            "id", "lead", "lead_name",
            "property", "property_title", "property_address",
            "agent", "agent_name",
            "scheduled_at", "status", "notes", "reminder_sent",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "reminder_sent", "created_at", "updated_at"]


class TourRequestCreateSerializer(serializers.ModelSerializer):
    """
    Public: captures the lead immediately (step 1) and creates the tour request.
    ID upload + admin approval happen afterward, so a lead is never lost.
    """
    property = serializers.PrimaryKeyRelatedField(queryset=Property.objects.all())

    class Meta:
        model = TourRequest
        fields = [
            "id", "public_id", "property", "full_name", "email", "phone",
            "preferred_date", "preferred_time", "tour_type", "notes", "status",
        ]
        read_only_fields = ["id", "public_id", "status"]

    def create(self, validated_data):
        prop = validated_data["property"]

        # 1) Capture the lead right away (low friction — never lose the inquiry).
        lead = None
        try:
            from apps.crm.models import Lead, LeadSource
            interest = "RENT" if getattr(prop, "listing_type", "") == "for-rent" else "BUY"
            parts = [
                f"Self-tour request for {prop.title}.",
                f"Preferred date: {validated_data.get('preferred_date') or 'flexible'}",
                f"Preferred time: {validated_data.get('preferred_time') or 'flexible'}",
            ]
            if validated_data.get("notes"):
                parts.append(f"Note: {validated_data['notes']}")
            lead = Lead.objects.create(
                full_name=validated_data["full_name"],
                email=(validated_data.get("email") or ""),
                phone=(validated_data.get("phone") or ""),
                source=LeadSource.PROPERTY_INQUIRY,
                interest_type=interest,
                property_interest=prop,
                detected_city=getattr(prop, "city", "") or "",
                message="\n".join(parts),
            )
        except Exception:
            logger.exception("Tour request: lead capture failed")

        tour = TourRequest.objects.create(lead=lead, **validated_data)

        # 2) Alert staff now — this is a real inquiry, regardless of ID step.
        if lead is not None:
            try:
                from apps.notifications.tasks import send_lead_notification
                send_lead_notification(lead.id)
            except Exception:
                logger.exception("Tour request: lead notification failed")
        try:
            from apps.notifications.tasks import send_admin_alert
            send_admin_alert(f"New Tour Request — {tour.full_name}", [
                ("Property", prop.title),
                ("Preferred date", str(validated_data.get("preferred_date") or "Flexible")),
                ("Preferred time", validated_data.get("preferred_time") or "Flexible"),
                ("Phone", validated_data.get("phone") or "—"),
                ("Email", validated_data.get("email") or "—"),
                ("Status", "Awaiting ID upload"),
            ])
        except Exception:
            logger.exception("Tour request: admin alert failed")

        return tour
