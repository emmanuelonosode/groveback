import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from apps.crm.models import RentalApplication
from apps.transactions.models import Invoice
from apps.accounts.models import CustomUser

count = 0
for app in RentalApplication.objects.all():
    user = CustomUser.objects.filter(email=app.email).first()
    if user:
        updated = Invoice.objects.filter(
            title__icontains='Move-in Costs', 
            description__icontains=f'Application ID #{app.id}', 
            user__isnull=True
        ).update(user=user)
        count += updated

print(f"Linked {count} invoices")
