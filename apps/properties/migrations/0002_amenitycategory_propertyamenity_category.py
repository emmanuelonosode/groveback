import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AmenityCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("icon", models.CharField(blank=True, help_text="Lucide icon name, e.g. 'home'", max_length=50)),
                ("order", models.PositiveIntegerField(default=0)),
            ],
            options={
                "verbose_name": "Amenity Category",
                "verbose_name_plural": "Amenity Categories",
                "ordering": ["order"],
            },
        ),
        migrations.AddField(
            model_name="propertyamenity",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="property_amenities",
                to="properties.amenitycategory",
            ),
        ),
    ]
