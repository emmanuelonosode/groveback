import logging
from celery import shared_task
from .services import flush_telemetry_queue

logger = logging.getLogger(__name__)

@shared_task
def flush_analytics_telemetry():
    """
    Periodic task to pop telemetry events from Redis and bulk insert into Postgres.
    Recommended to run every 1-5 minutes depending on traffic.
    """
    try:
        flush_telemetry_queue(batch_size=1000)
    except Exception as e:
        logger.error(f"Failed to flush telemetry queue: {e}")
