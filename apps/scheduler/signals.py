import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Viewing, ViewingStatus

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Viewing)
def send_tour_confirmation_on_create(sender, instance: Viewing, created, **kwargs):
    """
    When staff schedule a viewing in the admin, send the prospective tenant a
    self-tour confirmation email. Only on creation, only for active statuses,
    and only once (guarded by confirmation_sent). Never blocks the save.
    """
    if not created:
        return
    if instance.confirmation_sent:
        return
    if instance.status not in (ViewingStatus.SCHEDULED, ViewingStatus.CONFIRMED):
        return
    try:
        from apps.notifications.tasks import send_tour_confirmation_email
        send_tour_confirmation_email(instance.pk)
    except Exception:
        # A mail failure must never break creating the viewing.
        logger.exception("Tour confirmation email failed for viewing %s", instance.pk)
