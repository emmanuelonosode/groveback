"""
debug_rently.py — Fetch & inspect a small sample of Rently listings.

Does NOT write to the database unless --insert is passed.
Prints a full diagnostic report for each property:
  • raw API field names returned
  • cleaned description (Rently, prices, apply-now stripped)
  • image URL accessibility (HTTP HEAD)
  • tour / 360 URLs found
  • parsed amenities
  • final slug & title

Usage:
    python manage.py debug_rently
    python manage.py debug_rently --limit 5 --metro Dallas
    python manage.py debug_rently --limit 10 --insert   # actually seed these 10
"""

import re
import time
from decimal import Decimal, InvalidOperation

import requests
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils.text import slugify

from apps.accounts.models import Role
from apps.properties.models import (
    AmenityCategory, Property, PropertyAmenity, PropertyImage,
)

User = get_user_model()

# ── API ────────────────────────────────────────────────────────────────────────
BASE_URL = "https://r4vyup271c.execute-api.us-east-1.amazonaws.com/prod"
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":    "https://homes.rently.com/",
    "Origin":     "https://homes.rently.com",
})

PRICE_FACTOR = Decimal("0.74")

# ── Metro bboxes (subset for debug) ───────────────────────────────────────────
METRO_MAP = {
    "Atlanta":       (33.647946, -84.550854, 33.886823, -84.289560, 33.750127, -84.388520),
    "Dallas":        (32.617537, -97.478940, 33.016577, -96.554601, 32.776665, -96.796989),
    "Houston":       (29.523624, -95.788950, 30.110763, -95.013020, 29.760427, -95.369803),
    "Tampa":         (27.826087, -82.651970, 28.172020, -82.269581, 27.950575, -82.457178),
    "Phoenix":       (33.290023,-112.323975, 33.744167,-111.926105, 33.448376,-112.074036),
    "Charlotte":     (35.001080, -81.009518, 35.401220, -80.648100, 35.227087, -80.843127),
    "Nashville":     (35.966904, -87.055523, 36.406202, -86.516560, 36.174465, -86.767960),
    "Las Vegas":     (35.960011,-115.416925, 36.387000,-114.944978, 36.174969,-115.137421),
    "Orlando":       (28.355352, -81.611710, 28.695280, -81.124810, 28.538336, -81.379234),
    "Denver":        (39.614431,-105.109927, 39.914231,-104.598873, 39.739236,-104.984862),
}

# ── Description cleaning ───────────────────────────────────────────────────────
# Strip platform branding, raw prices, call-to-action language
_DESC_CLEAN = [
    # Platform name
    (re.compile(r'\bRently\b',              re.I), ''),
    (re.compile(r'\bhomes\.rently\.com\b',  re.I), ''),
    # Prices and rent mentions
    (re.compile(r'\$[\d,]+(?:\.\d{2})?(?:/mo(?:nth)?)?\b', re.I), ''),
    (re.compile(r'rent(?:ing|ed)?\s+for\s+\$[\d,]+', re.I), ''),
    # Apply / Application CTAs
    (re.compile(r'\bapply\s+now\b',         re.I), ''),
    (re.compile(r'\bapplying\b',            re.I), ''),
    (re.compile(r'\bapplication\s+fee\b',   re.I), ''),
    (re.compile(r'\bsubmit\s+an?\s+application\b', re.I), ''),
    (re.compile(r'\bschedule\s+a\s+(?:self[- ]guided\s+)?(?:tour|showing|viewing)\b', re.I), ''),
    (re.compile(r'\bself[- ]guided\s+tour\b', re.I), ''),
    (re.compile(r'\bcontact\s+us\s+to\s+(?:apply|schedule|tour|lease)\b', re.I), ''),
    (re.compile(r'\bvisit\s+(?:our\s+)?website\b', re.I), ''),
    # Clean up leftover punctuation artefacts and double-spaces
    (re.compile(r'\s{2,}'),                 ' '),
    (re.compile(r'(^|[.!?])\s*[,;]\s*'),   r'\1 '),
]

_CF_BASE = "https://d39tc8gklidfbm.cloudfront.net/images"
_S3_RE   = re.compile(r"https?://s3\.amazonaws\.com/[^/]+/images/(\d+)/")

