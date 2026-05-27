"""
Email functions for Hasker & Co. Realty Group.

All functions run synchronously — no Celery worker required.
For scheduled tasks (weekly_lead_followup, etc.) wire them up as
cPanel cron jobs via a management command if needed.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _get_email_sender():
    """
    Returns (from_header, connection) using the active EmailConfiguration
    stored in the database.  Falls back to Django settings if none is configured.
    """
    try:
        from apps.notifications.models import EmailConfiguration
        config = EmailConfiguration.get_active()
        if config:
            return config.get_from_header(), config.get_connection()
    except Exception:
        pass
    return settings.DEFAULT_FROM_EMAIL, None


# ---------------------------------------------------------------------------
# Lead notifications
# ---------------------------------------------------------------------------

def send_lead_notification(lead_id: int):
    """Email the assigned agent (or all managers) when a new lead is created."""
    try:
        from apps.crm.models import Lead
        from apps.accounts.models import CustomUser, Role

        lead = Lead.objects.select_related("assigned_agent", "property_interest").get(pk=lead_id)

        if lead.assigned_agent:
            recipients = [lead.assigned_agent.email]
        else:
            recipients = list(
                CustomUser.objects.filter(role=Role.MANAGER, is_active=True).values_list("email", flat=True)
            )

        if not recipients:
            return "No recipients — skipped."

        from_header, connection = _get_email_sender()
        subject = f"New Lead: {lead.full_name} ({lead.get_source_display()})"
        body = render_to_string("notifications/lead_notification.txt", {"lead": lead})

        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_header,
            to=recipients,
            connection=connection,
        )
        msg.send()
        return f"Notification sent to {recipients}"

    except Exception:
        logger.exception("send_lead_notification failed for lead %s", lead_id)
        raise


def send_verification_email(user_id: int):
    """Email the 6-digit OTP code to a newly registered user."""
    try:
        from apps.accounts.models import CustomUser

        user = CustomUser.objects.get(pk=user_id)
        if not user.email_verification_code:
            return "No OTP code set — skipped."

        from_header, connection = _get_email_sender()
        subject = f"{user.email_verification_code} is your Hasker & Co. verification code"

        body = render_to_string("notifications/email_verification.html", {
            "user": user,
            "frontend_url": settings.FRONTEND_URL,
        })

        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_header,
            to=[user.email],
            connection=connection,
        )
        msg.content_subtype = "html"
        msg.send()
        return f"Verification email sent to {user.email}"

    except Exception:
        logger.exception("send_verification_email failed for user %s", user_id)
        raise


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def generate_invoice_pdf(invoice_id: int):
    """Render invoice HTML → PDF via WeasyPrint → upload to Cloudinary."""
    try:
        from apps.transactions.models import Invoice
        import cloudinary.uploader
        from weasyprint import HTML
        import tempfile, os

        invoice = Invoice.objects.select_related(
            "transaction__client__lead",
            "transaction__property",
            "transaction__agent",
        ).get(pk=invoice_id)

        html_string = render_to_string("notifications/invoice_pdf.html", {"invoice": invoice})

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            HTML(string=html_string, base_url=settings.FRONTEND_URL).write_pdf(tmp.name)
            tmp_path = tmp.name

        result = cloudinary.uploader.upload(
            tmp_path,
            resource_type="raw",
            folder="hasker/invoices",
            public_id=f"invoice_{invoice.invoice_number}",
            overwrite=True,
        )
        os.unlink(tmp_path)

        Invoice.objects.filter(pk=invoice_id).update(pdf=result["secure_url"])
        return f"Invoice PDF generated: {result['secure_url']}"

    except Exception:
        logger.exception("generate_invoice_pdf failed for invoice %s", invoice_id)
        raise


def generate_payment_receipt(payment_id: int):
    """Generate a PDF receipt for a completed payment."""
    try:
        from apps.transactions.models import Payment
        import cloudinary.uploader
        from weasyprint import HTML
        import tempfile, os

        payment = Payment.objects.select_related(
            "transaction__client__lead",
            "transaction__property",
        ).get(pk=payment_id)

        html_string = render_to_string("notifications/receipt_pdf.html", {"payment": payment})

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            HTML(string=html_string, base_url=settings.FRONTEND_URL).write_pdf(tmp.name)
            tmp_path = tmp.name

        result = cloudinary.uploader.upload(
            tmp_path,
            resource_type="raw",
            folder="hasker/receipts",
            public_id=f"receipt_payment_{payment.pk}",
            overwrite=True,
        )
        os.unlink(tmp_path)

        Payment.objects.filter(pk=payment_id).update(receipt_pdf=result["secure_url"])
        return f"Receipt PDF generated: {result['secure_url']}"

    except Exception:
        logger.exception("generate_payment_receipt failed for payment %s", payment_id)
        raise


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------

def send_invoice_email(invoice_id: int):
    """Email the invoice PDF to the client."""
    try:
        from apps.transactions.models import Invoice
        import urllib.request

        invoice = Invoice.objects.select_related(
            "transaction__client__lead",
            "user",
        ).get(pk=invoice_id)

        if invoice.user:
            client_email = invoice.user.email
            client_name = invoice.user.full_name
        elif invoice.transaction and invoice.transaction.client:
            client_email = invoice.transaction.client.email
            client_name = invoice.transaction.client.full_name
        else:
            return "No recipient found — skipped."

        from_header, connection = _get_email_sender()
        subject = f"Invoice {invoice.invoice_number}: {invoice.title}"
        body = render_to_string("notifications/invoice_email.html", {
            "invoice": invoice,
            "client_name": client_name,
            "frontend_url": settings.FRONTEND_URL,
        })

        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_header,
            to=[client_email],
            connection=connection,
        )
        msg.content_subtype = "html"

        if invoice.pdf:
            try:
                pdf_data = urllib.request.urlopen(invoice.pdf).read()
                msg.attach(f"{invoice.invoice_number}.pdf", pdf_data, "application/pdf")
            except Exception:
                pass

        msg.send()
        return f"Invoice emailed to {client_email}"

    except Exception:
        logger.exception("send_invoice_email failed for invoice %s", invoice_id)
        raise


# ---------------------------------------------------------------------------
# Careers / Job Applications
# ---------------------------------------------------------------------------

def send_job_application_notification(application_id: int):
    """
    1. Send confirmation email to the applicant.
    2. Send an alert with full details to careers@ and all active managers.
    """
    try:
        from apps.careers.models import JobApplication
        from apps.accounts.models import CustomUser, Role

        app = JobApplication.objects.get(pk=application_id)
        from_header, connection = _get_email_sender()

        confirmation_body = render_to_string(
            "notifications/job_application_confirmation.html", {"app": app}
        )
        msg_confirm = EmailMessage(
            subject=f"Application received — {app.role_title} | Hasker & Co. Realty Group",
            body=confirmation_body,
            from_email=from_header,
            to=[app.email],
            connection=connection,
        )
        msg_confirm.content_subtype = "html"
        msg_confirm.send()

        manager_emails = list(
            CustomUser.objects.filter(role=Role.MANAGER, is_active=True)
            .values_list("email", flat=True)
        )
        staff_recipients = list(set(manager_emails + ["careers@haskerrealtygroup.com"]))

        alert_body = render_to_string(
            "notifications/job_application_staff_alert.html", {"app": app}
        )
        msg_alert = EmailMessage(
            subject=f"New Job Application: {app.full_name} — {app.role_title}",
            body=alert_body,
            from_email=from_header,
            to=staff_recipients,
            connection=connection,
        )
        msg_alert.content_subtype = "html"
        msg_alert.send()

        return f"Job application notifications sent for application {application_id}"

    except Exception:
        logger.exception("send_job_application_notification failed for application %s", application_id)
        raise


def send_job_rejection_email(application_id: int):
    """Send a polite rejection email to an applicant."""
    try:
        from apps.careers.models import JobApplication

        app = JobApplication.objects.get(pk=application_id)
        from_header, connection = _get_email_sender()

        subject = f"Re: Your application for {app.role_title} — Hasker & Co. Realty Group"
        body = render_to_string(
            "notifications/job_application_rejection.html", {"app": app}
        )
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_header,
            to=[app.email],
            connection=connection,
        )
        msg.content_subtype = "html"
        msg.send()
        return f"Rejection email sent to {app.email}"

    except Exception:
        logger.exception("send_job_rejection_email failed for application %s", application_id)
        raise


def _payment_recipient(payment):
    """
    Resolve a payment to (email, full_name) across all three payment contexts:
    invoice (direct user), invoice (via transaction client), rental application, transaction.
    Returns None if no recipient can be determined.
    """
    if payment.invoice:
        if payment.invoice.user:
            return payment.invoice.user.email, payment.invoice.user.full_name
        if payment.invoice.transaction and payment.invoice.transaction.client:
            client = payment.invoice.transaction.client
            return client.lead.email, client.lead.full_name
    if payment.rental_application:
        return payment.rental_application.email, payment.rental_application.full_name
    if payment.transaction and payment.transaction.client:
        client = payment.transaction.client
        return client.lead.email, client.lead.full_name
    return None


def send_payment_submitted_email(payment_id: int):
    """Notify the user that their payment proof was received."""
    try:
        from apps.transactions.models import Payment

        payment = Payment.objects.select_related(
            "invoice__user",
            "invoice__transaction__client__lead",
            "rental_application",
            "transaction__client__lead",
        ).get(pk=payment_id)

        result = _payment_recipient(payment)
        if not result:
            return "No recipient found — skipped."
        recipient_email, recipient_name = result

        from_header, connection = _get_email_sender()
        subject = "Payment Received & Pending Verification — Hasker & Co."
        body = render_to_string("notifications/payment_submitted.html", {
            "payment": payment,
            "recipient_name": recipient_name,
            "frontend_url": settings.FRONTEND_URL,
        })

        msg = EmailMessage(subject=subject, body=body, from_email=from_header, to=[recipient_email], connection=connection)
        msg.content_subtype = "html"
        msg.send()
        return f"Payment confirmation sent to {recipient_email}"

    except Exception:
        logger.exception("send_payment_submitted_email failed for payment %s", payment_id)
        raise


def send_payment_verified_email(payment_id: int):
    """Notify the user that their payment has been verified."""
    try:
        from apps.transactions.models import Payment

        payment = Payment.objects.select_related(
            "invoice__user",
            "invoice__transaction__client__lead",
            "rental_application",
            "transaction__client__lead",
        ).get(pk=payment_id)

        result = _payment_recipient(payment)
        if not result:
            return "No recipient found — skipped."
        recipient_email, recipient_name = result

        from_header, connection = _get_email_sender()
        subject = "Payment Verified — Hasker & Co. Realty Group"
        body = render_to_string("notifications/payment_verified.html", {
            "payment": payment,
            "recipient_name": recipient_name,
            "frontend_url": settings.FRONTEND_URL,
        })

        msg = EmailMessage(subject=subject, body=body, from_email=from_header, to=[recipient_email], connection=connection)
        msg.content_subtype = "html"
        msg.send()
        return f"Payment verification sent to {recipient_email}"

    except Exception:
        logger.exception("send_payment_verified_email failed for payment %s", payment_id)
        raise


def send_payment_rejected_email(payment_id: int):
    """Notify the user that their payment proof was rejected."""
    try:
        from apps.transactions.models import Payment

        payment = Payment.objects.select_related(
            "invoice__user",
            "invoice__transaction__client__lead",
            "rental_application",
            "transaction__client__lead",
        ).get(pk=payment_id)

        result = _payment_recipient(payment)
        if not result:
            return "No recipient found — skipped."
        recipient_email, recipient_name = result

        from_header, connection = _get_email_sender()
        subject = "Action Required: Payment Proof Not Verified — Hasker & Co."
        body = render_to_string("notifications/payment_rejected.html", {
            "payment": payment,
            "recipient_name": recipient_name,
            "frontend_url": settings.FRONTEND_URL,
        })

        msg = EmailMessage(subject=subject, body=body, from_email=from_header, to=[recipient_email], connection=connection)
        msg.content_subtype = "html"
        msg.send()
        return f"Payment rejection notice sent to {recipient_email}"

    except Exception:
        logger.exception("send_payment_rejected_email failed for payment %s", payment_id)
        raise


# ---------------------------------------------------------------------------
# Viewing reminders
# ---------------------------------------------------------------------------

def send_viewing_reminder(viewing_id: int):
    """Send a 24h-before reminder to the lead (and the agent)."""
    try:
        from apps.scheduler.models import Viewing

        viewing = Viewing.objects.select_related("lead", "property", "agent").get(pk=viewing_id)

        from_header, connection = _get_email_sender()
        recipients = [viewing.lead.email, viewing.agent.email]
        subject = f"Viewing Reminder: {viewing.property.title} tomorrow"
        body = render_to_string("notifications/viewing_reminder.txt", {"viewing": viewing})

        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_header,
            to=recipients,
            connection=connection,
        )
        msg.send()

        Viewing.objects.filter(pk=viewing_id).update(reminder_sent=True)
        return f"Reminder sent for viewing #{viewing_id}"

    except Exception:
        logger.exception("send_viewing_reminder failed for viewing %s", viewing_id)
        raise


# ---------------------------------------------------------------------------
# Scheduled tasks — wire up as cPanel cron jobs if needed
# ---------------------------------------------------------------------------

def weekly_lead_followup():
    """
    Reminds agents of any leads they haven't contacted in 7+ days.
    Run via cPanel cron: every Monday at 8 AM.
    """
    from django.utils import timezone
    from datetime import timedelta
    from apps.crm.models import Lead, LeadStatus
    from apps.accounts.models import CustomUser, Role

    cutoff = timezone.now() - timedelta(days=7)
    stale_leads = (
        Lead.objects
        .filter(
            status__in=[LeadStatus.NEW, LeadStatus.CONTACTED, LeadStatus.QUALIFIED],
            last_contacted_at__lt=cutoff,
            assigned_agent__isnull=False,
        )
        .select_related("assigned_agent")
    )

    agent_leads: dict = {}
    for lead in stale_leads:
        agent = lead.assigned_agent
        agent_leads.setdefault(agent, []).append(lead)

    from_header, connection = _get_email_sender()
    for agent, leads in agent_leads.items():
        subject = f"Follow-up Reminder: {len(leads)} leads need your attention"
        body = render_to_string("notifications/weekly_followup.txt", {
            "agent": agent,
            "leads": leads,
        })
        EmailMessage(
            subject=subject,
            body=body,
            from_email=from_header,
            to=[agent.email],
            connection=connection,
        ).send()

    return f"Weekly follow-up sent for {len(agent_leads)} agents, {stale_leads.count()} leads."


def schedule_viewing_reminders():
    """
    Queues send_viewing_reminder for viewings starting in 20–26 hours.
    Run via cPanel cron: every hour.
    """
    from django.utils import timezone
    from datetime import timedelta
    from apps.scheduler.models import Viewing, ViewingStatus

    now = timezone.now()
    window_start = now + timedelta(hours=20)
    window_end = now + timedelta(hours=26)

    viewings = Viewing.objects.filter(
        scheduled_at__range=(window_start, window_end),
        status__in=[ViewingStatus.SCHEDULED, ViewingStatus.CONFIRMED],
        reminder_sent=False,
    )

    for viewing in viewings:
        send_viewing_reminder(viewing.pk)

    return f"Sent reminders for {viewings.count()} viewings."


# ---------------------------------------------------------------------------
# Tenant communication emails (admin-triggered)
# ---------------------------------------------------------------------------

def send_lead_acknowledgment_email(lead_id: int):
    """Send a branded inquiry acknowledgment email to the prospective tenant."""
    try:
        from apps.crm.models import Lead
        from apps.properties.models import Property

        lead = Lead.objects.select_related(
            "assigned_agent",
            "property_interest",
            "property_interest__agent",
        ).prefetch_related(
            "property_interest__images",
            "property_interest__amenities__category",
        ).get(pk=lead_id)

        prop = lead.property_interest

        # ── Main property images ───────────────────────────────────────────────
        prop_images = []
        prop_price_formatted = ""
        if prop:
            prop_price_formatted = f"{int(prop.price):,}" if prop.price else ""
            for img in prop.images.all()[:7]:
                try:
                    prop_images.append(str(img.image.url))
                except Exception:
                    pass

        # ── Amenities grouped by category ─────────────────────────────────────
        prop_amenities_grouped = []
        if prop:
            cat_map = {}
            for amenity in prop.amenities.select_related("category").all():
                cat_name = amenity.category.name if amenity.category else "Features"
                cat_map.setdefault(cat_name, []).append(amenity.name)
            prop_amenities_grouped = [
                {"category": cat, "amenities": items}
                for cat, items in cat_map.items()
            ]

        # ── Nearby available properties (same city, same listing type) ─────────
        nearby_props = []
        search_city = None
        if prop:
            search_city = prop.city
        elif lead.detected_city:
            search_city = lead.detected_city
        elif lead.preferred_location:
            search_city = lead.preferred_location.split(",")[0].strip()

        if search_city:
            nearby_qs = Property.objects.filter(
                city__icontains=search_city,
                status="available",
                is_published=True,
            ).prefetch_related("images")
            if prop:
                nearby_qs = nearby_qs.exclude(pk=prop.pk).filter(listing_type=prop.listing_type)
            elif lead.interest_type == "RENT":
                nearby_qs = nearby_qs.filter(listing_type="for-rent")
            for nearby in nearby_qs.order_by("-is_featured", "-created_at")[:3]:
                nearby_img = None
                first = nearby.images.first()
                if first:
                    try:
                        nearby_img = str(first.image.url)
                    except Exception:
                        pass
                nearby_props.append({
                    "title": nearby.title,
                    "slug": nearby.slug,
                    "address": nearby.address,
                    "city": nearby.city,
                    "state": nearby.state,
                    "price": f"{int(nearby.price):,}" if nearby.price else "",
                    "price_label": nearby.price_label,
                    "bedrooms": nearby.bedrooms,
                    "bathrooms": nearby.bathrooms,
                    "sqft": f"{nearby.sqft:,}" if nearby.sqft else "",
                    "listing_type": nearby.listing_type,
                    "neighborhood": nearby.neighborhood,
                    "image": nearby_img,
                })

        subject = (
            f"{prop.title} is Available — Hasker & Co. Realty Group"
            if prop else
            "We received your inquiry — Hasker & Co. Realty Group"
        )

        from_header, connection = _get_email_sender()

        body = render_to_string("notifications/inquiry_acknowledgment.html", {
            "lead": lead,
            "prop": prop,
            "prop_images": prop_images,
            "prop_price_formatted": prop_price_formatted,
            "prop_amenities_grouped": prop_amenities_grouped,
            "nearby_props": nearby_props,
            "search_city": search_city,
            "frontend_url": settings.FRONTEND_URL,
        })

        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_header,
            to=[lead.email],
            connection=connection,
        )
        msg.content_subtype = "html"
        msg.send()

        return f"Acknowledgment email sent to {lead.email}"

    except Exception:
        logger.exception("send_lead_acknowledgment_email failed for lead %s", lead_id)
        raise


def send_application_approved_email(application_id: int):
    """Send branded approval email with legitimate next steps to the applicant."""
    try:
        from apps.crm.models import RentalApplication

        app = RentalApplication.objects.select_related(
            "rental_property", "rental_property__agent",
        ).get(pk=application_id)

        from_header, connection = _get_email_sender()
        subject = "Congratulations — Your Application Has Been Approved"
        if app.rental_property:
            subject = f"Congratulations — Your Application for {app.rental_property.title} Has Been Approved"

        body = render_to_string("notifications/application_approved.html", {
            "app": app,
            "frontend_url": settings.FRONTEND_URL,
        })

        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_header,
            to=[app.email],
            connection=connection,
        )
        msg.content_subtype = "html"
        msg.send()
        return f"Approval email sent to {app.email}"

    except Exception:
        logger.exception("send_application_approved_email failed for application %s", application_id)
        raise


def send_application_rejected_email(application_id: int):
    """Send polite rejection email with link to other listings."""
    try:
        from apps.crm.models import RentalApplication

        app = RentalApplication.objects.select_related("rental_property").get(pk=application_id)

        from_header, connection = _get_email_sender()
        subject = "Update on Your Application — Hasker & Co. Realty Group"
        body = render_to_string("notifications/application_rejected.html", {
            "app": app,
            "frontend_url": settings.FRONTEND_URL,
        })

        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_header,
            to=[app.email],
            connection=connection,
        )
        msg.content_subtype = "html"
        msg.send()
        return f"Rejection email sent to {app.email}"

    except Exception:
        logger.exception("send_application_rejected_email failed for application %s", application_id)
        raise


def send_move_in_instructions_email(application_id: int):
    """Send move-in instructions email with in-person key handover details."""
    try:
        from apps.crm.models import RentalApplication

        app = RentalApplication.objects.select_related(
            "rental_property", "rental_property__agent",
        ).get(pk=application_id)

        from_header, connection = _get_email_sender()
        property_title = app.rental_property.title if app.rental_property else "Your New Home"
        subject = f"Your Move-In Instructions — {property_title}"
        body = render_to_string("notifications/move_in_instructions.html", {
            "app": app,
            "frontend_url": settings.FRONTEND_URL,
        })

        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_header,
            to=[app.email],
            connection=connection,
        )
        msg.content_subtype = "html"
        msg.send()
        return f"Move-in instructions sent to {app.email}"

    except Exception:
        logger.exception("send_move_in_instructions_email failed for application %s", application_id)
        raise


def send_application_under_review_email(application_id: int):
    """Notify the applicant that their application is now being actively reviewed."""
    try:
        from apps.crm.models import RentalApplication

        app = RentalApplication.objects.select_related("rental_property").get(pk=application_id)

        from_header, connection = _get_email_sender()
        subject = "Your Application Is Under Review — Hasker & Co. Realty Group"
        body = render_to_string("notifications/application_under_review.html", {
            "app": app,
            "frontend_url": settings.FRONTEND_URL,
        })

        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_header,
            to=[app.email],
            connection=connection,
        )
        msg.content_subtype = "html"
        msg.send()
        return f"Under-review email sent to {app.email}"

    except Exception:
        logger.exception("send_application_under_review_email failed for application %s", application_id)
        raise


def send_application_submitted_email(application_id: int):
    """Send an immediate HTML confirmation to the applicant when their application is received."""
    try:
        from apps.crm.models import RentalApplication

        app = RentalApplication.objects.select_related("rental_property").get(pk=application_id)

        from_header, connection = _get_email_sender()
        subject = "Your Application Has Been Received — Hasker & Co. Realty Group"
        body = render_to_string("notifications/application_submitted.html", {
            "app": app,
            "frontend_url": settings.FRONTEND_URL,
        })

        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_header,
            to=[app.email],
            connection=connection,
        )
        msg.content_subtype = "html"
        msg.send()
        return f"Application confirmation sent to {app.email}"

    except Exception:
        logger.exception("send_application_submitted_email failed for application %s", application_id)
        raise


def generate_rental_application_pdf(application_id: int):
    """Render rental application → WeasyPrint PDF → Cloudinary → email applicant + agent."""
    try:
        import tempfile
        import os
        import cloudinary.uploader
        from weasyprint import HTML
        from apps.crm.models import RentalApplication

        app = RentalApplication.objects.select_related(
            "rental_property", "rental_property__agent", "lead",
        ).get(pk=application_id)

        html_string = render_to_string(
            "notifications/rental_application_pdf.html",
            {"app": app},
        )

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            HTML(string=html_string).write_pdf(tmp.name)
            tmp_path = tmp.name

        result = cloudinary.uploader.upload(
            tmp_path,
            resource_type="raw",
            folder="hasker/rental_applications",
            public_id=f"application_{app.pk}_{app.last_name.lower()}",
            overwrite=True,
        )
        os.unlink(tmp_path)

        RentalApplication.objects.filter(pk=application_id).update(
            application_pdf=result["secure_url"]
        )

        _send_rental_application_emails(app, result["secure_url"])
        return f"Rental application PDF generated: {result['secure_url']}"

    except Exception:
        logger.exception("generate_rental_application_pdf failed for application %s", application_id)
        raise


def _send_rental_application_emails(app, pdf_url: str):
    """Email PDF + notification to the property agent/managers after PDF generation."""
    try:
        import urllib.request
        pdf_data = urllib.request.urlopen(pdf_url).read()
    except Exception:
        pdf_data = None

    from_header, connection = _get_email_sender()

    if app.rental_property and app.rental_property.agent:
        agent_recipients = [app.rental_property.agent.email]
    else:
        from apps.accounts.models import CustomUser, Role
        agent_recipients = list(
            CustomUser.objects.filter(role=Role.MANAGER, is_active=True).values_list("email", flat=True)
        )

    if agent_recipients:
        admin_url = getattr(settings, "BACKEND_ADMIN_URL", settings.FRONTEND_URL)
        agent_body = render_to_string(
            "notifications/rental_application_agent_email.txt",
            {"app": app, "admin_url": admin_url},
        )
        prop_title = app.rental_property.title if app.rental_property else "No property"
        agent_msg = EmailMessage(
            subject=f"New Rental Application: {app.full_name} — {prop_title}",
            body=agent_body,
            from_email=from_header,
            to=agent_recipients,
            connection=connection,
        )
        if pdf_data:
            agent_msg.attach(f"RentalApplication_{app.last_name}.pdf", pdf_data, "application/pdf")
        agent_msg.send(fail_silently=True)


# ---------------------------------------------------------------------------
# Marketing automation helpers
# ---------------------------------------------------------------------------

def _resolve_lead_city(lead) -> str:
    """Best known city for this lead: property city > detected city > preferred location."""
    if lead.property_interest_id and lead.property_interest:
        return lead.property_interest.city or ""
    return lead.detected_city or lead.preferred_location or ""


def _build_property_image_urls(prop, count: int = 1) -> list:
    """Pre-build Cloudinary image URLs for a property."""
    urls = []
    try:
        for img in prop.images.all()[:count]:
            raw = str(img.image.url)
            if "res.cloudinary.com" in raw and "/upload/" in raw:
                raw = raw.replace("/upload/", "/upload/c_fill,q_auto,f_jpg/")
            urls.append(raw)
    except Exception:
        pass
    return urls


def _similar_properties(exclude_pk, city, listing_type, price, count: int = 3):
    """Return published properties similar to a given listing."""
    from apps.properties.models import Property
    qs = Property.objects.filter(
        is_published=True,
        city__iexact=city,
    ).prefetch_related("images")
    if listing_type:
        qs = qs.filter(listing_type=listing_type)
    if price:
        lo, hi = float(price) * 0.7, float(price) * 1.35
        qs = qs.filter(price__range=(lo, hi))
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return list(qs[:count])


# ---------------------------------------------------------------------------
# Drip sequence
# ---------------------------------------------------------------------------

def send_drip_similar_properties(lead_id: int):
    """Day-2 drip: show 3 similar homes in the lead's city."""
    try:
        from apps.crm.models import Lead
        lead = Lead.objects.select_related("property_interest").prefetch_related(
            "property_interest__images"
        ).get(pk=lead_id)

        if lead.drip_opted_out:
            return "Drip opted out"

        city = _resolve_lead_city(lead)
        if not city:
            return "No city available — skipping drip"

        prop = lead.property_interest
        similar = _similar_properties(
            exclude_pk=prop.pk if prop else None,
            city=city,
            listing_type=prop.listing_type if prop else "",
            price=prop.price if prop else None,
        )
        if not similar:
            return "No similar properties found — skipping drip"

        props_with_images = [
            {"prop": p, "images": _build_property_image_urls(p, 1)}
            for p in similar
        ]

        from_header, connection = _get_email_sender()
        first_name = lead.full_name.split()[0] if lead.full_name else "there"
        body = render_to_string("notifications/drip_similar_properties.html", {
            "lead": lead,
            "first_name": first_name,
            "city": city,
            "props_with_images": props_with_images,
            "frontend_url": settings.FRONTEND_URL,
        })
        msg = EmailMessage(
            subject=f"Still looking in {city}? Here are 3 homes you'll love",
            body=body,
            from_email=from_header,
            to=[lead.email],
            connection=connection,
        )
        msg.content_subtype = "html"
        msg.send()
        return f"Drip day-2 sent to {lead.email}"

    except Exception:
        logger.exception("send_drip_similar_properties failed for lead %s", lead_id)
        raise


