import gzip
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils.text import slugify

from apps.accounts.models import Role
from apps.properties.models import AmenityCategory, Property, PropertyAmenity

User = get_user_model()

CATEGORIES = [
    ("home", "Home Features", "Home", 0),
    ("kitchen", "Kitchen Features", "ChefHat", 1),
    ("utility", "Utility & Maintenance", "Zap", 2),
    ("community", "Community Features", "Users", 3),
    ("pet", "Pet Policy", "PawPrint", 4),
]

AMENITY_KEYWORDS = [
    ("kitchen", "kitchen"),
    ("dishwasher", "kitchen"),
    ("refrigerator", "kitchen"),
    ("microwave", "kitchen"),
    ("stainless", "kitchen"),
    ("washer", "utility"),
    ("dryer", "utility"),
    ("laundry", "utility"),
    ("air condition", "utility"),
    ("central air", "utility"),
    ("thermostat", "utility"),
    ("pool", "community"),
    ("fitness", "community"),
    ("clubhouse", "community"),
    ("showcase", "community"),
    ("featured", "community"),
    ("3d tour", "community"),
    ("garage", "community"),
    ("pet", "pet"),
    ("dog", "pet"),
    ("cat", "pet"),
]


def _text(value):
    return str(value or "").strip()


def _int(value, default=0):
    try:
        if value in ("", None):
            return default
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return default


def _decimal(value, default=Decimal("0")):
    try:
        if value in ("", None):
            return default
        return Decimal(str(value).replace(",", "").replace("$", "").strip())
    except (InvalidOperation, TypeError, ValueError):
        return default


def _discounted_rent(value):
    original = _decimal(value, Decimal("0"))
    if original <= 0:
        return Decimal("0")
    return ((original * Decimal("0.60")) / Decimal("100")).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    ) * Decimal("100")