TOUR_FIELDS = [
    "virtual_tour_url", "virtual_tour", "tour_url",
    "three_sixty_url", "tour_360", "matterport_url",
    "video_url", "tour_link", "media_tour_url",
    "inside_maps_url", "insidemaps_url", "zillow_3d_url",
    "kuula_url", "matterport", "tour",
]


def _clean_desc(text: str) -> str:
    if not text:
        return ""
    for pattern, replacement in _DESC_CLEAN:
        text = pattern.sub(replacement, text)
    return text.strip()


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    m = _S3_RE.match(url)
    if m:
        return f"{_CF_BASE}/{m.group(1)}/large"
    return url.replace("/thumb", "/large").replace("/medium", "/large")


def _photo_url(pic) -> str:
    """Extract a clean https:// URL from a Rently picture entry."""
    if isinstance(pic, str):
        url = _normalize_url(pic.strip())
    elif isinstance(pic, dict):
        raw = (
            pic.get("large_url") or pic.get("url") or
            pic.get("medium_url") or pic.get("src", "")
        )
        url = _normalize_url(str(raw).strip() if raw else "")
    else:
        return ""

    if not url:
        return ""
    # Normalise scheme — CloudinaryField must never receive protocol-relative URLs
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("http://"):
        url = "https://" + url[7:]
    elif not url.startswith("https://"):
        return ""  # Can't use this URL safely

    return url


def _get(url, params=None, timeout=25, retries=3):
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1.5 ** attempt)


def _dec(v, default=None):
    try:
        return Decimal(str(v).strip()) if str(v).strip() else default
    except (InvalidOperation, TypeError):
        return default


def _int(v, default=None):
    try:
        return int(str(v).strip()) if str(v).strip() else default
    except (ValueError, TypeError):
        return default


def _str(v, default=""):
    return str(v).strip() if v not in (None, "") else default


def _bool(v):
    return str(v).lower() in ("true", "1", "yes", "t")


def _adj_price(rent):
    try:
        return (Decimal(str(rent)) * PRICE_FACTOR).quantize(Decimal("1"))
    except (InvalidOperation, TypeError):
        return Decimal("0")


def _adj_address(address: str) -> str:
    m = re.match(r"^(\d+)(.*)", address.strip())
    return (str(int(m.group(1)) + 2) + m.group(2)) if m else address


def _parse_amenities(raw) -> list[tuple[str, str]]:
    if not raw:
        return []
    import json
    try:
        items = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return []
    out = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                name = _str(
                    item.get("name") or item.get("title") or
                    item.get("amenity_name") or item.get("label", "")
                )
                if name:
                    out.append((slugify(name), name))
            elif isinstance(item, str) and item.strip():
                out.append((slugify(item.strip()), item.strip()))
    elif isinstance(items, dict):
        for key, val in items.items():
            if val and val not in (False, 0, "0", "false"):
                name = key.replace("_", " ").replace("-", " ").title()
                out.append((slugify(key), name))
    return out


def _tour_urls(detail: dict) -> tuple[str, str]:
    """Return (virtual_tour_url, tour_360_url). Checks many possible field names."""
    found = []
    # Check all known tour field names
    for f in TOUR_FIELDS:
        val = _str(detail.get(f, ""))
        if val and val.startswith("http") and val not in found:
            found.append(val)
    # Also scan for any key containing 'tour', 'matterport', '360', 'virtual', 'inside'
    for key, val in detail.items():
        if isinstance(val, str) and val.startswith("http"):
            key_lower = key.lower()
            if any(kw in key_lower for kw in ("tour", "matterport", "360", "virtual", "inside", "kuula", "zillow3d")):
                if val not in found:
                    found.append(val)
    vt  = found[0] if found else ""
    t360 = found[1] if len(found) > 1 and found[1] != vt else ""
    return vt, t360


def _check_url(url: str, timeout: int = 6) -> tuple[bool, int, str]:
    """Return (ok, status_code, content_type)."""
    try:
        r = SESSION.head(url, timeout=timeout, allow_redirects=True)
        ct = r.headers.get("Content-Type", "")
        return r.status_code < 400, r.status_code, ct
    except Exception as e:
        return False, 0, str(e)


