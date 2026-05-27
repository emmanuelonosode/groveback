from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0004_lead_geo_drip"),
    ]

    operations = [
        migrations.AddField(
            model_name="rentalapplication",
            name="recovery_email_sent",
            field=models.BooleanField(default=False),
        ),
    ]