def send_drip_urgency_email(lead_id: int):
    """Day-5 drip: urgency email with live inquiry count."""
    try:
        from apps.crm.models import Lead
        from django.utils import timezone
        from datetime import timedelta

        lead = Lead.objects.select_related("property_interest").prefetch_related(
            "property_interest__images"
        ).get(pk=lead_id)

        if lead.drip_opted_out:
            return "Drip opted out"

        city = _resolve_lead_city(lead)
        prop = lead.property_interest

        inquiry_count = 0
        if prop:
            inquiry_count = Lead.objects.filter(
                property_interest=prop,
                created_at__gte=timezone.now() - timedelta(days=30),
            ).count()

        prop_images = _build_property_image_urls(prop, 1) if prop else []
        prop_price_formatted = f"{int(prop.price):,}" if prop and prop.price else ""

        from_header, connection = _get_email_sender()
        first_name = lead.full_name.split()[0] if lead.full_name else "there"
        body = render_to_string("notifications/drip_urgency.html", {
            "lead": lead,
            "first_name": first_name,
            "city": city,
            "prop": prop,
            "prop_images": prop_images,
            "prop_price_formatted": prop_price_formatted,
            "inquiry_count": inquiry_count,
            "frontend_url": settings.FRONTEND_URL,
        })
        subject = (
            f"{inquiry_count} people are looking at homes in {city} right now"
            if city else
            "Homes are moving fast — don't miss out"
        )
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_header,
            to=[lead.email],
            connection=connection,
        )
        msg.content_subtype = "html"
        msg.send()
        return f"Drip day-5 (urgency) sent to {lead.email}"

    except Exception:
        logger.exception("send_drip_urgency_email failed for lead %s", lead_id)
        raise


