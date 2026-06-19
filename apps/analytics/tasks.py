import logging
from celery import shared_task
from .services import process_spool, prune_processed_spool

logger = logging.getLogger(__name__)

@shared_task
def flush_analytics_telemetry():
    """
    Optional belt-and-suspenders: drain the RawTelemetryEvent spool if Celery
    beat happens to be running. The primary driver is the `process_telemetry`
    management command via cron; the beacon endpoint also has an inline valve.
    """
    try:
        process_spool(batch_size=1000)
        prune_processed_spool(days=7)
    except Exception as e:
        logger.error(f"Failed to process telemetry spool: {e}")
