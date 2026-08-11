import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from apps.notifications.tasks import send_daily_invoice_reminders
from apps.transactions.models import Invoice
from django.utils import timezone
from datetime import timedelta

print("Before:", Invoice.objects.filter(due_reminder_sent=False, status="SENT").count())
result = send_daily_invoice_reminders()
print("Result:", result)
print("After:", Invoice.objects.filter(due_reminder_sent=False, status="SENT").count())