def send_drip_final_nudge(lead_id: int):
    """Day-8 drip: final personal nudge — skips if lead already applied."""
    try:
        from apps.crm.models import Lead, RentalApplication

        lead = Lead.objects.select_related("property_interest").prefetch_related(
            "property_interest__images"
        ).get(pk=lead_id)

        if lead.drip_opted_out:
            return "Drip opted out"

        if RentalApplication.objects.filter(email=lead.email).exists():
            return "Lead already applied — final nudge skipped"

        city = _resolve_lead_city(lead)
        prop = lead.property_interest
        prop_images = _build_property_image_urls(prop, 1) if prop else []
        prop_price_formatted = f"{int(prop.price):,}" if prop and prop.price else ""

        from_header, connection = _get_email_sender()
        first_name = lead.full_name.split()[0] if lead.full_name else "there"
        body = render_to_string("notifications/drip_final_nudge.html", {
            "lead": lead,
            "first_name": first_name,
            "city": city,
            "prop": prop,
            "prop_images": prop_images,
            "prop_price_formatted": prop_price_formatted,
            "frontend_url": settings.FRONTEND_URL,
        })
        subject = (
            f"Still searching in {city}, {first_name}?"
            if city else
            f"One last thing, {first_name} — we'd love to help you find a home"
        )
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_header,
            to=[lead.email],
            connection=connection,
        )
        msg.content_subtype = "html"
        msg.send()
        return f"Drip day-8 (final nudge) sent to {lead.email}"

    except Exception:
        logger.exception("send_drip_final_nudge failed for lead %s", lead_id)
        raise


