"""
seed_rently.py — Seed the database directly from the Rently.com public API.

Streams SFR homes metro-by-metro (never accumulates more than --batch-size
records in RAM) and fetches apartment communities per bbox. Maps every field
the Property / PropertyImage / PropertyAmenity schema supports, including
virtual tour URLs, year built, lot size, deposit, and full amenity sets.

Usage:
    python manage.py seed_rently
    python manage.py seed_rently --skip-communities
    python manage.py seed_rently --skip-sfr
    python manage.py seed_rently --state TX
    python manage.py seed_rently --clear          # delete all for-rent first
    python manage.py seed_rently --batch-size 100 --workers 4
    python manage.py seed_rently --skip-details   # fast run, listing data only
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# ── Description cleaning ───────────────────────────────────────────────────────
_DESC_CLEAN = [
    (re.compile(r'\bRently\b',              re.I), ''),
    (re.compile(r'\bhomes\.rently\.com\b',  re.I), ''),
    (re.compile(r'\$[\d,]+(?:\.\d{2})?(?:/mo(?:nth)?)?\b', re.I), ''),
    (re.compile(r'rent(?:ing|ed)?\s+for\s+\$[\d,]+', re.I), ''),
    (re.compile(r'\bapply\s+now\b',         re.I), ''),
    (re.compile(r'\bapplying\b',            re.I), ''),
    (re.compile(r'\bapplication\s+fee\b',   re.I), ''),
    (re.compile(r'\bsubmit\s+an?\s+application\b', re.I), ''),
    (re.compile(r'\bschedule\s+a\s+(?:self[- ]guided\s+)?(?:tour|showing|viewing)\b', re.I), ''),
    (re.compile(r'\bself[- ]guided\s+tour\b', re.I), ''),
    (re.compile(r'\bcontact\s+us\s+to\s+(?:apply|schedule|tour|lease)\b', re.I), ''),
    (re.compile(r'\bvisit\s+(?:our\s+)?website\b', re.I), ''),
    (re.compile(r'\s{2,}'),                 ' '),
]


def _clean_desc(text: str) -> str:
    if not text:
        return ""
    for pattern, replacement in _DESC_CLEAN:
        text = pattern.sub(replacement, text)
    return text.strip()


def _insert_images_raw(property_id: int, urls: list) -> int:
    """Insert property images via raw SQL, bypassing CloudinaryField entirely.

    CloudinaryField.to_python() recognises cloudfront.net as a Cloudinary CDN
    domain and mangles the URL at assignment time — before it even reaches the
    database. Writing directly through the DB cursor stores the string as-is.
    """
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

User = get_user_model()

# ── API ────────────────────────────────────────────────────────────────────────
BASE_URL = "https://r4vyup271c.execute-api.us-east-1.amazonaws.com/prod"
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":    "https://homes.rently.com/",
    "Origin":     "https://homes.rently.com",
})

# ── Price & address display transforms ────────────────────────────────────────
PRICE_FACTOR = Decimal("0.74")   # −26 % off Rently asking price


def _adj_price(rent):
    try:
        return (Decimal(str(rent)) * PRICE_FACTOR).quantize(Decimal("1"))
    except (InvalidOperation, TypeError):
        return Decimal("0")


def _adj_address(address: str) -> str:
    """Increment the street number by 2 (light display obfuscation)."""
    m = re.match(r"^(\d+)(.*)", address.strip())
    return (str(int(m.group(1)) + 2) + m.group(2)) if m else address


# ── 78 US metro bounding boxes ────────────────────────────────────────────────
METROS = [
    # (city_name, sw_lat, sw_lng, ne_lat, ne_lng, center_lat, center_lng)
    ("Atlanta",          33.647946, -84.550854, 33.886823, -84.289560, 33.750127, -84.388520),
    ("Austin",           30.098659, -97.938376, 30.516863, -97.569459, 30.267153, -97.743061),
    ("Charlotte",        35.001080, -81.009518, 35.401220, -80.648100, 35.227087, -80.843127),
    ("Dallas",           32.617537, -97.478940, 33.016577, -96.554601, 32.776665, -96.796989),
    ("Denver",           39.614431,-105.109927, 39.914231,-104.598873, 39.739236,-104.984862),
    ("Houston",          29.523624, -95.788950, 30.110763, -95.013020, 29.760427, -95.369803),
    ("Jacksonville",     30.102099, -81.994293, 30.584600, -81.391620, 30.332184, -81.655651),
    ("Las Vegas",        35.960011,-115.416925, 36.387000,-114.944978, 36.174969,-115.137421),
    ("Miami",            25.594089, -80.873516, 25.979434, -80.119893, 25.761680, -80.191790),
    ("Nashville",        35.966904, -87.055523, 36.406202, -86.516560, 36.174465, -86.767960),
    ("Orlando",          28.355352, -81.611710, 28.695280, -81.124810, 28.538336, -81.379234),
    ("Phoenix",          33.290023,-112.323975, 33.744167,-111.926105, 33.448376,-112.074036),
    ("Raleigh",          35.712600, -78.998379, 36.074540, -78.574371, 35.779590, -78.638179),
    ("San Antonio",      29.284437, -98.774048, 29.717788, -98.294136, 29.424122, -98.493629),
    ("Tampa",            27.826087, -82.651970, 28.172020, -82.269581, 27.950575, -82.457178),
    ("Seattle",          47.481600,-122.435960, 47.734100,-122.224200, 47.606209,-122.332071),
    ("Portland",         45.432200,-122.836700, 45.653900,-122.471600, 45.523064,-122.676483),
    ("Sacramento",       38.394600,-121.552900, 38.685200,-121.323500, 38.575764,-121.478851),
    ("Salt Lake City",   40.699800,-112.101600, 40.852700,-111.739700, 40.760780,-111.891047),
    ("Tucson",           31.966800,-111.097900, 32.459300,-110.683600, 32.222607,-110.974709),
    ("Albuquerque",      34.978400,-106.886900, 35.218300,-106.468700, 35.084386,-106.650422),
    ("Boise",            43.494100,-116.423500, 43.691700,-116.100200, 43.615021,-116.202317),
    ("Spokane",          47.578400,-117.556700, 47.749800,-117.273100, 47.658779,-117.426047),
    ("Omaha",            41.194400, -96.240900, 41.402600, -95.893900, 41.256537, -95.934503),
    ("Kansas City",      38.836500, -94.774600, 39.337700, -94.404600, 39.099727, -94.578567),
    ("St Louis",         38.530000, -90.320600, 38.774100, -90.182000, 38.627003, -90.199402),
    ("Indianapolis",     39.634100, -86.326200, 39.927000, -85.946700, 39.768402, -86.158068),
    ("Columbus",         39.862900, -83.200000, 40.157100, -82.770900, 39.961176, -82.998794),
    ("Cincinnati",       39.035800, -84.696400, 39.254200, -84.356100, 39.103118, -84.512020),
    ("Cleveland",        41.390300, -81.870900, 41.599700, -81.533000, 41.499320, -81.694361),
    ("Pittsburgh",       40.363200, -80.095300, 40.501100, -79.866400, 40.440625, -79.995888),
    ("Louisville",       38.095900, -85.945600, 38.379900, -85.594200, 38.252665, -85.758456),
    ("Memphis",          34.994400, -90.133900, 35.268700, -89.651900, 35.149634, -90.048980),
    ("Richmond",         37.396300, -77.601700, 37.590200, -77.310800, 37.540726, -77.436047),
    ("Virginia Beach",   36.665200, -76.076500, 36.936600, -75.864000, 36.852924, -75.977985),
    ("Baltimore",        39.197200, -76.711300, 39.372200, -76.529100, 39.290385, -76.612190),
    ("Washington DC",    38.791645, -77.119759, 38.995853, -76.909393, 38.907192, -77.036871),
    ("Philadelphia",     39.867004, -75.280303, 40.137992, -74.955763, 39.952584, -75.165222),
    ("New York",         40.477399, -74.259090, 40.917577, -73.700009, 40.712776, -74.005974),
    ("Boston",           42.227900, -71.191130, 42.396800, -70.923300, 42.360082, -71.058880),
    ("Chicago",          41.644600, -87.940100, 42.023100, -87.524000, 41.878114, -87.629798),
    ("Detroit",          42.255200, -83.287900, 42.452600, -82.910400, 42.331427, -83.045754),
    ("Minneapolis",      44.889900, -93.329000, 45.051400, -93.004100, 44.977753, -93.265011),
    ("Milwaukee",        42.921400, -87.999000, 43.192400, -87.860400, 43.038902, -87.906474),
    ("New Orleans",      29.864800, -90.139400, 30.069600, -89.614800, 29.951065, -90.071533),
    ("Birmingham",       33.368300, -86.999500, 33.597600, -86.711600, 33.520661, -86.802490),
    ("Huntsville",       34.601400, -86.698600, 34.839900, -86.441900, 34.730369, -86.586098),
    ("Mobile",           30.591200, -88.200500, 30.756500, -88.023100, 30.695366, -88.039893),
    ("Greenville",       34.761700, -82.497900, 34.934200, -82.310500, 34.852619, -82.394012),
    ("Columbia SC",      33.942100, -81.205800, 34.103600, -80.934600, 34.000343, -81.034814),
    ("Myrtle Beach",     33.617100, -78.952200, 33.804400, -78.809300, 33.688721, -78.886925),
    ("Wilmington NC",    34.099400, -77.979800, 34.302100, -77.807200, 34.225726, -77.944710),
    ("Fayetteville NC",  35.008900, -79.108900, 35.184800, -78.830900, 35.052664, -78.878358),
    ("Greensboro",       36.004700, -79.907200, 36.188300, -79.700700, 36.072636, -79.791975),
    ("Durham",           35.946200, -79.058400, 36.067900, -78.826300, 35.994034, -78.898619),
    ("Knoxville",        35.885100, -84.218000, 36.053300, -83.847300, 35.960638, -83.920739),
    ("Chattanooga",      34.994200, -85.445800, 35.132600, -85.177300, 35.045631, -85.308960),
    ("Savannah",         31.991200, -81.222400, 32.152900, -81.029300, 32.083541, -81.099834),
    ("Augusta",          33.326800, -82.212900, 33.537400, -81.902800, 33.474062, -81.974649),
    ("Macon",            32.780300, -83.768100, 32.944200, -83.562000, 32.840695, -83.632402),
    ("Columbus GA",      32.360200, -85.007900, 32.604500, -84.897600, 32.460976, -84.987709),
    ("Fort Worth",       32.619900, -97.475800, 32.990800, -97.183100, 32.755490, -97.330765),
    ("San Jose",         37.134000,-122.058000, 37.469200,-121.588700, 37.338208,-121.886329),
    ("Los Angeles",      33.703000,-118.668200, 34.337000,-118.155300, 34.052235,-118.243683),
    ("San Diego",        32.534400,-117.282000, 32.971500,-116.905900, 32.715738,-117.161084),
    ("Fresno",           36.653800,-119.935100, 36.886200,-119.659500, 36.746842,-119.772591),
    ("Bakersfield",      35.272800,-119.187200, 35.449300,-118.836300, 35.373292,-119.018712),
    ("Colorado Springs", 38.781500,-104.874300, 38.993000,-104.688000, 38.833882,-104.821363),
    ("Fort Collins",     40.480100,-105.161800, 40.634600,-105.010600, 40.585260,-105.084423),
    ("Pueblo",           38.231800,-104.708200, 38.337700,-104.573600, 38.254450,-104.609140),
    ("Tulsa",            35.942500, -96.119900, 36.239400, -95.751900, 36.153982, -95.992775),
    ("Oklahoma City",    35.333900, -97.671100, 35.594200, -97.282500, 35.467560, -97.516428),
    ("Little Rock",      34.619600, -92.499100, 34.804700, -92.175000, 34.746481, -92.289596),
    ("Jackson MS",       32.218200, -90.275000, 32.424900, -90.068900, 32.298757, -90.184776),
    ("Lexington",        37.934700, -84.622800, 38.085800, -84.408500, 38.040584, -84.503716),
    ("Baton Rouge",      30.341500, -91.218200, 30.569300, -90.985300, 30.451465, -91.154551),
    ("Shreveport",       32.375900, -93.889600, 32.566100, -93.699700, 32.525152, -93.750179),
    ("Allentown",        40.541800, -75.636200, 40.651400, -75.436700, 40.608431, -75.490900),
    ("Harrisburg",       40.248900, -76.964200, 40.353300, -76.836600, 40.273788, -76.884716),
]

# ── Amenity slug → category key ───────────────────────────────────────────────
SLUG_TO_CAT = {
    # kitchen
    "granite-countertops": "kitchen", "quartz-countertops": "kitchen",
    "stainless-steel-appliances": "kitchen", "dishwasher": "kitchen",
    "refrigerator": "kitchen", "microwave": "kitchen",
    "gas-stove": "kitchen", "kitchen-island": "kitchen",
    "gas-range": "kitchen", "double-oven": "kitchen", "wine-fridge": "kitchen",
    "garbage-disposal": "kitchen", "eat-in-kitchen": "kitchen",
    # utility
    "w-d-hookups": "utility", "washer-dryer": "utility",
    "laundry-in-unit": "utility", "in-unit-laundry": "utility",
    "washer-dryer-hookup": "utility", "washer-dryer-included": "utility",
    "central-air": "utility", "central-heat": "utility",
    "air-conditioning": "utility", "smart-thermostat": "utility",
    "utilities-included": "utility", "air-filter-delivery": "utility",
    "high-speed-internet": "utility", "cable-ready": "utility",
    "ceiling-fans": "utility", "fireplace": "utility",
    # community
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
    # pet
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

PROP_TYPE_MAP = {
    "house": "residential", "sfr": "residential",
    "condo": "condo", "townhouse": "townhouse",
    "apartment": "residential", "multi_family": "residential",
}

# Virtual-tour field names Rently might use (checked in order)
TOUR_FIELDS = [
    "virtual_tour_url", "virtual_tour", "tour_url",
    "three_sixty_url", "tour_360", "matterport_url",
    "video_url", "tour_link", "media_tour_url",
    "inside_maps_url", "insidemaps_url", "zillow_3d_url",
    "kuula_url", "matterport", "tour",
]


# ── HTTP helper ───────────────────────────────────────────────────────────────
def _get(url, params=None, timeout=20, retries=3):
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1.5 ** attempt)


# ── Value coercions ───────────────────────────────────────────────────────────
def _str(v, default=""):
    return str(v).strip() if v not in (None, "") else default


def _int(v, default=None):
    try:
        return int(str(v).strip()) if str(v).strip() else default
    except (ValueError, TypeError):
        return default


def _dec(v, default=None):
    try:
        return Decimal(str(v).strip()) if str(v).strip() else default
    except (InvalidOperation, TypeError):
        return default


def _bool(v):
    return str(v).lower() in ("true", "1", "yes", "t")


def _tour_url(detail: dict) -> tuple[str, str]:
    """Return (virtual_tour_url, tour_360_url) from a detail dict.
    Checks all known tour field names AND scans every key for tour-related keywords.
    """
    found = []
    # Check known field names first
    for f in TOUR_FIELDS:
        val = _str(detail.get(f, ""))
        if val and val.startswith("http") and val not in found:
            found.append(val)
    # Scan all keys for anything tour-like
    for key, val in detail.items():
        if isinstance(val, str) and val.startswith("http"):
            key_lower = key.lower()
            if any(kw in key_lower for kw in ("tour", "matterport", "360", "virtual", "inside", "kuula")):
                if val not in found:
                    found.append(val)
    vt   = found[0] if found else ""
    t360 = found[1] if len(found) > 1 and found[1] != vt else ""
    return vt, t360


def _parse_amenities(raw) -> list[tuple[str, str]]:
    """Parse Rently amenities JSON string → [(slug, display_name)]."""
    if not raw:
        return []
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


_CF_BASE = "https://d39tc8gklidfbm.cloudfront.net/images"
_S3_RE   = re.compile(r"https?://s3\.amazonaws\.com/[^/]+/images/(\d+)/")


def _normalize_url(url: str) -> str:
    """Convert Rently S3 URLs → CloudFront equivalents (CloudinaryField-safe).
    S3 URLs (https://s3.amazonaws.com/Rently_dev/images/{id}/large_watermarked)
    get mangled by Django's CloudinaryField because it treats s3.amazonaws.com
    as a Cloudinary S3-backend host and strips the path. CloudFront URLs are
    plain CDN links and store/retrieve without issue.
    """
    if not url:
        return ""
    m = _S3_RE.match(url)
    if m:
        return f"{_CF_BASE}/{m.group(1)}/large"
    # Also normalise thumb → large for the slim listing fallback
    return url.replace("/thumb", "/large")


def _photo_url(pic) -> str:
    """Extract a clean https:// image URL from a Rently picture entry.

    Rently API picture objects may be strings or dicts.
    We always prefer large_url > url > medium_url > src.
    We reject anything that doesn't resolve to a full https:// URL so that
    CloudinaryField never receives a protocol-relative or partial URL
    (which would cause build_url() to produce a garbled CDN address).
    """
    if isinstance(pic, str):
        url = _normalize_url(pic.strip())
    elif isinstance(pic, dict):
        raw = _str(
            pic.get("large_url") or pic.get("url") or
            pic.get("medium_url") or pic.get("src", "")
        )
        url = _normalize_url(raw)
    else:
        return ""

    # Reject protocol-relative, empty, or non-http URLs
    if not url or not url.startswith("https://"):
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("http://"):
            url = "https://" + url[7:]
        else:
            return ""  # Unparseable — skip this image

    return url


def _make_slug(pid, address, city, state) -> str:
    if address and address.strip():
        base = address.strip()
    elif city:
        base = f"{city} {state} {pid}"
    else:
        base = str(pid)
    return slugify(base)[:250]


def _unique_slug(base, existing, fallback_id) -> str:
    if base not in existing:
        return base
    candidate = f"{base}-{fallback_id}"[:250]
    if candidate in existing:
        candidate = slugify(f"{base} {fallback_id} r")[:250]
    return candidate


# ─────────────────────────────────────────────────────────────────────────────
class Command(BaseCommand):
    help = "Seed from the Rently public API — streams batches to keep RAM flat."

    def add_arguments(self, parser):
        parser.add_argument("--skip-sfr",         action="store_true")
        parser.add_argument("--skip-communities",  action="store_true")
        parser.add_argument("--skip-details",      action="store_true",
                            help="Skip full detail fetch (faster, fewer fields)")
        parser.add_argument("--state",    default=None,
                            help="Only import this state (2-letter code, e.g. GA)")
        parser.add_argument("--limit",    type=int, default=None,
                            help="Stop after this many total properties inserted")
        parser.add_argument("--batch-size", type=int, default=150,
                            help="SFR IDs per fetch+insert cycle (RAM control, default 150)")
        parser.add_argument("--workers",  type=int, default=6,
                            help="Parallel detail-fetch threads per batch (default 6)")
        parser.add_argument("--clear",    action="store_true",
                            help="Delete all for-rent properties before seeding")

    # ── Main ──────────────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        skip_sfr         = options["skip_sfr"]
        skip_communities = options["skip_communities"]
        skip_details     = options["skip_details"]
        state_filter     = options["state"].upper() if options["state"] else None
        limit            = options["limit"]
        batch_size       = options["batch_size"]
        workers          = options["workers"]

        # ── Clear ─────────────────────────────────────────────────────────────
        if options["clear"]:
            qs = Property.objects.filter(cross_street="rently")
            n = qs.count()
            self.stdout.write(f"Clearing {n} Rently-sourced properties...")
            PropertyImage.objects.filter(property__in=qs).delete()
            PropertyAmenity.objects.filter(property__in=qs).delete()
            qs.delete()
            self.stdout.write("Cleared.")

        # ── Amenity categories ────────────────────────────────────────────────
        cat_objs = {}
        for key, name, icon, order in CATEGORIES:
            obj, _ = AmenityCategory.objects.get_or_create(
                name=name, defaults={"icon": icon, "order": order},
            )
            cat_objs[key] = obj

        # ── Agent ─────────────────────────────────────────────────────────────
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
        total_props = total_amenities = total_images = 0

        # ══════════════════════════════════════════════════════════════════════
        # 1. APARTMENT COMMUNITIES — per-metro bbox (avoids one huge slow call)
        # ══════════════════════════════════════════════════════════════════════
        if not skip_communities:
            self.stdout.write("\n── Fetching apartment communities per metro bbox...")
            comm_map = {}

            for city_name, sw_lat, sw_lng, ne_lat, ne_lng, c_lat, c_lng in METROS:
                self.stdout.write(f"   Communities: {city_name}...", ending="\r")
                try:
                    data = _get(f"{BASE_URL}/api/homes_listings", timeout=30, params={
                        "community_type": "all", "from_web": "true",
                        "city_filter": city_name,
                        "latitude1": sw_lat, "longitude1": sw_lng,
                        "latitude2": ne_lat, "longitude2": ne_lng,
                        "searchLatitude": c_lat, "searchLongitude": c_lng,
                    })
                    for c in data.get("community_data", []) + data.get("nearest_community_data", []):
                        cid = c.get("id")
                        if cid and cid not in comm_map:
                            comm_map[cid] = c
                    time.sleep(0.15)
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"\n   {city_name} communities: {e}"))

            self.stdout.write(f"\n   Found {len(comm_map)} unique communities.")

            for cid, comm in comm_map.items():
                if limit and total_props >= limit:
                    break

                city  = _str(comm.get("city"))
                state = _str(comm.get("state", "")).upper()
                if state_filter and state != state_filter:
                    continue

                name      = _str(comm.get("name") or f"Apartment Community in {city}")
                zipcode   = _str(comm.get("zipcode"))
                lat       = _dec(comm.get("latitude"))
                lng       = _dec(comm.get("longitude"))
                addr_raw  = _str(comm.get("address") or name)
                fp        = comm.get("floorplan", {})
                min_rent  = fp.get("min_rent") or 0
                max_rent  = fp.get("max_rent") or 0
                min_beds  = _int(fp.get("min_bedrooms"), 0) or 0
                max_beds  = _int(fp.get("max_bedrooms"), 0) or 0
                min_baths = _dec(fp.get("min_bathrooms"), Decimal("1"))
                min_sqft  = _int(fp.get("min_size"), 0) or 0
                adj_price = _adj_price(min_rent)

                beds_label = (
                    f"{min_beds}–{max_beds} Bed" if max_beds and max_beds != min_beds
                    else (f"{min_beds}-Bed" if min_beds else "Studio")
                )
                price_range = (
                    f"${int(_adj_price(min_rent)):,}–${int(_adj_price(max_rent)):,}/mo"
                    if max_rent else ""
                )
                description = (
                    f"{name} is a residential apartment community in {city}, {state}. "
                    f"Available units range from {beds_label} floorplans"
                    + (f" priced from {price_range}." if price_range else ".")
                    + f" {comm.get('active_units_count', 0)} units currently available."
                )

                slug = _unique_slug(
                    _make_slug(f"comm-{cid}", addr_raw, city, state),
                    existing_slugs, f"comm-{cid}",
                )
                if slug in existing_slugs:
                    continue

                try:
                    prop = Property.objects.create(
                        agent=agent, slug=slug,
                        title=f"{beds_label} Apartment at {name}, {city}",
                        description=description,
                        type="residential", listing_type="for-rent", status="available",
                        price=adj_price, price_label="/mo",
                        bedrooms=min_beds, bathrooms=min_baths, sqft=min_sqft,
                        address=addr_raw, city=city, state=state, zip_code=zipcode,
                        latitude=lat, longitude=lng,
                        neighborhood=name, condition="good",
                        cross_street="rently", is_published=True,
                    )
                    existing_slugs.add(slug)
                    total_props += 1

                    # All gallery photos — use raw SQL to bypass CloudinaryField mangling
                    gallery = comm.get("gallery_photos", [])
                    gallery_urls = [
                        _photo_url(ph)
                        for ph in gallery
                    ]
                    total_images += _insert_images_raw(prop.id, gallery_urls)

                    if total_props % 50 == 0:
                        self.stdout.write(f"   {total_props} properties seeded...")

                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"   Skipped community {cid}: {e}"))

        # ══════════════════════════════════════════════════════════════════════
        # 2. SFR HOMES — streamed: collect bbox → flush batch → repeat
        # ══════════════════════════════════════════════════════════════════════
        if not skip_sfr:
            self.stdout.write("\n── Streaming SFR homes (fetch + insert per batch)...")

            def fetch_detail(pid):
                try:
                    d = _get(f"{BASE_URL}/api/propertyDetails/{pid}", timeout=25)
                    return pid, d.get("property") or d
                except Exception:
                    return pid, None

            def _insert_sfr(pid, slim, detail):
                """Insert one SFR property. Returns (props, amenities, images) counts."""
                fp         = slim.get("floorplan", {})
                beds       = _int(detail.get("bedrooms")    or fp.get("bedrooms"), 0) or 0
                baths      = _dec(detail.get("bathrooms")   or fp.get("bathrooms"), Decimal("1"))
                sqft       = _int(detail.get("size")        or fp.get("size"), 0) or 0
                rent       = detail.get("price")            or fp.get("rent") or 0
                year_built = _int(detail.get("year_built")  or detail.get("year"), None)
                lot_size   = _dec(detail.get("lot_size")    or detail.get("lot"), None)
                stories    = _int(detail.get("stories")     or detail.get("floors"), None)
                raw_addr   = _str(detail.get("address")     or detail.get("street_address")
                                  or slim.get("address", ""))
                city       = _str(detail.get("city")        or slim.get("city", ""))
                raw_state  = _str(detail.get("state")       or slim.get("state", "")).upper()
                zipcode    = _str(detail.get("zipcode")     or detail.get("zip", ""))
                lat        = _dec(detail.get("latitude")    or slim.get("latitude"))
                lng        = _dec(detail.get("longitude")   or slim.get("longitude"))
                raw_desc   = _str(detail.get("description") or slim.get("headline", ""))
                deposit    = _dec(detail.get("deposit"), None)
                prop_type  = PROP_TYPE_MAP.get(_str(slim.get("type", "")).lower(), "residential")
                neighborhood = _str(detail.get("neighborhood") or detail.get("community_name", ""))

                # Virtual tour / 360
                vt_url, t360_url = _tour_url(detail)

                adj_price  = _adj_price(rent)
                adj_addr   = _adj_address(raw_addr) if raw_addr else ""
                bed_label  = "Studio" if beds == 0 else f"{beds}-Bed"

                title = (
                    f"{bed_label} Home at {adj_addr}, {city}" if adj_addr and city else
                    f"{bed_label} Home at {adj_addr}"          if adj_addr else
                    f"{bed_label} Home in {city}, {raw_state}" if city else
                    f"{bed_label} Rental Home"
                )

                # Clean description — strip Rently branding, prices, apply-now CTAs
                desc = _clean_desc(raw_desc)
                if not desc:
                    desc = (
                        f"A well-maintained {bed_label.lower()} home available for rent in "
                        f"{city}, {raw_state}."
                        + (f" Built in {year_built}." if year_built else "")
                        + (f" Security deposit: ${int(deposit):,}." if deposit else "")
                    )

                slug = _unique_slug(_make_slug(pid, raw_addr, city, raw_state), existing_slugs, pid)
                if slug in existing_slugs:
                    return 0, 0, 0

                # ── Amenities ─────────────────────────────────────────────────
                parsed = _parse_amenities(detail.get("amenities", ""))

                # Pet flags from both floorplan and detail
                pet = []
                if _bool(fp.get("dog"))  or _bool(detail.get("allow_dog")):
                    pet.append(("dogs-allowed", "Dogs Allowed"))
                if _bool(fp.get("cat"))  or _bool(detail.get("allow_cat")):
                    pet.append(("cats-allowed", "Cats Allowed"))
                if _bool(fp.get("no_pet")) or _bool(detail.get("no_pets")):
                    pet.append(("no-pets", "No Pets"))

                # Deduplicate amenities
                seen_amen = set()
                all_amenities = []
                for s, n in parsed + pet:
                    if s not in seen_amen:
                        seen_amen.add(s)
                        all_amenities.append((s, n))

                has_garage = "garage" in seen_amen

                # ── Photos — prefer large_url → url → medium_url ──────────────
                pictures = detail.get("pictures", [])
                if not pictures:
                    fb = slim.get("picture", "")
                    if fb:
                        pictures = [fb]

                # ── Create property ───────────────────────────────────────────
                prop = Property.objects.create(
                    agent=agent, slug=slug,
                    title=title, description=desc,
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

                # Amenities
                amen_objs = [
                    PropertyAmenity(
                        property=prop,
                        category=cat_objs[SLUG_TO_CAT.get(s, "home")],
                        name=n,
                    )
                    for s, n in all_amenities if s != "garage"
                ]
                if amen_objs:
                    PropertyAmenity.objects.bulk_create(amen_objs, batch_size=500, ignore_conflicts=True)

                # Images — raw SQL to bypass CloudinaryField URL mangling
                photo_urls = [_photo_url(pic) for pic in pictures]
                n_images = _insert_images_raw(prop.id, photo_urls)

                return 1, len(amen_objs), n_images

            def _flush(pending: dict):
                """Fetch details + insert for one batch. Clears pending in-place."""
                nonlocal total_props, total_amenities, total_images
                if not pending:
                    return
                batch_details = {}
                if not skip_details:
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        futs = {pool.submit(fetch_detail, pid): pid for pid in pending}
                        for fut in as_completed(futs):
                            pid, det = fut.result()
                            if det:
                                batch_details[pid] = det
                for pid, slim in list(pending.items()):
                    if limit and total_props >= limit:
                        break
                    detail = batch_details.get(pid, {})
                    raw_state = _str(detail.get("state") or slim.get("state", "")).upper()
                    if state_filter and raw_state and raw_state != state_filter:
                        continue
                    try:
                        p, a, im = _insert_sfr(pid, slim, detail)
                        total_props     += p
                        total_amenities += a
                        total_images    += im
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"   Skipped {pid}: {e}"))
                batch_details.clear()
                pending.clear()

            seen_ids    = set()
            pending     = {}
            total_found = 0

            for city_name, sw_lat, sw_lng, ne_lat, ne_lng, c_lat, c_lng in METROS:
                if limit and total_props >= limit:
                    break
                self.stdout.write(
                    f"   {city_name} ({total_found} found, {total_props} seeded)...",
                    ending="\r",
                )
                try:
                    data = _get(f"{BASE_URL}/api/searchQueryNew", params={
                        "rentalType": "0", "pc": "1",
                        "smart_match": "false", "from_web": "true",
                        "city_filter": city_name,
                        "latitude1": sw_lat, "longitude1": sw_lng,
                        "latitude2": ne_lat, "longitude2": ne_lng,
                        "searchLatitude": c_lat, "searchLongitude": c_lng,
                    })
                    for p in data.get("property_data", []) + data.get("nearest_property_data", []):
                        pid = p.get("id")
                        if pid and pid not in seen_ids:
                            seen_ids.add(pid)
                            total_found += 1
                            pending[pid] = {
                                "floorplan": p.get("floorplan", {}),
                                "picture":   _normalize_url(p.get("picture", "")),
                                "type":      p.get("type", "House"),
                                "address":   p.get("address", ""),
                                "city":      p.get("city", ""),
                                "state":     p.get("state", ""),
                                "latitude":  p.get("latitude"),
                                "longitude": p.get("longitude"),
                                "headline":  p.get("headline", ""),
                            }
                            if len(pending) >= batch_size:
                                _flush(pending)
                                self.stdout.write(
                                    f"\n   Batch done — {total_found} found, {total_props} seeded"
                                )
                    time.sleep(0.15)
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"\n   {city_name} failed: {e}"))

            if pending and not (limit and total_props >= limit):
                _flush(pending)

            self.stdout.write(f"\n   SFR total found: {total_found}")

        self.stdout.write(self.style.SUCCESS(f"\n{'='*50}"))
        self.stdout.write(self.style.SUCCESS("RENTLY SEED COMPLETE"))
        self.stdout.write(self.style.SUCCESS(f"Properties : {total_props:,}"))
        self.stdout.write(self.style.SUCCESS(f"Amenities  : {total_amenities:,}"))
        self.stdout.write(self.style.SUCCESS(f"Images     : {total_images:,}"))
        self.stdout.write(self.style.SUCCESS(f"{'='*50}"))
