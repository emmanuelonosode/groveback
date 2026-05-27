from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0003_utm_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="detected_city",
            field=models.CharField(
                blank=True,
                max_length=100,
                help_text="City auto-detected from browser IP or search intent on submission",
            ),
        ),
        migrations.AddField(
            model_name="lead",
            name="drip_opted_out",
            field=models.BooleanField(
                default=False,
                help_text="Suppress automated drip sequence for this lead",
            ),
        ),
    ]
