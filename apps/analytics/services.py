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
    ip_addr = data.get("ip_address")
    
    visitor, created_visitor = Visitor.objects.get_or_create(fingerprint_id=fingerprint)
    
    # Update IP history
    if ip_addr:
        if not visitor.first_ip:
            visitor.first_ip = ip_addr
        visitor.last_ip = ip_addr

    if user_id and not visitor.user_id:
        visitor.user_id = user_id
        
    session_id = data.get("session_id")
    if not session_id:
        visitor.save()
        return
        
    session, created_session = VisitorSession.objects.get_or_create(
        session_id=session_id,
        defaults={
            "visitor": visitor,
            "ip_address": ip_addr,
            "city": data.get("city", ""),
            "region": data.get("region", ""),
            "country_code": data.get("country_code", ""),
            "browser": data.get("browser", ""),
            "os": data.get("os", ""),
            "device_type": data.get("device_type", ""),
            "screen": data.get("screen", ""),
            "viewport": data.get("viewport", ""),
            "pixel_ratio": float(data.get("pixel_ratio") or 1.0),
            "connection_type": data.get("connection_type", ""),
            "hardware_concurrency": int(data.get("hardware_concurrency") or 0),
            "device_memory": float(data.get("device_memory") or 0.0),
            "max_touch_points": int(data.get("max_touch_points") or 0),
            "orientation": data.get("orientation", ""),
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
    
    if not created_session and visitor != session.visitor:
        session.visitor = visitor
        session.save(update_fields=["visitor"])

    event_type = data.get("event_type")
    ts = parse_datetime(data.get("timestamp") or "") or timezone.now()

    # Track city/location intent
    city = data.get("city") or session.city
    if city and city not in (visitor.searched_locations or []):
        locations = list(visitor.searched_locations or [])
        locations.append(city)
        visitor.searched_locations = locations[:20]

    # Handle end session
    if event_type == "session_end":
        session.end_time = ts
        session.total_dwell_time = float(data.get("dwell_time", 0.0))
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
                visit.max_scroll_depth = max(visit.max_scroll_depth, float(data["max_scroll_depth"]))
            if "idle_time" in data:
                visit.idle_time = float(data["idle_time"])
            visit.save(update_fields=["max_scroll_depth", "idle_time"])
            
    # Handle arbitrary events (clicks, conversions, property views, identify)
    if event_type not in ["session_end", "page_view", "engagement", "init", None]:
        visit = None
        if path:
            visit = PageVisit.objects.filter(session=session, path=path).order_by("-entry_time").first()
            
        event_data = data.get("event_data", {})
        if not isinstance(event_data, dict):
            event_data = {}

        # Handle identify / lead submission
        email = event_data.get("email")
        if email and isinstance(email, str) and "@" in email:
            visitor.associated_email = email.strip().lower()
            visitor.is_lead = True
            if not visitor.user_id:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                matched_user = User.objects.filter(email__iexact=email.strip()).first()
                if matched_user:
                    visitor.user = matched_user

        # Track property views
        prop_id = event_data.get("property_id")
        if prop_id:
            pid_str = str(prop_id)
            viewed = list(visitor.viewed_property_ids or [])
            if pid_str not in viewed:
                viewed.append(pid_str)
                visitor.viewed_property_ids = viewed[:50]
            session.properties_viewed_count = (session.properties_viewed_count or 0) + 1
            session.save(update_fields=["properties_viewed_count"])

        TelemetryEvent.objects.create(
            session=session,
            page_visit=visit,
            event_type=event_type,
            event_data=event_data,
            created_at=ts,
        )

    # Recalculate visitor summary stats
    sessions_qs = visitor.sessions.all()
    visitor.total_sessions_count = sessions_qs.count()
    visitor.total_dwell_time = sum(s.total_dwell_time or 0.0 for s in sessions_qs)
    if session.device_type:
        visitor.primary_device = session.device_type
    if session.city:
        visitor.primary_city = session.city

    visitor.save()


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
