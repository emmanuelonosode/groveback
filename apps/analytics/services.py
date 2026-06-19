import json
import logging
import redis
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import Visitor, VisitorSession, PageVisit, TelemetryEvent, RawTelemetryEvent

logger = logging.getLogger(__name__)

# Using the CELERY_BROKER_URL for our Redis client
try:
    redis_client = redis.from_url(getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0"))
except Exception as e:
    logger.error(f"Failed to connect to Redis: {e}")
    redis_client = None

TELEMETRY_QUEUE_KEY = "analytics:telemetry:queue"

def queue_telemetry_event(payload: dict):
    """
    DEPRECATED — telemetry now spools to the durable RawTelemetryEvent table
    (see views.visitor_session + process_spool). Kept only for backwards compat.
    """
    if redis_client:
        try:
            redis_client.lpush(TELEMETRY_QUEUE_KEY, json.dumps(payload))
        except Exception as e:
            logger.error(f"Redis LPUSH failed: {e}")
    else:
        logger.warning("Redis client not available, telemetry event dropped.")

def flush_telemetry_queue(batch_size=500):
    """
    Called by Celery beat task to process the queued events and insert into Postgres.
    """
    if not redis_client:
        return
    
    events_to_process = []
    try:
        # Pop up to batch_size items
        for _ in range(batch_size):
            item = redis_client.rpop(TELEMETRY_QUEUE_KEY)
            if not item:
                break
            events_to_process.append(json.loads(item))
    except Exception as e:
        logger.error(f"Failed to pop from Redis: {e}")
        return

    if not events_to_process:
        return
    
    for payload in events_to_process:
        try:
            process_single_payload(payload)
        except Exception as e:
            logger.error(f"Failed to process telemetry payload: {e}")

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
        
    # We update the visitor if a new session is started by the same visitor
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
    ts = parse_datetime(data.get("timestamp") or "") or timezone.now()

    # Handle end session
    if event_type == "session_end":
        session.end_time = ts
        session.total_dwell_time = data.get("dwell_time", 0.0)
        session.save(update_fields=["end_time", "total_dwell_time"])

    # Handle page visits
    path = data.get("path")
    if path and event_type == "page_view":
        PageVisit.objects.create(
            session=session,
            path=path,
            entry_time=ts,
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
            created_at=ts,
        )


# ── Durable spool processing (DB-backed, no Redis/Celery) ─────────────────────

MAX_ATTEMPTS = 5


def unprocessed_backlog() -> int:
    """Count of raw telemetry rows still awaiting processing."""
    return RawTelemetryEvent.objects.filter(processed=False).count()


def process_spool(batch_size: int = 1000) -> int:
    """
    Drain the oldest unprocessed RawTelemetryEvent rows into the structured
    models. Idempotent (process_single_payload uses get_or_create). A row that
    keeps failing is marked processed after MAX_ATTEMPTS so one poison payload
    can never block the queue. Returns the number of rows cleared.
    """
    rows = list(
        RawTelemetryEvent.objects.filter(processed=False).order_by("received_at")[:batch_size]
    )
    if not rows:
        return 0

    done_ids = []
    for row in rows:
        try:
            process_single_payload(row.payload or {})
            done_ids.append(row.id)
        except Exception:
            logger.exception("Failed processing RawTelemetryEvent %s", row.id)
            attempts = (row.attempts or 0) + 1
            if attempts >= MAX_ATTEMPTS:
                done_ids.append(row.id)  # give up — skip this poison row
            else:
                RawTelemetryEvent.objects.filter(id=row.id).update(attempts=attempts)

    if done_ids:
        RawTelemetryEvent.objects.filter(id__in=done_ids).update(processed=True)
    return len(done_ids)


def prune_processed_spool(days: int = 7) -> int:
    """Delete processed spool rows older than `days` to keep the table small."""
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = RawTelemetryEvent.objects.filter(processed=True, received_at__lt=cutoff).delete()
    return deleted
