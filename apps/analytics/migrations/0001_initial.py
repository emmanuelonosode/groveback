from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="VisitorSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_id",    models.CharField(db_index=True, max_length=64, unique=True)),
                ("ip_address",    models.GenericIPAddressField(blank=True, null=True)),
                ("city",          models.CharField(blank=True, max_length=100)),
                ("region",        models.CharField(blank=True, max_length=100)),
                ("country_code",  models.CharField(blank=True, max_length=10)),
                ("browser",       models.CharField(blank=True, max_length=100)),
                ("os",            models.CharField(blank=True, max_length=50)),
                ("device_type",   models.CharField(blank=True, max_length=20)),
                ("screen",        models.CharField(blank=True, max_length=30)),
                ("language",      models.CharField(blank=True, max_length=20)),
                ("timezone",      models.CharField(blank=True, max_length=60)),
                ("landing_page",  models.CharField(blank=True, max_length=500)),
                ("referrer",      models.TextField(blank=True)),
                ("utm_source",    models.CharField(blank=True, max_length=100)),
                ("utm_medium",    models.CharField(blank=True, max_length=100)),
                ("utm_campaign",  models.CharField(blank=True, max_length=200)),
                ("referral_code", models.CharField(blank=True, max_length=20)),
                ("created_at",    models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"], "verbose_name": "Visitor Session", "verbose_name_plural": "Visitor Sessions"},
        ),
    ]
