from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0002_rentalapplication"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="utm_source",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="lead",
            name="utm_medium",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="lead",
            name="utm_campaign",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="utm_source",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="utm_medium",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="utm_campaign",
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
