import csv
import json
import os
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role
from apps.properties.models import AmenityCategory, Property, PropertyAmenity, PropertyImage

User = get_user_model()

# ── Amenity slug → our 5 category keys ────────────────────────────────────────
SLUG_TO_CAT = {
    # kitchen
    "granite-countertops": "kitchen",
    "quartz-countertops": "kitchen",
    "stainless-steel-appliances": "kitchen",
    "dishwasher": "kitchen",
    "refrigerator": "kitchen",
    "microwave": "kitchen",
    "gas-stove": "kitchen",
    "kitchen-island": "kitchen",
    "gas-range": "kitchen",
    "double-oven": "kitchen",
    "wine-fridge": "kitchen",
    # utility
    "w-d-hookups": "utility",
    "washer-dryer": "utility",
    "laundry-in-unit": "utility",
    "in-unit-laundry": "utility",
    "central-air": "utility",
    "central-heat": "utility",
    "air-conditioning": "utility",
    "air-filter-delivery": "utility",
    "utilities-included": "utility",
    "smart-thermostat": "utility",
    # community
    "has-pool": "community",
    "community-pool": "community",
    "patio": "community",
    "fenced-yard": "community",
    "garage": "community",
    "gated-community": "community",
    "hoa": "community",
    "walking-trails": "community",
    "fitness-center": "community",
    "clubhouse": "community",
    "playground": "community",
    "basketball-court": "community",
    "tennis-court": "community",
    "dog-park": "community",
    "rooftop-deck": "community",
    # pet
    "pet-friendly": "pet",
    "no-pets": "pet",
    "dogs-allowed": "pet",
    "cats-allowed": "pet",
    "pet-deposit": "pet",
    "pet-fee": "pet",
}

CATEGORIES = [
    ("home",      "Home Features",         "Home",     0),
    ("kitchen",   "Kitchen Features",      "ChefHat",  1),
    ("utility",   "Utility & Maintenance", "Zap",      2),
    ("community", "Community Features",    "Users",    3),
    ("pet",       "Pet Policy",            "PawPrint", 4),
]

TYPE_LABEL = {
    "house":     "Home",
    "apartment": "Apartment",
    "townhouse": "Townhouse",
    "condo":     "Condo",
}


def _bool(val: str) -> bool:
    return val.strip().lower() in ("true", "1", "yes")


def _dec(val: str, default=None):
    try:
        return Decimal(val.strip()) if val.strip() else default
    except InvalidOperation:
        return default


def _int(val: str, default=None):
    try:
        return int(val.strip()) if val.strip() else default
    except ValueError:
        return default


