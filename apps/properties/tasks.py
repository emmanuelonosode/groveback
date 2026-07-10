from datetime import timedelta

from celery import shared_task
from django.utils import timezone


@shared_task
def unpublish_stale_listings(grace_days: int = 60):
    """
    Retire rented/sold listings after a grace period.

    Delisted homes are kept published for `grace_days` (the page shows a
    "currently rented" banner and funnels visitors to similar homes) so their
    Google equity recirculates instead of turning into a 404 immediately.
    Uses `updated_at` as the status-change proxy — the status flip touches it.
    """
    from apps.properties.models import Property

    cutoff = timezone.now() - timedelta(days=grace_days)
    count = (
        Property.objects
        .filter(status__in=["rented", "sold"], is_published=True, updated_at__lt=cutoff)
        .update(is_published=False)
    )
    return f"unpublished {count} stale listings (rented/sold > {grace_days}d)"
