import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()
from apps.transactions.models import Invoice
from apps.notifications.tasks import generate_invoice_pdf

count = 0
for inv in Invoice.objects.filter(invoice_number__startswith="HRG-"):
    old_seq = int(inv.invoice_number.split("-")[-1])
    new_seq = old_seq + 2499
    inv.invoice_number = f"PFH-2026-{new_seq:04d}"
    inv.save(update_fields=['invoice_number'])
    # Regenerate the PDF so the file updates
    try:
        generate_invoice_pdf(inv.id)
    except Exception as e:
        print(f"Failed to generate PDF for invoice {inv.id}: {e}")
    count += 1

print(f"Successfully updated {count} invoices and PDFs to the new PFH format!")
