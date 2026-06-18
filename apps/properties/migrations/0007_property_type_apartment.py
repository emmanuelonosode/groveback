from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0006_alter_property_virtual_tour_url_favoriteproperty"),
    ]

    operations = [
        migrations.AlterField(
            model_name="property",
            name="type",
            field=models.CharField(
                choices=[
                    ("residential", "Residential"),
                    ("apartment", "Apartment"),
                    ("commercial", "Commercial"),
                    ("land", "Land"),
                    ("condo", "Condo"),
                    ("townhouse", "Townhouse"),
                ],
                default="residential",
                max_length=20,
            ),
        ),
    ]
