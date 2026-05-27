"""
Django signals for the CRM app.
Fires real-time webhook events to the Hasker Mailer when key CRM events occur,
so the Mailer can automatically tag contacts and enroll them in drip sequences.
"""

import logging
import threading
from typing import Optional

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _fire_mailer_webhook(event: str, email: str, name: str = "", phone: str = "", tags: Optional[list] = None, property_slug: Optional[str] = None, source: str = "", message: str = ""):
    """
    Fire a webhook to the Hasker Mailer in a background thread.
    Never blocks the main Django request.
    """
    def _send():
        try:
            from django.conf import settings
            import urllib.request
            import json

            mailer_url = getattr(settings, "MAILER_APP_URL", "").rstrip("/")
            mailer_key = getattr(settings, "MAILER_SYNC_KEY", "")

            if not mailer_url or not mailer_key:
                return  # Not configured — skip silently

            data_dict = {
                "event": event,
                "email": email,
                "name": name,
                "phone": phone or "",
                "tags": tags or [],
                "source": source or "",
                "message": message or "",
            }
            if property_slug:
                data_dict["property_slug"] = property_slug

            payload = json.dumps(data_dict).encode("utf-8")

            req = urllib.request.Request(
                f"{mailer_url}/api/hargrove-webhook",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Mailer-Key": mailer_key,
                },
                method="POST",
            )
            # 5 second timeout — fire and forget
            with urllib.request.urlopen(req, timeout=5) as resp:
                logger.info("Mailer webhook '%s' fired for %s → %s", event, email, resp.status)

        except Exception as e:
            logger.warning("Mailer webhook failed for event '%s' (%s): %s", event, email, e)
            # Never raise — signals must not break user-facing requests

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()


# ── Signal: New Lead created ───────────────────────────────────────────────────
# NOTE: Cannot use @receiver(post_save, sender="crm.Lead") string form —
# Django only resolves string senders for the contrib.auth swappable model.
# We connect manually in ready() using the actual model class.
def on_lead_save(sender, instance, created, **kwargs):
    from apps.crm.models import LeadStatus, InterestType

    # Guard: field may not exist yet if migration hasn't run
    opted_out = getattr(instance, "email_marketing_opted_out", False)
    if opted_out:
        return  # Respect opt-out

    INTEREST_TAG = {
        InterestType.BUY: "Buyer",
        InterestType.RENT: "Renter",
        InterestType.SELL: "Seller",
        InterestType.INVEST: "Investor",
    }

    if created:
        tags = ["Lead"]
        interest_tag = INTEREST_TAG.get(instance.interest_type)
        if interest_tag:
            tags.append(interest_tag)

        # ── Admin alert: new inquiry received ────────────────────────────────
        def _alert_inquiry():
            try:
                from apps.notifications.tasks import send_admin_alert
                rows = [
                    ("Name",     instance.full_name),
                    ("Email",    instance.email),
                    ("Phone",    instance.phone or "—"),
                    ("Interest", instance.get_interest_type_display()),
                    ("Source",   instance.get_source_display()),
                ]
                if instance.property_interest:
                    rows.append(("Property", str(instance.property_interest)))
                if instance.message:
                    rows.append(("Message", (instance.message[:200] + "…") if len(instance.message) > 200 else instance.message))
                send_admin_alert(f"New Inquiry — {instance.full_name}", rows)
            except Exception as e:
                logger.warning("Admin inquiry alert failed: %s", e)
        threading.Thread(target=_alert_inquiry, daemon=True).start()

        if instance.property_interest_id and instance.property_interest:
            tags.append("Property Inquiry")
            _fire_mailer_webhook(
                event="property_inquiry",
                email=instance.email,
                name=instance.full_name,
                phone=instance.phone,
                tags=tags,
                property_slug=instance.property_interest.slug,
                source=instance.source or "",
                message=instance.message or ""
            )
        else:
            _fire_mailer_webhook(
                event="new_lead",
                email=instance.email,
                name=instance.full_name,
                phone=instance.phone,
                tags=tags,
                source=instance.source or "",
                message=instance.message or ""
            )
    else:
        # Lead status changed to QUALIFIED — trigger qualification drip
        if instance.status == LeadStatus.QUALIFIED:
            _fire_mailer_webhook(
                event="lead_qualified",
                email=instance.email,
                name=instance.full_name,
                phone=instance.phone,
                tags=["Lead", "Qualified"],
                source=instance.source or "",
                message=instance.message or ""
            )
        elif instance.status == LeadStatus.CONVERTED:
            _fire_mailer_webhook(
                event="lead_converted",
                email=instance.email,
                name=instance.full_name,
                phone=instance.phone,
                tags=["Client"],
                source=instance.source or "",
                message=instance.message or ""
            )


# ── Signal: Rental Application submitted ──────────────────────────────────────
def on_application_save(sender, instance, created, **kwargs):
    from apps.crm.models import ApplicationStatus

    if created and instance.status == ApplicationStatus.SUBMITTED:
        _fire_mailer_webhook(
            event="application_submitted",
            email=instance.email,
            name=instance.full_name,
            tags=["Applicant"],
        )
    elif not created and instance.status == ApplicationStatus.APPROVED:
        _fire_mailer_webhook(
            event="application_approved",
            email=instance.email,
            name=instance.full_name,
            tags=["Applicant", "Approved Tenant"],
        )


# ── Signal: New verified portal user ──────────────────────────────────────────
def on_user_verified(sender, instance, created, **kwargs):
    from apps.accounts.models import Role

    if instance.role != Role.CLIENT:
        return  # Only sync client users

    if not created and instance.is_email_verified:
        # User just got verified (update, not create)
        _fire_mailer_webhook(
            event="new_portal_user",
            email=instance.email,
            name=instance.full_name,
            tags=["Portal User", "Verified"],
        )


def connect_signals():
    """
    Connect all signal handlers using the real model classes.
    Called from CrmConfig.ready() after all models are loaded.
    Using post_save.connect() here (instead of @receiver with a string sender)
    because Django only supports string senders for the swappable AUTH_USER_MODEL.
    """
    from apps.crm.models import Lead, RentalApplication
    from apps.accounts.models import CustomUser

    post_save.connect(on_lead_save, sender=Lead)
    post_save.connect(on_application_save, sender=RentalApplication)
    post_save.connect(on_user_verified, sender=CustomUser)
