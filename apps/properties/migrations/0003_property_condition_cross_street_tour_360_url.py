from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0002_amenitycategory_propertyamenity_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="condition",
            field=models.CharField(
                blank=True,
                choices=[
                    ("new", "New Construction"),
                    ("excellent", "Excellent"),
                    ("good", "Good"),
                    ("fair", "Fair"),
                ],
                default="good",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="property",
            name="cross_street",
            field=models.CharField(
                blank=True,
                help_text="Nearest cross street",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="property",
            name="tour_360_url",
            field=models.URLField(
                blank=True,
                help_text="Matterport / Zillow 3D Home URL",
            ),
        ),
        migrations.AlterField(
            model_name="property",
            name="virtual_tour_url",
            field=models.URLField(blank=True, help_text="360° virtual tour embed URL"),
        ),
    ]
