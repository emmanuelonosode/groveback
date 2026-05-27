from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0002_remove_invoice_stripe_invoice_id_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentMethodConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("method", models.CharField(choices=[("BANK_TRANSFER", "Bank Transfer"), ("CASH", "Cash"), ("CHECK", "Check"), ("PAYPAL", "PayPal"), ("VENMO", "Venmo"), ("CASHAPP", "CashApp"), ("CHIME", "Chime")], max_length=20, unique=True)),
                ("display_name", models.CharField(help_text='"e.g. "Venmo", "Cash App"', max_length=50)),
                ("handle", models.CharField(help_text='e.g. "@HaskerRealty" or "payments@haskerrealtygroup.com"', max_length=200)),
                ("is_active", models.BooleanField(default=True)),
                ("extra_instructions", models.TextField(blank=True, help_text="Optional note shown to tenants (e.g. 'Use Friends & Family')")),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Payment Method Config",
                "verbose_name_plural": "Payment Method Configs",
                "ordering": ["method"],
            },
        ),
    ]
