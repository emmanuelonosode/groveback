import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

_REDIS = "redis://:qwjiBno7nAJiJdJW4ec@127.0.0.1:35717/0"

app = Celery("hasker")

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
    },
)

app.autodiscover_tasks()
