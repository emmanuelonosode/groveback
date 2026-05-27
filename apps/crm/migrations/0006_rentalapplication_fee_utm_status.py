from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0005_rentalapplication_recovery"),
    ]

    operations = [
        migrations.AddField(
            model_name="rentalapplication",
            name="application_fee",
            field=models.DecimalField(decimal_places=2, default=100.0, max_digits=10),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="is_fee_paid",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="payment_intent_id",
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name="rentalapplication",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("PENDING_PAYMENT", "Pending Payment"),
                    ("PENDING_VERIFICATION", "Pending Verification"),
                    ("SUBMITTED", "Submitted"),
                    ("REVIEWED", "Reviewed"),
                    ("APPROVED", "Approved"),
                    ("REJECTED", "Rejected"),
                    ("PAYMENT_FAILED", "Payment Failed"),
                ],
                default="DRAFT",
                max_length=20,
            ),
        ),
    ]