SLUG_TO_CAT = {
    "granite-countertops": "kitchen", "quartz-countertops": "kitchen",
    "stainless-steel-appliances": "kitchen", "dishwasher": "kitchen",
    "refrigerator": "kitchen", "microwave": "kitchen",
    "gas-stove": "kitchen", "kitchen-island": "kitchen",
    "gas-range": "kitchen", "double-oven": "kitchen", "wine-fridge": "kitchen",
    "garbage-disposal": "kitchen", "eat-in-kitchen": "kitchen",
    "w-d-hookups": "utility", "washer-dryer": "utility",
    "laundry-in-unit": "utility", "in-unit-laundry": "utility",
    "washer-dryer-hookup": "utility", "washer-dryer-included": "utility",
    "central-air": "utility", "central-heat": "utility",
    "air-conditioning": "utility", "smart-thermostat": "utility",
    "utilities-included": "utility", "air-filter-delivery": "utility",
    "high-speed-internet": "utility", "cable-ready": "utility",
    "ceiling-fans": "utility", "fireplace": "utility",
    "has-pool": "community", "community-pool": "community", "swimming-pool": "community",
    "patio": "community", "fenced-yard": "community", "private-yard": "community",
    "garage": "community", "gated-community": "community", "gated-access": "community",
    "fitness-center": "community", "gym": "community",
    "clubhouse": "community", "playground": "community",
    "basketball-court": "community", "tennis-court": "community",
    "dog-park": "community", "rooftop-deck": "community",
    "walking-trails": "community", "hoa": "community",
    "balcony": "community", "deck": "community", "storage": "community",
    "parking": "community", "covered-parking": "community", "carport": "community",
    "elevator": "community", "concierge": "community",
    "business-center": "community", "game-room": "community",
    "package-lockers": "community", "ev-charging": "community",
    "pet-friendly": "pet", "no-pets": "pet",
    "dogs-allowed": "pet", "cats-allowed": "pet",
    "pet-deposit": "pet", "pet-fee": "pet", "pet-rent": "pet",
    "large-dogs-ok": "pet", "small-dogs-ok": "pet",
}

CATEGORIES = [
    ("home",      "Home Features",         "Home",     0),
    ("kitchen",   "Kitchen Features",      "ChefHat",  1),
    ("utility",   "Utility & Maintenance", "Zap",      2),
    ("community", "Community Features",    "Users",    3),
    ("pet",       "Pet Policy",            "PawPrint", 4),
]

def _insert_images_raw(property_id: int, urls: list) -> int:
    """Insert images via raw SQL — bypasses CloudinaryField.to_python() which
    mangles cloudfront.net URLs by treating them as Cloudinary CDN addresses."""
    clean = [u for u in urls if u and u.startswith("https://")]
    if not clean:
        return 0
    q = connection.ops.quote_name
    sql = (
        f"INSERT INTO {q('properties_propertyimage')} "
        f"({q('property_id')}, {q('image')}, {q('caption')}, {q('is_primary')}, {q('order')}) "
        f"VALUES (%s, %s, %s, %s, %s)"
    )
    rows = [(property_id, url, "", i == 0, i) for i, url in enumerate(clean)]
    with connection.cursor() as cursor:
        cursor.executemany(sql, rows)
    return len(clean)


PROP_TYPE_MAP = {
    "house": "residential", "sfr": "residential",
    "condo": "condo", "townhouse": "townhouse",
    "apartment": "residential", "multi_family": "residential",
}