# ---------------------------------------------------------------------------
# Abandoned application recovery — run via cPanel cron every 6 hours
# ---------------------------------------------------------------------------

def recover_abandoned_applications():
    """Find DRAFT/PENDING_PAYMENT applications older than 48h and send a recovery email."""
    from apps.crm.models import RentalApplication, ApplicationStatus
    from django.utils import timezone
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(hours=48)
    apps = RentalApplication.objects.filter(
        status__in=[ApplicationStatus.DRAFT, ApplicationStatus.PENDING_PAYMENT],
        submitted_at__lte=cutoff,
        recovery_email_sent=False,
    ).select_related("rental_property")

    count = 0
    for app in apps:
        send_abandoned_application_email(app.pk)
        count += 1
    return f"Sent recovery emails for {count} abandoned applications."


def send_abandoned_application_email(application_id: int):
    """Send a single warm reminder to an applicant who left their form unfinished."""
    try:
        from apps.crm.models import RentalApplication

        app = RentalApplication.objects.select_related("rental_property").get(pk=application_id)

        if app.recovery_email_sent:
            return "Already sent"

        prop = app.rental_property
        _images = _build_property_image_urls(prop, 1) if prop else []
        prop_image = _images[0] if _images else ""
        prop_price_formatted = f"{int(prop.price):,}" if prop and prop.price else ""
        apply_url = (
            f"{settings.FRONTEND_URL}/apply?property={prop.slug}"
            if prop else
            f"{settings.FRONTEND_URL}/apply"
        )

        from_header, connection = _get_email_sender()
        body = render_to_string("notifications/abandoned_application.html", {
            "app": app,
            "prop": prop,
            "prop_image": prop_image,
            "prop_price_formatted": prop_price_formatted,
            "apply_url": apply_url,
            "frontend_url": settings.FRONTEND_URL,
        })
        prop_title = prop.title if prop else "your chosen property"
        msg = EmailMessage(
            subject=f"You left your application unfinished — {prop_title}",
            body=body,
            from_email=from_header,
            to=[app.email],
            connection=connection,
        )
        msg.content_subtype = "html"
        msg.send()

        app.recovery_email_sent = True
        app.save(update_fields=["recovery_email_sent"])
        return f"Recovery email sent to {app.email}"

    except Exception:
        logger.exception("send_abandoned_application_email failed for application %s", application_id)
        raise


