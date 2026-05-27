# Generated manually
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0006_rentalapplication_fee_utm_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="email_marketing_opted_out",
            field=models.BooleanField(
                default=False,
                help_text="Set by the Hasker Mailer when this lead unsubscribes from marketing emails"
            ),
        ),
    ]