class Command(BaseCommand):
    help = "Fetch a small sample of Rently listings and print a full diagnostic report."

    def add_arguments(self, parser):
        parser.add_argument("--limit",  type=int, default=10, help="Properties to inspect (default 10)")
        parser.add_argument("--metro",  default="Atlanta", help="Metro to pull from (default Atlanta)")
        parser.add_argument("--insert", action="store_true", help="Actually insert into the DB after validation")
        parser.add_argument("--check-images", action="store_true", default=True,
                            help="HTTP HEAD each image URL to verify it resolves (default on)")
        parser.add_argument("--no-check-images", dest="check_images", action="store_false")
        parser.add_argument("--raw",    action="store_true",
                            help="Also dump the raw API response keys for each property")

    def handle(self, *args, **options):
        limit        = options["limit"]
        metro        = options["metro"]
        do_insert    = options["insert"]
        check_images = options["check_images"]
        show_raw     = options["raw"]

        bbox = METRO_MAP.get(metro)
        if not bbox:
            available = ", ".join(METRO_MAP.keys())
            self.stderr.write(f"Unknown metro '{metro}'. Available: {available}")
            return
        sw_lat, sw_lng, ne_lat, ne_lng, c_lat, c_lng = bbox

        self.stdout.write(f"\n{'═'*70}")
        self.stdout.write(f"  Rently Debug Inspector — {metro} — limit {limit}")
        self.stdout.write(f"{'═'*70}\n")

        # ── 1. Pull listing page ──────────────────────────────────────────────
        self.stdout.write("▶ Fetching listing page...")
        try:
            data = _get(f"{BASE_URL}/api/searchQueryNew", params={
                "rentalType": "0", "pc": "1",
                "smart_match": "false", "from_web": "true",
                "city_filter": metro,
                "latitude1": sw_lat, "longitude1": sw_lng,
                "latitude2": ne_lat, "longitude2": ne_lng,
                "searchLatitude": c_lat, "searchLongitude": c_lng,
            })
        except Exception as e:
            self.stderr.write(f"  ERROR fetching listing page: {e}")
            return

        listings = data.get("property_data", []) + data.get("nearest_property_data", [])
        self.stdout.write(f"  API returned {len(listings)} listings for {metro}")

        if show_raw and listings:
            self.stdout.write(f"\n  Sample listing-level keys: {list(listings[0].keys())}")

        # ── 2. Pick up to `limit` unique IDs ─────────────────────────────────
        seen   = set()
        sample = []
        for p in listings:
            pid = p.get("id")
            if pid and pid not in seen:
                seen.add(pid)
                sample.append(p)
            if len(sample) >= limit:
                break

        self.stdout.write(f"  Inspecting {len(sample)} properties...\n")

        # ── 3. Setup for optional insert ──────────────────────────────────────
        if do_insert:
            cat_objs = {}
            for key, name, icon, order in CATEGORIES:
                obj, _ = AmenityCategory.objects.get_or_create(
                    name=name, defaults={"icon": icon, "order": order},
                )
                cat_objs[key] = obj

            agent, created = User.objects.get_or_create(
                email="agent@haskerrealtygroup.com",
                defaults={
                    "first_name": "Marcus", "last_name": "Reid",
                    "role": Role.AGENT, "phone": "(757) 555-0101",
                },
            )
            if created:
                agent.set_password("Agent1234!")
                agent.save()

            existing_slugs = set(Property.objects.values_list("slug", flat=True))
            inserted = 0

        # ── 4. Per-property inspection ────────────────────────────────────────
        for idx, listing in enumerate(sample, 1):
            pid = listing.get("id")
            self.stdout.write(f"{'─'*70}")
            self.stdout.write(f"[{idx}/{len(sample)}] Property ID: {pid}")

            # ── Fetch detail ──────────────────────────────────────────────────
            try:
                detail_resp = _get(f"{BASE_URL}/api/propertyDetails/{pid}", timeout=25)
                detail = detail_resp.get("property") or detail_resp
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Detail fetch failed: {e}"))
                detail = {}

            if show_raw:
                self.stdout.write(f"  Detail keys: {list(detail.keys())}")

            # ── Extract fields ────────────────────────────────────────────────
            fp         = listing.get("floorplan", {})
            beds       = _int(detail.get("bedrooms")   or fp.get("bedrooms"), 0) or 0
            baths      = _dec(detail.get("bathrooms")  or fp.get("bathrooms"), Decimal("1"))
            sqft       = _int(detail.get("size")       or fp.get("size"), 0) or 0
            rent       = detail.get("price")            or fp.get("rent") or 0
            year_built = _int(detail.get("year_built") or detail.get("year"), None)
            raw_addr   = _str(detail.get("address")    or detail.get("street_address")
                              or listing.get("address", ""))
            city       = _str(detail.get("city")       or listing.get("city", ""))
            raw_state  = _str(detail.get("state")      or listing.get("state", "")).upper()
            zipcode    = _str(detail.get("zipcode")    or detail.get("zip", ""))
            lat        = _dec(detail.get("latitude")   or listing.get("latitude"))
            lng        = _dec(detail.get("longitude")  or listing.get("longitude"))
            deposit    = _dec(detail.get("deposit"), None)
            raw_desc   = _str(detail.get("description") or listing.get("headline", ""))
            neighborhood = _str(detail.get("neighborhood") or detail.get("community_name", ""))
            prop_type  = PROP_TYPE_MAP.get(_str(listing.get("type", "")).lower(), "residential")
            lot_size   = _dec(detail.get("lot_size") or detail.get("lot"), None)
            stories    = _int(detail.get("stories") or detail.get("floors"), None)

            adj_price = _adj_price(rent)
            adj_addr  = _adj_address(raw_addr) if raw_addr else ""
            bed_label = "Studio" if beds == 0 else f"{beds}-Bed"

            # ── Title ─────────────────────────────────────────────────────────
            title = (
                f"{bed_label} Home at {adj_addr}, {city}" if adj_addr and city else
                f"{bed_label} Home at {adj_addr}"          if adj_addr else
                f"{bed_label} Home in {city}, {raw_state}" if city else
                f"{bed_label} Rental Home"
            )

            # ── Description cleaning ──────────────────────────────────────────
            clean_desc = _clean_desc(raw_desc)
            if not clean_desc:
                clean_desc = (
                    f"A well-maintained {bed_label.lower()} home available for rent in "
                    f"{city}, {raw_state}."
                    + (f" Built in {year_built}." if year_built else "")
                    + (f" Security deposit: ${int(deposit):,}." if deposit else "")
                )

            # ── Slug ──────────────────────────────────────────────────────────
            base_slug = slugify(raw_addr)[:250] if raw_addr else slugify(f"{city} {raw_state} {pid}")[:250]
            slug      = base_slug

            # ── Virtual tours ─────────────────────────────────────────────────
            vt_url, t360_url = _tour_urls(detail)

            # ── Amenities ─────────────────────────────────────────────────────
            parsed_amen = _parse_amenities(detail.get("amenities", ""))
            pet_amen = []
            if _bool(fp.get("dog"))  or _bool(detail.get("allow_dog")):
                pet_amen.append(("dogs-allowed", "Dogs Allowed"))
            if _bool(fp.get("cat"))  or _bool(detail.get("allow_cat")):
                pet_amen.append(("cats-allowed", "Cats Allowed"))
            if _bool(fp.get("no_pet")) or _bool(detail.get("no_pets")):
                pet_amen.append(("no-pets", "No Pets"))

            seen_amen = set()
            all_amen  = []
            for s, n in parsed_amen + pet_amen:
                if s not in seen_amen:
                    seen_amen.add(s)
                    all_amen.append((s, n))
            has_garage = "garage" in seen_amen

            # ── Photos ────────────────────────────────────────────────────────
            pictures = detail.get("pictures", [])
            if not pictures and listing.get("picture"):
                pictures = [listing["picture"]]

            photo_urls = []
            for pic in pictures:
                u = _photo_url(pic)
                if u:
                    photo_urls.append(u)

            # ── Print report ──────────────────────────────────────────────────
            ok   = self.style.SUCCESS("✓")
            warn = self.style.WARNING("⚠")
            err  = self.style.ERROR("✗")

            self.stdout.write(f"\n  TITLE    : {title}")
            self.stdout.write(f"  SLUG     : {slug}")
            self.stdout.write(f"  ADDRESS  : {adj_addr or '(none)'}  ←raw: {raw_addr or '(none)'}")
            self.stdout.write(f"  CITY/ST  : {city}, {raw_state}  {zipcode}")
            self.stdout.write(f"  LAT/LNG  : {lat}, {lng}")
            self.stdout.write(f"  TYPE     : {prop_type}")
            self.stdout.write(f"  BEDS/BATH: {beds} bed / {baths} bath")
            self.stdout.write(f"  SQFT     : {sqft or '(none)'}")
            self.stdout.write(f"  PRICE    : raw={rent}  →  adjusted=${adj_price}/mo")
            self.stdout.write(f"  YEAR     : {year_built or '(none)'}")
            self.stdout.write(f"  LOT SIZE : {lot_size or '(none)'} acres")
            self.stdout.write(f"  STORIES  : {stories or '(none)'}")
            self.stdout.write(f"  DEPOSIT  : ${int(deposit):,}" if deposit else "  DEPOSIT  : (none)")
            self.stdout.write(f"  GARAGE   : {'yes' if has_garage else 'no'}")
            self.stdout.write(f"  NEIGHBOR : {neighborhood or '(none)'}")

            self.stdout.write(f"\n  DESC (raw)  : {raw_desc[:120]}..." if len(raw_desc) > 120 else f"\n  DESC (raw)  : {raw_desc or '(empty)'}")
            self.stdout.write(f"  DESC (clean): {clean_desc[:120]}..." if len(clean_desc) > 120 else f"  DESC (clean): {clean_desc or '(empty)'}")

            self.stdout.write(f"\n  TOUR (virtual_tour_url): {vt_url or '(none)'}")
            self.stdout.write(f"  TOUR (tour_360_url)    : {t360_url or '(none)'}")

            self.stdout.write(f"\n  AMENITIES ({len(all_amen)} total):")
            if all_amen:
                for s, n in all_amen:
                    cat = SLUG_TO_CAT.get(s, "home")
                    self.stdout.write(f"    [{cat:10}] {n} ({s})")
            else:
                self.stdout.write(f"    (none parsed)")

            self.stdout.write(f"\n  PHOTOS ({len(photo_urls)} found):")
            for i, url in enumerate(photo_urls[:5]):  # Show first 5
                if check_images:
                    reachable, status, ct = _check_url(url)
                    icon = ok if reachable else err
                    self.stdout.write(f"    {icon} [{i}] {status} {ct[:30]:30} {url}")
                else:
                    self.stdout.write(f"    [{i}] {url}")
            if len(photo_urls) > 5:
                self.stdout.write(f"    ... and {len(photo_urls) - 5} more photos")

            # ── Optional insert ───────────────────────────────────────────────
            if do_insert:
                if slug in existing_slugs:
                    self.stdout.write(self.style.WARNING(f"\n  → SKIP: slug already exists"))
                else:
                    try:
                        prop = Property.objects.create(
                            agent=agent, slug=slug,
                            title=title, description=clean_desc,
                            type=prop_type, listing_type="for-rent", status="available",
                            price=adj_price, price_label="/mo",
                            bedrooms=beds, bathrooms=baths or Decimal("1"), sqft=sqft,
                            year_built=year_built,
                            lot_size=lot_size,
                            stories=stories or 1,
                            garage=1 if has_garage else 0,
                            address=adj_addr, city=city, state=raw_state, zip_code=zipcode,
                            latitude=lat, longitude=lng,
                            neighborhood=neighborhood,
                            virtual_tour_url=vt_url,
                            tour_360_url=t360_url,
                            condition="good", cross_street="rently", is_published=True,
                        )
                        existing_slugs.add(slug)
                        inserted += 1

                        # Amenities
                        amen_objs = [
                            PropertyAmenity(
                                property=prop,
                                category=cat_objs[SLUG_TO_CAT.get(s, "home")],
                                name=n,
                            )
                            for s, n in all_amen if s != "garage"
                        ]
                        if amen_objs:
                            PropertyAmenity.objects.bulk_create(
                                amen_objs, batch_size=200, ignore_conflicts=True
                            )

                        # Images — raw SQL bypasses CloudinaryField URL mangling
                        n_images = _insert_images_raw(prop.id, photo_urls)

                        self.stdout.write(self.style.SUCCESS(
                            f"\n  ✓ INSERTED: pk={prop.pk}  amenities={len(amen_objs)}  images={n_images}"
                        ))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"\n  ✗ INSERT FAILED: {e}"))

            self.stdout.write("")  # spacing

        # ── Summary ───────────────────────────────────────────────────────────
        self.stdout.write(f"{'═'*70}")
        self.stdout.write(f"  Inspection complete. {len(sample)} properties reviewed.")
        if do_insert:
            self.stdout.write(self.style.SUCCESS(f"  {inserted} properties inserted into the database."))
        else:
            self.stdout.write("  Run with --insert to write these to the database.")
        self.stdout.write(f"{'═'*70}\n")
