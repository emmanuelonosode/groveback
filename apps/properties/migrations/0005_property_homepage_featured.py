from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0004_add_map_filter_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="homepage_featured",
            field=models.BooleanField(
                default=False,
                help_text='Show in the "Available Now" section on the homepage. Independent of the Featured badge.',
            ),
        ),
    ]
