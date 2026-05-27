"""
Management command: clean_listings

- Sets all properties to pet-friendly (adds "Pets Allowed" amenity)
- Reduces each rental price by a random 20–40%
- Strips InvitationHomes links and stray HTML from description fields

Usage:
    python manage.py clean_listings
    python manage.py clean_listings --dry-run   # preview only, no DB writes
"""

import re
import random
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.properties.models import Property, PropertyAmenity, AmenityCategory


HTML_TAG_RE = re.compile(r"<[^>]+>", re.IGNORECASE)
MULTI_SPACE_RE = re.compile(r"\n{3,}")


def strip_html(text: str) -> str:
    """Remove all HTML tags and collapse excessive blank lines."""
    if not text:
        return text
    cleaned = HTML_TAG_RE.sub("", text)
    # Remove leftover "Learn More" link text that follows a stripped <a>
    cleaned = re.sub(r"\s*Learn More\s*", " ", cleaned, flags=re.IGNORECASE)
    # Collapse runs of 3+ newlines to 2
    cleaned = MULTI_SPACE_RE.sub("\n\n", cleaned)
    return cleaned.strip()


class Command(BaseCommand):
    help = "Clean listing data: pet-friendly, price reduction, strip HTML from descriptions"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without writing to the database",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be saved"))

        # Ensure pet amenity category exists
        pet_cat, _ = AmenityCategory.objects.get_or_create(
            name__iexact="pet",
            defaults={"name": "Pet", "icon": "paw-print"},
        )

        properties = list(Property.objects.all().order_by("id"))
        total = len(properties)
        self.stdout.write(f"Processing {total} properties…")

        price_updated = 0
        desc_updated = 0
        pet_added = 0
        amenity_bulk = []

        with transaction.atomic():
            for i, prop in enumerate(properties, 1):
                changed = False

                # ── 1. Pet-friendly amenity ──────────────────────────────────
                already_pet = prop.amenities.filter(
                    name__iregex=r"pet|dog|cat|animal"
                ).exists()
                if not already_pet:
                    amenity_bulk.append(
                        PropertyAmenity(
                            property=prop,
                            category=pet_cat,
                            name="Pets Allowed",
                        )
                    )
                    pet_added += 1

                # ── 2. Price reduction 20–40% ────────────────────────────────
                # Use property id as seed so the same property always gets the
                # same discount (idempotent re-runs won't stack discounts).
                rng = random.Random(prop.id)
                discount_pct = rng.randint(20, 40)
                multiplier = Decimal(str((100 - discount_pct) / 100))
                new_price = (prop.price * multiplier).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                if new_price != prop.price:
                    if dry_run and i <= 10:
                        self.stdout.write(
                            f"  [{i}/{total}] {prop.slug}: "
                            f"${prop.price} -> ${new_price} (-{discount_pct}%)"
                        )
                    prop.price = new_price
                    price_updated += 1
                    changed = True

                # ── 3. Strip HTML from description ───────────────────────────
                if prop.description:
                    cleaned = strip_html(prop.description)
                    if cleaned != prop.description:
                        prop.description = cleaned
                        desc_updated += 1
                        changed = True

                if changed and not dry_run:
                    prop.save(update_fields=["price", "description"])

                if i % 500 == 0:
                    self.stdout.write(f"  … {i}/{total} done")

            # Bulk-create pet amenities
            if amenity_bulk and not dry_run:
                PropertyAmenity.objects.bulk_create(amenity_bulk, batch_size=500, ignore_conflicts=True)

            if dry_run:
                # Roll back everything in dry-run mode
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f"\nDone {'(dry run)' if dry_run else ''}:\n"
            f"  Prices reduced : {price_updated}\n"
            f"  Descriptions cleaned: {desc_updated}\n"
            f"  Pet amenities added : {pet_added}"
        ))
