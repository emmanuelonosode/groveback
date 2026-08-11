import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from apps.crm.models import RentalApplication, ApplicationStatus

count = 0
for app in RentalApplication.objects.filter(status=ApplicationStatus.APPROVED):
    try:
        inv = app.generate_move_in_invoice()
        if inv:
            count += 1
            print(f"Generated invoice for App {app.id}")
    except Exception as e:
        print(f"Error on App {app.id}: {e}")

print(f"Created {count} backfilled move-in invoices")