def _load_json(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def _category_key(name):
    lowered = name.lower()
    for keyword, category in AMENITY_KEYWORDS:
        if keyword in lowered:
            return category
    return "home"


def _photo_url(photo):
    if isinstance(photo, str):
        return photo if photo.startswith("http") else ""
    if not isinstance(photo, dict):
        return ""
    for key in ("image_url", "url", "src", "thumbnail_url"):
        value = photo.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    return ""


def _amenity_name(amenity):
    if isinstance(amenity, str):
        return amenity.strip()
    if not isinstance(amenity, dict):
        return ""
    return _text(amenity.get("name") or amenity.get("displayString") or amenity.get("slug"))


def _insert_images_raw(property_id, urls):
    clean_urls = []
    seen = set()
    for url in urls:
        if url and url.startswith("http") and url not in seen:
            clean_urls.append(url)
            seen.add(url)
    if not clean_urls:
        return 0

    q = connection.ops.quote_name
    sql = (
        f"INSERT INTO {q('properties_propertyimage')} "
        f"({q('property_id')}, {q('image')}, {q('caption')}, {q('is_primary')}, {q('order')}) "
        f"VALUES (%s, %s, %s, %s, %s)"
    )
    rows = [(property_id, url, "", index == 0, index) for index, url in enumerate(clean_urls)]
    with connection.cursor() as cursor:
        cursor.executemany(sql, rows)
    return len(clean_urls)


class Command(BaseCommand):
    help = "Import scraped Zillow rental JSON into the database."

    def add_arguments(self, parser):
        parser.add_argument("--json", required=True, help="Path to zillow_rentals_latest.json or .json.gz")
        parser.add_argument("--clear", action="store_true", help="Delete existing Zillow imported rows first.")
        parser.add_argument("--limit", type=int, default=None, help="Maximum properties to import.")
        parser.add_argument("--dry-run", action="store_true", help="Validate and count without writing.")

    def handle(self, *args, **options):
        json_path = Path(options["json"]).expanduser()
        if not json_path.exists():
            raise CommandError(f"JSON file not found: {json_path}")

        self.stdout.write(f"Loading {json_path}...")
        payload = _load_json(json_path)
        properties = payload.get("properties")
        if not isinstance(properties, list):
            raise CommandError("Expected top-level JSON key 'properties' to be a list.")
        if options["limit"]:
            properties = properties[: options["limit"]]

        self.stdout.write(f"Selected {len(properties)} Zillow properties from JSON.")
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("DRY RUN - nothing written."))
            self.stdout.write(f"Images found: {sum(len((item.get('summary') or {}).get('photos') or []) for item in properties)}")
            self.stdout.write(f"Amenities found: {sum(len((item.get('summary') or {}).get('amenities') or []) for item in properties)}")
            return

        with transaction.atomic():
            if options["clear"]:
                deleted, _ = Property.objects.filter(agent__email="zillow@haskerrealtygroup.com").delete()
                self.stdout.write(self.style.WARNING(f"Cleared {deleted} existing Zillow imported rows."))

            categories = {}
            for key, name, icon, order in CATEGORIES:
                category, _ = AmenityCategory.objects.get_or_create(
                    name=name,
                    defaults={"icon": icon, "order": order},
                )
                categories[key] = category

            agent, created = User.objects.get_or_create(
                email="zillow@haskerrealtygroup.com",
                defaults={
                    "first_name": "Zillow",
                    "last_name": "Rentals",
                    "role": Role.AGENT,
                    "phone": "(757) 555-0199",
                },
            )
            if created:
                agent.set_password("Agent1234!")
                agent.save()

            existing_slugs = set(Property.objects.values_list("slug", flat=True))
            total_properties = total_images = total_amenities = skipped = 0

            for item in properties:
                summary = item.get("summary") or {}
                address = summary.get("address") or {}
                location = summary.get("map_location") or {}
                slug = _text(summary.get("slug"))
                if not slug:
                    slug = f"zillow-{slugify(_text(address.get('full_address') or summary.get('property_id')))}"
                base_slug = slug
                counter = 1
                while slug in existing_slugs:
                    counter += 1
                    slug = f"{base_slug}-{counter}"
                if not slug:
                    skipped += 1
                    continue

                beds = _int(summary.get("beds"), 0)
                baths = _decimal(summary.get("baths"), Decimal("0"))
                rent = _discounted_rent(summary.get("rent"))
                sqft = _int(summary.get("square_footage"), 0)
                year_built = _int(summary.get("year_built"), None)
                city = _text(address.get("city") or summary.get("market_name"))
                state = _text(address.get("state"))[:2].upper()
                address_1 = _text(address.get("address_1") or address.get("full_address"))
                zip_code = _text(address.get("zip_code"))[:10]
                neighborhood = _text(summary.get("neighborhood") or city)[:100]
                description = _text(summary.get("description"))
                title_address = address_1 or city
                bed_label = "Studio" if beds == 0 else f"{beds}-Bed"
                title = f"{bed_label} House for Rent - {title_address}, {city}, {state}".strip(" ,-")
                amenities = summary.get("amenities") or []

                prop = Property.objects.create(
                    agent=agent,
                    slug=slug,
                    title=title[:200],
                    description=description or f"A Zillow rental listing available in {city}, {state}.",
                    type="residential",
                    listing_type="for-rent",
                    status="available",
                    price=rent,
                    price_label="/mo",
                    bedrooms=beds,
                    bathrooms=baths,
                    sqft=sqft,
                    year_built=year_built,
                    garage=1 if any("garage" in _amenity_name(a).lower() for a in amenities) else 0,
                    address=address_1[:200],
                    city=city[:100],
                    state=state,
                    zip_code=zip_code,
                    latitude=_decimal(location.get("latitude"), None),
                    longitude=_decimal(location.get("longitude"), None),
                    neighborhood=neighborhood,
                    condition="excellent",
                    cross_street="",
                    virtual_tour_url=_text(summary.get("virtual_tour_url")),
                    tour_360_url=_text(summary.get("virtual_tour_url_mobile")),
                    is_featured=bool((summary.get("flags") or {}).get("is_featured_listing")),
                    is_published=True,
                )

                existing_slugs.add(slug)
                total_properties += 1

                total_images += _insert_images_raw(
                    prop.id,
                    [_photo_url(photo) for photo in summary.get("photos") or []],
                )

                amenity_objects = []
                seen_amenities = set()
                for amenity in amenities:
                    name = _amenity_name(amenity)[:100]
                    if not name or name.lower() in seen_amenities:
                        continue
                    seen_amenities.add(name.lower())
                    amenity_objects.append(
                        PropertyAmenity(
                            property=prop,
                            category=categories[_category_key(name)],
                            name=name,
                        )
                    )
                if amenity_objects:
                    PropertyAmenity.objects.bulk_create(amenity_objects, batch_size=1000)
                    total_amenities += len(amenity_objects)

                if total_properties % 250 == 0:
                    self.stdout.write(f"Imported {total_properties} Zillow properties...")

        self.stdout.write(self.style.SUCCESS("Zillow JSON import complete."))
        self.stdout.write(self.style.SUCCESS(f"Properties imported: {total_properties}"))
        self.stdout.write(self.style.SUCCESS(f"Images imported: {total_images}"))
        self.stdout.write(self.style.SUCCESS(f"Amenities imported: {total_amenities}"))
        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipped invalid rows: {skipped}"))