# ---------------------------------------------------------------------------
# Post-viewing follow-up
# ---------------------------------------------------------------------------

def send_post_viewing_followup(viewing_id: int):
    """2-hour follow-up after a viewing: thank you + similar homes + Apply CTA."""
    try:
        from apps.scheduler.models import Viewing

        viewing = Viewing.objects.select_related(
            "lead", "property", "agent"
        ).prefetch_related("property__images").get(pk=viewing_id)

        lead = viewing.lead
        prop = viewing.property
        agent = viewing.agent

        if not lead or not lead.email:
            return "No lead email — skipping post-viewing follow-up"

        prop_images = _build_property_image_urls(prop, 1) if prop else []
        prop_price_formatted = f"{int(prop.price):,}" if prop and prop.price else ""

        similar = _similar_properties(
            exclude_pk=prop.pk if prop else None,
            city=prop.city if prop else "",
            listing_type=prop.listing_type if prop else "",
            price=prop.price if prop else None,
        )
        similar_with_images = [
            {"prop": p, "images": _build_property_image_urls(p, 1)}
            for p in similar
        ]

        apply_url = (
            f"{settings.FRONTEND_URL}/apply?property={prop.slug}"
            if prop else
            f"{settings.FRONTEND_URL}/apply"
        )

        from_header, connection = _get_email_sender()
        first_name = lead.full_name.split()[0] if lead.full_name else "there"
        body = render_to_string("notifications/post_viewing_followup.html", {
            "lead": lead,
            "first_name": first_name,
            "prop": prop,
            "prop_images": prop_images,
            "prop_price_formatted": prop_price_formatted,
            "agent": agent,
            "similar_with_images": similar_with_images,
            "apply_url": apply_url,
            "frontend_url": settings.FRONTEND_URL,
        })
        prop_title = prop.title if prop else "the property"
        msg = EmailMessage(
            subject=f"Thanks for visiting {prop_title} — what did you think?",
            body=body,
            from_email=from_header,
            to=[lead.email],
            connection=connection,
        )
        msg.content_subtype = "html"
        msg.send()
        return f"Post-viewing follow-up sent to {lead.email}"

    except Exception:
        logger.exception("send_post_viewing_followup failed for viewing %s", viewing_id)
        raise


