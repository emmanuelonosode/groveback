import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from pathlib import Path

import cloudinary.uploader
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role
from apps.properties.models import AmenityCategory, Property, PropertyAmenity, PropertyImage

User = get_user_model()

DATA_FILE = Path(__file__).parent / "data" / "nationwide_condos.json"

STATE_FIXES = {
    "Atlanta":      "GA",
    "Denver":       "CO",
    "Las Vegas":    "NV",
    "Nashville":    "TN",
    "Philadelphia": "PA",
    "San Diego":    "CA",
    "Seattle":      "WA",
}

AMENITY_CATEGORIES = [
    {"name": "Interior Features",    "icon": "home",        "order": 0},
    {"name": "Kitchen & Appliances", "icon": "utensils",    "order": 1},
    {"name": "Outdoor & Grounds",    "icon": "tree",        "order": 2},
    {"name": "Utilities & Climate",  "icon": "thermometer", "order": 3},
    {"name": "Parking & Storage",    "icon": "car",         "order": 4},
    {"name": "Security & Access",    "icon": "shield",      "order": 5},
    {"name": "Community & Building", "icon": "building-2",  "order": 6},
    {"name": "Pet Policy",           "icon": "paw-print",   "order": 7},
]


def _upload_image(task):
    prop_id, order, url = task
    stable_id = f"properties/nationwide/{prop_id}/{order}"
    try:
        result = cloudinary.uploader.upload(
            url,
            public_id=stable_id,
            resource_type="image",
            overwrite=False,
            unique_filename=False,
        )
        return (prop_id, order, result["public_id"], None)
    except Exception as exc:
        return (prop_id, order, None, str(exc))


