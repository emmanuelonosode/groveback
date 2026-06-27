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
    ("granite", "kitchen"),
    ("quartz", "kitchen"),
    ("oven", "kitchen"),
    ("range", "kitchen"),
    ("washer", "utility"),
    ("dryer", "utility"),
    ("laundry", "utility"),
    ("air condition", "utility"),
    ("central air", "utility"),
    ("thermostat", "utility"),
    ("pool", "community"),
    ("fitness", "community"),
    ("playground", "community"),
    ("dog park", "community"),
    ("tennis", "community"),
    ("basketball", "community"),
    ("trail", "community"),
    ("gated", "community"),
    ("clubhouse", "community"),
    ("garage", "community"),
    ("yard", "community"),
    ("patio", "community"),
    ("pet", "pet"),
    ("dog", "pet"),
    ("cat", "pet"),
]

STATE_BY_MARKET_SLUG = {
    "atlanta-georgia": "GA",
    "austin-texas": "TX",
    "charlotte-north-carolina": "NC",
    "chicago-illinois": "IL",
    "dallas-texas": "TX",
    "denver-colorado": "CO",
    "houston-texas": "TX",
    "jacksonville-florida": "FL",
    "las-vegas-nevada": "NV",
    "los-angeles-california": "CA",
    "miami-florida": "FL",
    "minneapolis-minnesota": "MN",
    "nashville-tennessee": "TN",
    "orlando-florida": "FL",
    "phoenix-arizona": "AZ",
    "sacramento-california": "CA",
    "salt-lake-city-utah": "UT",
    "san-antonio-texas": "TX",
    "seattle-washington": "WA",
    "tampa-florida": "FL",
}


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
    # Note: 40% price reduction applied (original * 0.60), rounded to the nearest dollar.
    original = _decimal(value, Decimal("0"))
    if original <= 0:
        return Decimal("0")
    return (original * Decimal("0.60")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _load_json(path):
    with open(path, "rb") as test_file:
        magic = test_file.read(2)
    opener = gzip.open if magic == b"\x1f\x8b" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def _city_from_address(address):
    city = _text(address.get("city"))
    if city:
        return city
    address_line = _text(address.get("address_1") or address.get("full_address"))
    match = re.search(r"\s([A-Za-z .'-]+),\s*[A-Z]{2}\s+\d{5}", address_line)
    return match.group(1).strip() if match else ""


def _state_from(raw, summary):
    address = raw.get("address") or {}
    state = _text(address.get("state"))
    if len(state) == 2:
        return state.upper()
    market_slug = _text(summary.get("market_slug") or raw.get("market_slug"))
    return STATE_BY_MARKET_SLUG.get(market_slug, state[:2].upper())


def _zip_from(address, slug):
    zip_code = _text(address.get("zip_code") or address.get("postal_code"))
    if zip_code:
        return zip_code[:10]
    match = re.search(r"-(\d{5})-\d+$", _text(slug))
    return match.group(1) if match else ""


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
    for key in ("image_url", "url", "src", "imageUrl", "originalUrl", "cdnUrl", "largeUrl"):
        value = photo.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    return ""


def _amenity_name(amenity):
    if isinstance(amenity, str):
        return amenity.strip()
    if not isinstance(amenity, dict):
        return ""
    for key in ("name", "display_name", "displayName", "label", "title"):
        value = amenity.get(key)
        if value:
            return str(value).strip()
    slug = amenity.get("slug")
    return str(slug).replace("-", " ").title().strip() if slug else ""


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
    help = "Import scraped Invitation Homes JSON into the database."

    def add_arguments(self, parser):
        parser.add_argument("--json", required=True, help="Path to invitationhomes_properties_latest.json or .json.gz")
        parser.add_argument("--clear", action="store_true", help="Delete existing imported Invitation Homes rows first.")
        parser.add_argument("--markets", default=None, help="Comma-separated market slugs to import.")
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

        market_filter = (
            {market.strip() for market in options["markets"].split(",") if market.strip()}
            if options["markets"]
            else None
        )
        selected = []
        for item in properties:
            summary = item.get("summary") or {}
            raw = item.get("raw") or {}
            market_slug = _text(summary.get("market_slug") or raw.get("market_slug"))
            if market_filter and market_slug not in market_filter:
                continue
            selected.append(item)
            if options["limit"] and len(selected) >= options["limit"]:
                break

        self.stdout.write(f"Selected {len(selected)} properties from JSON.")
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("DRY RUN - nothing written."))
            self.stdout.write(f"Images found: {sum(len((item.get('summary') or {}).get('photos') or []) for item in selected)}")
            self.stdout.write(f"Amenities found: {sum(len((item.get('summary') or {}).get('amenities') or []) for item in selected)}")
            return

        with transaction.atomic():
            if options["clear"]:
                deleted, _ = Property.objects.filter(agent__email="agent@haskerrealtygroup.com").delete()
                self.stdout.write(self.style.WARNING(f"Cleared {deleted} imported Invitation Homes rows."))

            categories = {}
            for key, name, icon, order in CATEGORIES:
                category, _ = AmenityCategory.objects.get_or_create(
                    name=name,
                    defaults={"icon": icon, "order": order},
                )
                categories[key] = category

            agent, created = User.objects.get_or_create(
                email="agent@haskerrealtygroup.com",
                defaults={
                    "first_name": "Marcus",
                    "last_name": "Reid",
                    "role": Role.AGENT,
                    "phone": "(757) 555-0101",
                },
            )
            if created:
                agent.set_password("Agent1234!")
                agent.save()

            existing_slugs = set(Property.objects.values_list("slug", flat=True))
            total_properties = total_images = total_amenities = skipped = 0

            for item in selected:
                summary = item.get("summary") or {}
                raw = item.get("raw") or {}
                address = raw.get("address") or {}
                slug = _text(summary.get("slug") or raw.get("slug"))
                db_slug = re.sub(r"^invh-", "", slug).strip("-")
                if not db_slug:
                    db_slug = slugify(f"{summary.get('address') or raw.get('property_id')}")
                if not db_slug or db_slug in existing_slugs:
                    skipped += 1
                    continue

                beds = _int(summary.get("beds") or raw.get("beds"), 0)
                baths = _decimal(summary.get("baths") or raw.get("baths"), Decimal("0"))
                price = _discounted_rent(summary.get("rent") or raw.get("rent"))
                sqft = _int(summary.get("square_footage") or raw.get("square_footage"), 0)
                year_built = _int(summary.get("year_built") or raw.get("year_built"), None)
                city = _city_from_address(address) or _text(summary.get("market_name") or raw.get("market_name"))
                state = _state_from(raw, summary)
                address_1 = _text(address.get("address_1") or summary.get("address"))
                zip_code = _zip_from(address, slug)
                neighborhood = _text(summary.get("neighborhood")) or _text(raw.get("portfolio_group"))
                description = _text(summary.get("description") or raw.get("description"))
                map_location = summary.get("map_location") or raw.get("map_location") or {}
                latitude = _decimal(map_location.get("latitude") or map_location.get("lat"), None)
                longitude = _decimal(map_location.get("longitude") or map_location.get("lng"), None)

                bed_label = "Studio" if beds == 0 else f"{beds}-Bed"
                title_address = address_1 or city
                title = f"{bed_label} House for Rent - {title_address}, {city}, {state}".strip(" ,-")
                amenities = summary.get("amenities") or raw.get("amenities") or []

                prop = Property.objects.create(
                    agent=agent,
                    slug=db_slug,
                    title=title[:200],
                    description=description or f"A rental home available in {city}, {state}.",
                    type="residential",
                    listing_type="for-rent",
                    status="available",
                    price=price,
                    price_label="/mo",
                    bedrooms=beds,
                    bathrooms=baths,
                    sqft=sqft,
                    year_built=year_built,
                    garage=1 if any("garage" in _amenity_name(a).lower() for a in amenities) else 0,
                    address=address_1[:200],
                    city=city[:100],
                    state=state[:2],
                    zip_code=zip_code,
                    latitude=latitude,
                    longitude=longitude,
                    neighborhood=neighborhood[:100],
                    condition="excellent",
                    cross_street="",
                    virtual_tour_url=_text(summary.get("virtual_tour_url") or raw.get("virtual_tour_url")),
                    tour_360_url=_text(summary.get("virtual_tour_url_mobile") or raw.get("virtual_tour_url_mobile")),
                    is_featured=bool((summary.get("flags") or {}).get("is_featured_listing")),
                    is_published=True,
                )

                existing_slugs.add(db_slug)
                total_properties += 1

                photos = summary.get("photos") or raw.get("photos") or []
                total_images += _insert_images_raw(prop.id, [_photo_url(photo) for photo in photos])

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
                    self.stdout.write(f"Imported {total_properties} properties...")

        self.stdout.write(self.style.SUCCESS("Invitation Homes JSON import complete."))
        self.stdout.write(self.style.SUCCESS(f"Properties imported: {total_properties}"))
        self.stdout.write(self.style.SUCCESS(f"Images imported: {total_images}"))
        self.stdout.write(self.style.SUCCESS(f"Amenities imported: {total_amenities}"))
        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipped existing/invalid rows: {skipped}"))
