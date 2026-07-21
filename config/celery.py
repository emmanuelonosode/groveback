import os
from celery import Celery
from celery.schedules import crontab
from decouple import config

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

# Broker comes from REDIS_URL (set in .env). Defaults to a standard local Redis
# so a fresh VPS install works out of the box. Read via decouple (same as the
# rest of the app) so it isn't overwritten by Django settings lazy-loading.
_REDIS = config("REDIS_URL", default="redis://localhost:6379/0")

# `include` forces these task modules to import at worker startup, so every
# beat-scheduled task is registered deterministically (autodiscover timing can
# otherwise miss them and beat would dispatch tasks the worker can't run).
app = Celery("primefamilyhousing", include=["apps.notifications.tasks", "apps.analytics.tasks"])

# Bypass config_from_object — Django settings lazy-loading overwrites broker_url.
# Set everything directly so Redis is locked in from the start.
app.conf.update(
    broker_url=_REDIS,
    result_backend=_REDIS,
    timezone="America/Los_Angeles",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    beat_scheduler="django_celery_beat.schedulers:DatabaseScheduler",
    beat_schedule={
        "recover-abandoned-applications": {
            "task": "apps.notifications.tasks.recover_abandoned_applications",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "weekly-lead-followup": {
            "task": "apps.notifications.tasks.weekly_lead_followup",
            "schedule": crontab(hour=8, minute=0, day_of_week=1),
        },
        "schedule-viewing-reminders": {
            "task": "apps.notifications.tasks.schedule_viewing_reminders",
            "schedule": crontab(minute=0),
        },
        "process-telemetry-spool": {
            "task": "apps.analytics.tasks.flush_analytics_telemetry",
            "schedule": crontab(),  # every minute — drains the analytics spool
        },
    },
)

app.autodiscover_tasks()
