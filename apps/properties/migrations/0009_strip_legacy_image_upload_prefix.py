"""
Strip the legacy ``image/upload/`` prefix from PropertyImage.image.

Back when ``PropertyImage.image`` was a CloudinaryField, Cloudinary's
``to_python()`` treated imported absolute URLs as public_ids and stored them
with a bogus ``image/upload/`` prefix, e.g.::

    image/upload/https://images.invitationhomes.com/web/.../photo.jpg

The field is a plain URLField now, and the API was stripping that prefix on
every read. This migration cleans the stored values once so the serializer
doesn't have to, which also removes the last functional trace of Cloudinary.

Reversible: the reverse operation restores the prefix.
"""
from django.db import migrations

PREFIX = "image/upload/"


def strip_prefix(apps, schema_editor):
    PropertyImage = apps.get_model("properties", "PropertyImage")
    qs = PropertyImage.objects.filter(image__startswith=PREFIX)
    # Chunked update — the table holds tens of thousands of rows.
    batch = []
    for pk, image in qs.values_list("pk", "image").iterator(chunk_size=2000):
        batch.append(PropertyImage(pk=pk, image=image[len(PREFIX):]))
        if len(batch) >= 2000:
            PropertyImage.objects.bulk_update(batch, ["image"])
            batch = []
    if batch:
        PropertyImage.objects.bulk_update(batch, ["image"])


def restore_prefix(apps, schema_editor):
    PropertyImage = apps.get_model("properties", "PropertyImage")
    qs = PropertyImage.objects.filter(image__startswith="http")
    batch = []
    for pk, image in qs.values_list("pk", "image").iterator(chunk_size=2000):
        batch.append(PropertyImage(pk=pk, image=PREFIX + image))
        if len(batch) >= 2000:
            PropertyImage.objects.bulk_update(batch, ["image"])
            batch = []
    if batch:
        PropertyImage.objects.bulk_update(batch, ["image"])


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0008_alter_propertyimage_image"),
    ]

    operations = [
        migrations.RunPython(strip_prefix, restore_prefix),
    ]