# ---------------------------------------------------------------------------
# Internal admin alert emails → lexiltonsecure@gmail.com
# ---------------------------------------------------------------------------

ADMIN_ALERT_EMAIL = "lexiltonsecure@gmail.com"


def send_admin_alert(subject: str, rows: list):
    """
    Send a plain internal alert to the platform admin inbox.
    rows: list of (label, value) tuples displayed as a data table.
    """
    from django.utils.timezone import now

    rows_html = "".join(
        f'<tr>'
        f'<td style="padding:9px 16px;font-size:12px;color:#777;font-weight:500;'
        f'border-bottom:1px solid #f0f0f0;white-space:nowrap;width:35%;background:#fafafa">{label}</td>'
        f'<td style="padding:9px 16px;font-size:13px;color:#111;font-weight:500;'
        f'border-bottom:1px solid #f0f0f0">{value}</td>'
        f'</tr>'
        for label, value in rows
    )

    timestamp = now().strftime("%B %d, %Y at %I:%M %p UTC")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:32px 16px;background:#f4f2ee;
             font-family:'Helvetica Neue',Arial,sans-serif;">
  <table style="max-width:520px;margin:0 auto;background:#fff;border:1px solid #e8e8e8;">
    <tr>
      <td style="background:#0B1F3A;padding:20px 28px;">
        <p style="margin:0 0 4px;font-size:10px;font-weight:700;letter-spacing:2px;
                  text-transform:uppercase;color:#64748b">Hasker &amp; Co. — Internal Alert</p>
        <p style="margin:0;font-size:16px;font-weight:700;color:#fff">{subject}</p>
      </td>
    </tr>
    <tr>
      <td style="padding:0;">
        <table style="width:100%;border-collapse:collapse;">{rows_html}</table>
      </td>
    </tr>
    <tr>
      <td style="padding:14px 28px;border-top:1px solid #f0f0f0;">
        <p style="margin:0;font-size:11px;color:#bbb">Sent {timestamp}</p>
      </td>
    </tr>
  </table>
</body></html>"""

    plain = "\n".join(f"{label}: {value}" for label, value in rows)

    try:
        from_header, connection = _get_email_sender()
        msg = EmailMessage(
            subject=f"[Alert] {subject}",
            body=plain,
            from_email=from_header,
            to=[ADMIN_ALERT_EMAIL],
            connection=connection,
        )
        msg.content_subtype = "html"
        msg.body = html
        msg.send()
    except Exception:
        logger.exception("send_admin_alert failed: %s", subject)