class Command(BaseCommand):
    help = "Seed the database with scraped Invitation Homes property data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir", required=True,
            help="Path to the invitationhomes_nationwide_bundle_* directory",
        )
        parser.add_argument("--limit", type=int, default=None, help="Max properties per market")
        parser.add_argument(
            "--markets", default=None,
            help="Comma-separated market slugs to import (e.g. atlanta-georgia,miami-florida)",
        )
        parser.add_argument("--max-photos", type=int, default=8, help="Photos per property (default 8)")
        parser.add_argument(
            "--clear", action="store_true",
            help="Delete ALL existing properties, images, and amenities before seeding",
        )

    def handle(self, *args, **options):
        data_dir = options["data_dir"]
        limit = options["limit"]
        max_photos = options["max_photos"]
        market_filter = set(options["markets"].split(",")) if options["markets"] else None

        # Validate directory
        if not os.path.isdir(data_dir):
            raise CommandError(f"Directory not found: {data_dir}")

        def path(filename):
            return os.path.join(data_dir, filename)

        required = ["properties_core.csv", "property_amenities.csv", "property_photos.csv"]
        for f in required:
            if not os.path.exists(path(f)):
                raise CommandError(f"Missing required file: {f}")

        # ── Optionally clear ───────────────────────────────────────────────────
        if options["clear"]:
            self.stdout.write("Clearing existing properties, images, and amenities...")
            PropertyImage.objects.all().delete()
            PropertyAmenity.objects.all().delete()
            Property.objects.all().delete()

        # ── Load amenities lookup ──────────────────────────────────────────────
        self.stdout.write("Loading amenities CSV...")
        amenities_by_id = defaultdict(list)  # property_id → [(slug, name)]
        with open(path("property_amenities.csv"), encoding="utf-8") as f:
            for row in csv.DictReader(f):
                amenities_by_id[row["property_id"]].append(
                    (row["amenity_slug"].strip(), row["amenity_name"].strip())
                )

        # ── Load photos lookup ─────────────────────────────────────────────────
        self.stdout.write("Loading photos CSV...")
        photos_by_id = defaultdict(list)  # property_id → [(seq, is_primary, image_url)]
        with open(path("property_photos.csv"), encoding="utf-8") as f:
            for row in csv.DictReader(f):
                pid = row["property_id"]
                seq = _int(row.get("sequence", "0"), 0)
                is_primary = _bool(row.get("is_primary", "false"))
                image_url = row.get("image_url", "").strip()
                if image_url:
                    photos_by_id[pid].append((seq, is_primary, image_url))

        # Sort each property's photos by sequence and cap at max_photos
        for pid in photos_by_id:
            photos_by_id[pid] = sorted(photos_by_id[pid], key=lambda x: x[0])[:max_photos]

        # ── Ensure amenity categories exist ────────────────────────────────────
        self.stdout.write("Ensuring amenity categories...")
        cat_objs = {}
        for key, name, icon, order in CATEGORIES:
            obj, _ = AmenityCategory.objects.get_or_create(
                name=name,
                defaults={"icon": icon, "order": order},
            )
            cat_objs[key] = obj

        # ── Ensure agent exists ────────────────────────────────────────────────
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
            self.stdout.write("Agent user created.")

        # ── Existing slugs (skip duplicates unless --clear) ───────────────────
        existing_slugs = set(Property.objects.values_list("slug", flat=True))

        # ── Process properties ─────────────────────────────────────────────────
        self.stdout.write("Seeding properties...")
        market_counts: dict = defaultdict(int)
        total_props = total_amenities = total_images = 0

        with open(path("properties_core.csv"), encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = row["property_id"]
                # Strip "invh-" prefix and "+N" unit suffixes from slugs
                raw_slug = row["slug"].strip()
                slug = re.sub(r"^invh-", "", raw_slug)
                slug = re.sub(r"\+\d+", "", slug).replace("--", "-").strip("-")
                market_slug = row["market_slug"].strip()

                # Market filter
                if market_filter and market_slug not in market_filter:
                    continue

                # Per-market limit
                if limit and market_counts[market_slug] >= limit:
                    continue

                # Skip existing
                if slug in existing_slugs:
                    continue

                # ── Map fields ─────────────────────────────────────────────────
                beds = _int(row.get("beds", ""), 0) or 0
                baths = _dec(row.get("baths", ""), Decimal("0"))
                sqft = _int(row.get("square_footage", ""), 0) or 0
                raw_rent = _dec(row.get("rent", ""), Decimal("0"))
                # Reduce by 15% and round to the nearest $100
                if raw_rent and raw_rent > 0:
                    discounted = raw_rent * Decimal("0.85")
                    rent = Decimal(round(int(discounted) / 100) * 100)
                else:
                    rent = raw_rent
                year_built = _int(row.get("year_built", ""), None)
                lat = _dec(row.get("latitude", ""), None)
                lng = _dec(row.get("longitude", ""), None)
                is_new = _bool(row.get("active_is_new_construction", "false"))
                is_btr = _bool(row.get("is_btr_community", "false"))
                is_featured = _bool(row.get("is_featured_listing", "false"))
                community_raw = row.get("community", "").strip()
                try:
                    parsed = json.loads(community_raw)
                    community = parsed.get("name", "").strip() if isinstance(parsed, dict) else community_raw
                except (ValueError, TypeError):
                    community = community_raw
                if len(community) <= 4 or re.match(r"^invh", community, re.IGNORECASE):
                    community = ""
                market_name = row.get("market_name", "").strip()
                city = row.get("city", "").strip()
                state = row.get("state", "").strip()
                description = row.get("description", "").strip()
                virtual_tour = row.get("virtual_tour_url", "").strip()

                prop_type = "apartment" if is_btr else "house"
                type_label = TYPE_LABEL.get(prop_type, "Home")
                bed_label = "Studio" if beds == 0 else f"{beds}-Bed"
                address_1 = re.sub(r"\s*\+\d+\s*$", "", row.get("address_1", "").strip()).strip()
                # Use community name if present for a richer title, else street address
                if community:
                    title = f"{bed_label} {type_label} in {community}, {city}"
                elif address_1:
                    title = f"{bed_label} {type_label} at {address_1}, {city}"
                else:
                    title = f"{bed_label} {type_label} in {city}, {state}"

                # Garage: check amenities
                prop_amenities = amenities_by_id.get(pid, [])
                has_garage = any(slug_a == "garage" for slug_a, _ in prop_amenities)

                prop = Property.objects.create(
                    agent=agent,
                    slug=slug,
                    title=title,
                    description=description or f"A {bed_label.lower()} {type_label.lower()} available for rent in {city}, {state}.",
                    type=prop_type,
                    listing_type="for-rent",
                    status="available",
                    price=rent or Decimal("0"),
                    price_label="/mo",
                    bedrooms=beds,
                    bathrooms=baths,
                    sqft=sqft,
                    year_built=year_built,
                    garage=1 if has_garage else 0,
                    address=address_1,
                    city=city,
                    state=state,
                    zip_code=row.get("zip_code", "").strip(),
                    latitude=lat,
                    longitude=lng,
                    neighborhood=community or market_name,
                    condition="new" if is_new else "good",
                    virtual_tour_url=virtual_tour,
                    is_featured=is_featured,
                    is_published=True,
                )

                existing_slugs.add(slug)
                market_counts[market_slug] += 1
                total_props += 1

                # ── Amenities ──────────────────────────────────────────────────
                amenity_objs = []
                for amenity_slug, amenity_name in prop_amenities:
                    if amenity_slug == "garage":
                        continue  # already handled via garage field
                    cat_key = SLUG_TO_CAT.get(amenity_slug, "home")
                    amenity_objs.append(PropertyAmenity(
                        property=prop,
                        category=cat_objs[cat_key],
                        name=amenity_name,
                    ))
                if amenity_objs:
                    PropertyAmenity.objects.bulk_create(amenity_objs, batch_size=500, ignore_conflicts=True)
                    total_amenities += len(amenity_objs)

                # ── Images ─────────────────────────────────────────────────────
                photo_rows = photos_by_id.get(pid, [])
                image_objs = []
                for order, (seq, is_primary, image_url) in enumerate(photo_rows):
                    image_objs.append(PropertyImage(
                        property=prop,
                        image=image_url,
                        is_primary=is_primary,
                        order=order,
                    ))
                if image_objs:
                    PropertyImage.objects.bulk_create(image_objs, batch_size=500, ignore_conflicts=True)
                    total_images += len(image_objs)

                if total_props % 100 == 0:
                    self.stdout.write(f"  {total_props} properties seeded...")

        # ── Summary ────────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS(f"\n=== SEED COMPLETE ==="))
        self.stdout.write(self.style.SUCCESS(f"Properties : {total_props}"))
        self.stdout.write(self.style.SUCCESS(f"Amenities  : {total_amenities}"))
        self.stdout.write(self.style.SUCCESS(f"Images     : {total_images}"))
        self.stdout.write("\nMarkets imported:")
        for mkt, count in sorted(market_counts.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {mkt}: {count}")
