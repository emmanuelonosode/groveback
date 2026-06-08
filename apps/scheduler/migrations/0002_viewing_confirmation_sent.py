from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scheduler", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="viewing",
            name="confirmation_sent",
            field=models.BooleanField(default=False),
        ),
    ]