class Command(BaseCommand):
    help = (
        "Import 1,000 nationwide condo listings with images and amenities. "
        "Images are uploaded to Cloudinary in parallel. "
        "Fixes scraper state code errors."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--published",
            action="store_true",
            default=False,
            help="Set is_published=True on all imported listings (default: False).",
        )
        parser.add_argument(
            "--agent-email",
            default="admin@haskerrealtygroup.com",
            help="Email of the agent to assign to all listings.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Stop after importing this many properties (0 = no limit).",
        )
        parser.add_argument(
            "--skip-images",
            action="store_true",
            default=False,
            help="Skip Cloudinary image upload.",
        )
        parser.add_argument(
            "--reset-images",
            action="store_true",
            default=False,
            help="Delete and re-upload images for properties that already have them.",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=20,
            help="Number of parallel Cloudinary upload workers (default: 20).",
        )

    def handle(self, *args, **options):
        is_published = options["published"]
        agent_email  = options["agent_email"]
        limit        = options["limit"]
        skip_images  = options["skip_images"]
        reset_images = options["reset_images"]
        workers      = options["workers"]

        # ── 1. Load data file ─────────────────────────────────────────────────
        if not DATA_FILE.exists():
            raise CommandError(f"Bundled data file not found: {DATA_FILE}")

        self.stdout.write(f"Loading {DATA_FILE} ...")
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)

        raw_props = data.get("properties", [])
        raw_imgs  = data.get("property_images", [])
        raw_ams   = data.get("property_amenities", [])

        if not raw_props:
            raise CommandError("No 'properties' array found in the JSON file.")

        self.stdout.write(
            f"Found {len(raw_props)} properties, "
            f"{len(raw_imgs)} images, "
            f"{len(raw_ams)} amenities."
        )

        if limit:
            limited_ids = {p["id"] for p in raw_props[:limit]}
            raw_props   = raw_props[:limit]
            raw_imgs    = [i for i in raw_imgs if i["property_id"] in limited_ids]
            raw_ams     = [a for a in raw_ams  if a["property_id"] in limited_ids]
            self.stdout.write(f"Limit {limit}: {len(raw_imgs)} images, {len(raw_ams)} amenities.")

        # ── 2. Build lookup dicts ─────────────────────────────────────────────
        images_by_prop: dict[str, list] = defaultdict(list)
        for img in raw_imgs:
            images_by_prop[img["property_id"]].append(img)

        amenities_by_prop: dict[str, list] = defaultdict(list)
        for am in raw_ams:
            amenities_by_prop[am["property_id"]].append(am)

        # ── 3. Resolve agent ──────────────────────────────────────────────────
        agent = None
        try:
            candidate = User.objects.get(email=agent_email)
            if candidate.role == Role.AGENT:
                agent = candidate
            else:
                self.stdout.write(self.style.WARNING(
                    f"  Warning: {agent_email} has role={candidate.role}, not AGENT. "
                    "Looking for an AGENT fallback..."
                ))
        except User.DoesNotExist:
            self.stdout.write(self.style.WARNING(
                f"  Warning: No user with email '{agent_email}'. "
                "Looking for any AGENT user..."
            ))

        if agent is None:
            agent = User.objects.filter(role=Role.AGENT).first()
            if agent is None:
                raise CommandError(
                    "No AGENT user found. Create one or pass --agent-email."
                )
            self.stdout.write(self.style.WARNING(f"  Fallback agent: {agent.email}"))

        self.stdout.write(f"Agent: {agent.get_full_name()} <{agent.email}>")

        # ── 4. Ensure amenity categories exist ────────────────────────────────
        cat_map: dict[str, AmenityCategory] = {}
        for cat_def in AMENITY_CATEGORIES:
            obj, _ = AmenityCategory.objects.get_or_create(
                name=cat_def["name"],
                defaults={"icon": cat_def["icon"], "order": cat_def["order"]},
            )
            cat_map[cat_def["name"]] = obj

        # ── 5. Upload images to Cloudinary in parallel ────────────────────────
        # public_id = properties/nationwide/{prop_id}/{order}
        # overwrite=False means re-runs reuse existing Cloudinary assets.
        cloudinary_map: dict[tuple, str] = {}  # (prop_id, order) -> public_id

        if not skip_images:
            tasks = [
                (img["property_id"], img["order"], img["image"])
                for img in raw_imgs
            ]
            total_tasks  = len(tasks)
            done = failed = 0

            self.stdout.write(
                f"Uploading {total_tasks} images to Cloudinary "
                f"({workers} parallel workers) ..."
            )

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_upload_image, t): t for t in tasks}
                for future in as_completed(futures):
                    prop_id, order, public_id, err = future.result()
                    if public_id:
                        cloudinary_map[(prop_id, order)] = public_id
                        done += 1
                    else:
                        failed += 1
                        self.stdout.write(self.style.WARNING(
                            f"  Upload failed ({prop_id} order={order}): {err}"
                        ))
                    total_done = done + failed
                    if total_done % 500 == 0:
                        self.stdout.write(
                            f"  [{total_done}/{total_tasks}] "
                            f"uploaded={done} failed={failed}"
                        )

            self.stdout.write(
                f"Upload complete: {done} succeeded, {failed} failed."
            )

        # ── 6. Import properties ──────────────────────────────────────────────
        created_count = skipped_count = fixed_states = 0
        images_added = amenities_added = 0

        for i, raw in enumerate(raw_props, start=1):
            prop_id = raw["id"]
            address = raw["address"]
            city    = raw["city"]
            state   = STATE_FIXES.get(raw["city"], raw["state"])
            if state != raw["state"]:
                fixed_states += 1

            existing = Property.objects.filter(address=address, city=city).first()

            if existing:
                prop      = existing
                has_imgs  = prop.images.exists()
                has_ams   = prop.amenities.exists()

                if has_imgs and not reset_images:
                    skipped_count += 1
                    if i % 100 == 0:
                        self.stdout.write(
                            f"  [{i}/{len(raw_props)}] "
                            f"created={created_count} skipped={skipped_count}"
                        )
                    continue

                if reset_images:
                    if has_imgs:
                        prop.images.all().delete()
                    if has_ams:
                        prop.amenities.all().delete()
            else:
                prop = Property.objects.create(
                    agent=agent,
                    is_published=is_published,
                    is_featured=raw.get("is_featured", False),
                    homepage_featured=raw.get("homepage_featured", False),
                    title=raw["title"],
                    description=raw["description"],
                    type=raw["type"],
                    listing_type=raw["listing_type"],
                    status=raw["status"],
                    condition=raw.get("condition", "good"),
                    price=Decimal(str(raw["price"])),
                    price_label=raw.get("price_label", ""),
                    bedrooms=raw.get("bedrooms", 1),
                    bathrooms=Decimal(str(raw.get("bathrooms", 1.0))),
                    sqft=raw.get("sqft", 0),
                    lot_size=Decimal(str(raw["lot_size"])) if raw.get("lot_size") else None,
                    year_built=raw.get("year_built"),
                    garage=raw.get("garage", 0),
                    stories=raw.get("stories", 1),
                    address=address,
                    city=city,
                    state=state,
                    zip_code=raw.get("zip_code", ""),
                    neighborhood=raw.get("neighborhood", ""),
                    cross_street=raw.get("cross_street", ""),
                    latitude=Decimal(str(raw["latitude"])) if raw.get("latitude") else None,
                    longitude=Decimal(str(raw["longitude"])) if raw.get("longitude") else None,
                    virtual_tour_url=raw.get("virtual_tour_url", ""),
                    tour_360_url=raw.get("tour_360_url", ""),
                )
                created_count += 1

            # ── Attach images ─────────────────────────────────────────────────
            if not skip_images:
                img_objs = []
                for img in images_by_prop.get(prop_id, []):
                    public_id = cloudinary_map.get((prop_id, img["order"]))
                    if public_id:
                        img_objs.append(PropertyImage(
                            property=prop,
                            image=public_id,
                            caption=img.get("caption", ""),
                            is_primary=img.get("is_primary", False),
                            order=img.get("order", 0),
                        ))
                if img_objs:
                    PropertyImage.objects.bulk_create(img_objs)
                    images_added += len(img_objs)

            # ── Attach amenities ──────────────────────────────────────────────
            am_objs = []
            for am in amenities_by_prop.get(prop_id, []):
                cat = cat_map.get(am.get("category"))
                if cat:
                    am_objs.append(PropertyAmenity(
                        property=prop,
                        category=cat,
                        name=am["name"],
                    ))
            if am_objs:
                PropertyAmenity.objects.bulk_create(am_objs, ignore_conflicts=True)
                amenities_added += len(am_objs)

            if i % 100 == 0:
                self.stdout.write(
                    f"  [{i}/{len(raw_props)}] "
                    f"created={created_count} skipped={skipped_count} "
                    f"images={images_added} amenities={amenities_added}"
                )

        # ── 7. Summary ────────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== IMPORT COMPLETE ==="))
        self.stdout.write(self.style.SUCCESS(f"Properties created : {created_count}"))
        self.stdout.write(self.style.SUCCESS(f"Properties skipped : {skipped_count}"))
        self.stdout.write(self.style.SUCCESS(f"State codes fixed  : {fixed_states}"))
        self.stdout.write(self.style.SUCCESS(f"Images added       : {images_added}"))
        self.stdout.write(self.style.SUCCESS(f"Amenities added    : {amenities_added}"))
        self.stdout.write(self.style.SUCCESS(f"Published          : {is_published}"))
        if not is_published:
            self.stdout.write(self.style.WARNING(
                "\nListings are unpublished. Review in admin then re-run with --published.\n"
                "Admin: https://admin.haskerrealtygroup.com/admin/properties/property/"
            ))
