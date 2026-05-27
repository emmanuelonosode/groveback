"""
scrape_invitationhomes.py
─────────────────────────
Live web scraper for invitationhomes.com.  Pulls every active rental listing
across all 19 markets, transforms prices (-15 %, round to nearest $100),
strips branding from descriptions, and writes clean records to the database.

Usage:
    python manage.py scrape_invitationhomes
    python manage.py scrape_invitationhomes --markets atlanta-georgia,tampa-florida
    python manage.py scrape_invitationhomes --limit 50
    python manage.py scrape_invitationhomes --delay 2
    python manage.py scrape_invitationhomes --dry-run
    python manage.py scrape_invitationhomes --clear
    python manage.py scrape_invitationhomes --skip-detail
"""

import json
import logging
import math
import random
import re
import time
from decimal import Decimal, InvalidOperation

import requests
from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils.text import slugify

from apps.accounts.models import Role
from apps.properties.models import AmenityCategory, Property, PropertyAmenity

User = get_user_model()
log = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

BASE = "https://www.invitationhomes.com"

# All 19 InvitationHomes markets: (url-slug, display-city, state-abbrev)
MARKETS = [
    ("atlanta-georgia",               "Atlanta",              "GA"),
    ("tampa-florida",                 "Tampa",                "FL"),
    ("phoenix-arizona",               "Phoenix",              "AZ"),
    ("orlando-florida",               "Orlando",              "FL"),
    ("dallas-texas",                  "Dallas",               "TX"),
    ("houston-texas",                 "Houston",              "TX"),
    ("charlotte-north-carolina",      "Charlotte",            "NC"),
    ("jacksonville-florida",          "Jacksonville",         "FL"),
    ("las-vegas-nevada",              "Las Vegas",            "NV"),
    ("nashville-tennessee",           "Nashville",            "TN"),
    ("south-florida-miami",           "Miami",                "FL"),
    ("denver-colorado",               "Denver",               "CO"),
    ("seattle-washington",            "Seattle",              "WA"),
    ("minneapolis-minnesota",         "Minneapolis",          "MN"),
    ("northern-california",           "Northern California",  "CA"),
    ("southern-california",           "Southern California",  "CA"),
    ("chicago-illinois",              "Chicago",              "IL"),
    ("raleigh-durham-north-carolina", "Raleigh-Durham",       "NC"),
    ("austin-texas",                  "Austin",               "TX"),
]

CATEGORIES = [
    ("home",      "Home Features",         "Home",     0),
    ("kitchen",   "Kitchen Features",      "ChefHat",  1),
    ("utility",   "Utility & Maintenance", "Zap",      2),
    ("community", "Community Features",    "Users",    3),
    ("pet",       "Pet Policy",            "PawPrint", 4),
]

# keyword → amenity category key
_AMENITY_KW: list[tuple[str, str]] = [
    ("kitchen",          "kitchen"),
    ("dishwasher",       "kitchen"),
    ("refrigerator",     "kitchen"),
    ("microwave",        "kitchen"),
    ("stainless",        "kitchen"),
    ("granite",          "kitchen"),
    ("quartz",           "kitchen"),
    ("oven",             "kitchen"),
    ("range",            "kitchen"),
    ("island",           "kitchen"),
    ("washer",           "utility"),
    ("dryer",            "utility"),
    ("laundry",          "utility"),
    ("air condition",    "utility"),
    ("central air",      "utility"),
    ("hvac",             "utility"),
    ("heating",          "utility"),
    ("cooling",          "utility"),
    ("thermostat",       "utility"),
    ("pool",             "community"),
    ("fitness",          "community"),
    ("gym",              "community"),
    ("playground",       "community"),
    ("dog park",         "community"),
    ("tennis",           "community"),
    ("basketball",       "community"),
    ("walking trail",    "community"),
    ("gated",            "community"),
    ("clubhouse",        "community"),
    ("hoa",              "community"),
    ("pet",              "pet"),
    ("dog",              "pet"),
    ("cat",              "pet"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Connection":      "keep-alive",
    "Sec-Fetch-Dest":  "document",
    "Sec-Fetch-Mode":  "navigate",
    "Sec-Fetch-Site":  "none",
    "Sec-Fetch-User":  "?1",
    "Cache-Control":   "max-age=0",
}

JSON_HEADERS = {
    **HEADERS,
    "Accept":         "application/json,*/*;q=0.8",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

# ── Description cleaning ─────────────────────────────────────────────────────

_DESC_PATS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\[([^\]]*)\]\([^)]*\)'),          r'\1'),   # [text](url) → text
    (re.compile(r'<[^>]+>'),                          ''),    # HTML tags
    (re.compile(r'&[a-z#0-9]{1,8};', re.I),          ' '),   # HTML entities
    (re.compile(r'\bInvitation\s*Homes?\b', re.I),    ''),
    (re.compile(r'\bInvitationHomes\b', re.I),        ''),
    (re.compile(r'\binvitationhomes\.com\b', re.I),   ''),
    (re.compile(r'\bIH\s+(?=\w)', re.I),              ''),    # "IH " prefix
    (re.compile(r'https?://\S+'),                     ''),    # raw URLs
    (re.compile(r' {3,}'),                            '  '),  # extra spaces
    (re.compile(r'\n{3,}'),                           '\n\n'),
    (re.compile(r'^\s+', re.M),                       ''),    # leading whitespace per line
    (re.compile(r'\s+$', re.M),                       ''),    # trailing whitespace per line
]


def _clean_desc(text: str) -> str:
    if not text:
        return ""
    for pat, repl in _DESC_PATS:
        text = pat.sub(repl, text)
    return text.strip()


# ── Price transform ──────────────────────────────────────────────────────────

def _transform_price(raw) -> int:
    """raw_price × 0.85, rounded to nearest $100."""
    try:
        p = int(float(str(raw).replace(",", "").replace("$", "").strip()))
    except (ValueError, TypeError):
        return 0
    return round(p * 0.85 / 100) * 100


# ── Raw SQL image insert ─────────────────────────────────────────────────────

def _insert_images_raw(property_id: int, urls: list) -> int:
    """
    Insert images via raw SQL to bypass CloudinaryField.to_python() which
    mangles external CDN URLs (cloudfront.net, etc.) on write.
    """
    clean = [u for u in urls if u and isinstance(u, str) and u.startswith("https://")]
    if not clean:
        return 0
    q = connection.ops.quote_name
    sql = (
        f"INSERT INTO {q('properties_propertyimage')} "
        f"({q('property_id')}, {q('image')}, {q('caption')}, "
        f"{q('is_primary')}, {q('order')}) "
        f"VALUES (%s, %s, %s, %s, %s)"
    )
    rows = [(property_id, url, "", i == 0, i) for i, url in enumerate(clean)]
    with connection.cursor() as cursor:
        cursor.executemany(sql, rows)
    return len(clean)


# ── Amenity categorisation ───────────────────────────────────────────────────

def _cat_for(name: str) -> str:
    lo = name.lower()
    for kw, cat in _AMENITY_KW:
        if kw in lo:
            return cat
    return "home"


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def _get(session: requests.Session, url: str, *, retries: int = 3,
        base_delay: float = 1.5, **kwargs) -> requests.Response:
    """GET with retry + jitter + rate-limit handling."""
    for attempt in range(retries):
        time.sleep(base_delay + random.uniform(0.3, 0.9))
        try:
            r = session.get(url, timeout=30, **kwargs)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 90))
                log.warning("Rate-limited → sleeping %ds", wait)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            if attempt == retries - 1:
                raise
            log.warning("GET %s failed (%s), retry %d/%d", url, exc, attempt + 1, retries)
            time.sleep(base_delay * 2 ** attempt)
    raise RuntimeError(f"All {retries} attempts failed for {url}")


# ── __NEXT_DATA__ extraction ─────────────────────────────────────────────────

def _next_data(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return None
    try:
        return json.loads(tag.string)
    except json.JSONDecodeError:
        return None


def _find_list(obj, *keys):
    """Walk nested dicts/lists; return first value whose key matches any of keys."""
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, list) and v:
                return v
        for v in obj.values():
            result = _find_list(v, *keys)
            if result is not None:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _find_list(item, *keys)
            if result is not None:
                return result
    return None


def _find_int(obj, *keys) -> int:
    """Walk nested dicts; return first integer value matching any key."""
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if v is not None:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    pass
        for v in obj.values():
            result = _find_int(v, *keys)
            if result:
                return result
    return 0


# ── Image URL helpers ────────────────────────────────────────────────────────

_IH_IMG_RE = re.compile(r'/c_(?:scale|fill),w_\d+/')

# Branded / placeholder images IH injects — skip these entirely.
# Matches filenames that are generic branding, not property photos.
_BRANDED_IMG_RE = re.compile(
    r'(?:invitation.?homes?|ih[-_]logo|ih[-_]brand|ih[-_]hero|'
    r'placeholder|fallback|default[-_]image|no[-_]photo|nophoto|'
    r'logo[-_]|[-_]logo|brand[-_]|[-_]brand)',
    re.I,
)


def _upgrade_ih_image(url: str) -> str:
    """Upgrade InvitationHomes CDN images to 1200px wide."""
    if not url or not url.startswith("http"):
        return ""
    if "images.invitationhomes.com" in url:
        url = _IH_IMG_RE.sub("/c_fill,w_1200/", url)
    return url


def _is_branded(url: str) -> bool:
    """Return True if the URL looks like an IH placeholder/branding image."""
    # Check the filename portion (after last slash, before query string)
    path = url.split("?")[0]
    filename = path.rsplit("/", 1)[-1]
    return bool(_BRANDED_IMG_RE.search(filename))


def _photo_url(photo) -> str:
    if isinstance(photo, str):
        u = _upgrade_ih_image(photo)
        return "" if _is_branded(u) else u
    if isinstance(photo, dict):
        for k in ("url", "src", "imageUrl", "originalUrl", "cdnUrl", "largeUrl"):
            v = photo.get(k, "")
            if v and isinstance(v, str) and v.startswith("http"):
                u = _upgrade_ih_image(v)
                return "" if _is_branded(u) else u
    return ""


# ── Address helpers ──────────────────────────────────────────────────────────

def _parse_address_line(text: str):
    """
    Parse 'Street City, ST ZIP' → (address, city, state, zip).
    IH format: '47 Welcome Wy Bethlehem, GA 30620'
    """
    text = text.strip()
    m = re.match(r'^(.*),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$', text)
    if m:
        street_city = m.group(1).strip()
        state       = m.group(2)
        zip_code    = m.group(3)
        parts = street_city.rsplit(" ", 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip(), state, zip_code
        return street_city, street_city, state, zip_code
    return text, "", "", ""


def _address_from_slug(slug: str) -> tuple[str, str]:
    """
    Extract street address and ZIP from an IH property slug.
    Slug format: {address-parts}-{zip5}-{property-id}
    Example: '47-welcome-way-30620-124045'  →  ('47 Welcome Way', '30620')
    """
    parts = slug.split("-")
    # Require at least: one address word, a 5-digit zip, and a numeric id
    if len(parts) < 3:
        return "", ""
    prop_id  = parts[-1]
    zip_part = parts[-2]
    if not prop_id.isdigit() or not (zip_part.isdigit() and len(zip_part) == 5):
        return "", ""
    addr_parts = parts[:-2]
    # Title-case each word; numbers stay as-is
    address = " ".join(
        p.upper() if len(p) <= 2 and not p.isdigit() else p.capitalize()
        for p in addr_parts
    )
    return address, zip_part


def _parse_microdata_address(soup) -> tuple[str, str, str, str]:
    """
    Extract address from HTML itemprop / schema.org microdata.
    Returns (street, city, state, zip).
    """
    def _text(el):
        return el.get_text(" ", strip=True) if el else ""

    # itemprop attributes (schema.org PostalAddress)
    street = _text(soup.find(attrs={"itemprop": "streetAddress"}))
    city   = _text(soup.find(attrs={"itemprop": "addressLocality"}))
    state  = _text(soup.find(attrs={"itemprop": "addressRegion"}))
    zip_c  = _text(soup.find(attrs={"itemprop": "postalCode"}))
    if street:
        return street, city, state, zip_c

    # JSON-LD structured data
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            ld = json.loads(tag.string or "")
            items = ld if isinstance(ld, list) else [ld]
            for item in items:
                addr = item.get("address") or {}
                if isinstance(addr, dict) and addr.get("streetAddress"):
                    return (
                        addr.get("streetAddress", ""),
                        addr.get("addressLocality", ""),
                        addr.get("addressRegion", ""),
                        addr.get("postalCode", ""),
                    )
        except Exception:
            pass

    return "", "", "", ""


# ── JSON listing → standard dict ─────────────────────────────────────────────

_LISTING_KEYS = (
    "listings", "properties", "homes", "items",
    "results", "data", "units", "rentalListings",
)
_TOTAL_KEYS = (
    "totalCount", "total", "count", "totalResults",
    "totalListings", "totalProperties", "numResults",
)
_SLUG_KEYS  = ("slug", "urlSlug", "propertySlug", "listingSlug", "permalink")
_PRICE_KEYS = ("rent", "price", "monthlyRent", "rentalRate", "listingPrice")
_SQFT_KEYS  = ("squareFeet", "sqft", "livingArea", "squareFootage", "floorArea")
_PHOTO_KEYS = ("photos", "images", "media", "photoUrls", "imageUrls", "imageList")
_DESC_KEYS  = ("description", "listingDescription", "remarks", "publicRemarks", "homeDescription")
_AMEN_KEYS  = ("amenities", "features", "homeFeatures", "propertyFeatures", "amenityList")


def _pick(obj: dict, *keys, default=None):
    for k in keys:
        v = obj.get(k)
        if v is not None:
            return v
    return default


def _listing_from_json(obj: dict, market_slug: str, default_state: str) -> dict | None:
    if not isinstance(obj, dict):
        return None

    # Slug / detail URL
    slug = _pick(obj, *_SLUG_KEYS, default="")
    detail_url = _pick(obj, "detailUrl", "url", "propertyUrl", "listingUrl", default="")
    if detail_url and detail_url.startswith("/"):
        detail_url = f"{BASE}{detail_url}"
    if not detail_url and slug:
        detail_url = f"{BASE}/houses-for-rent/{slug}"
    if not slug and detail_url:
        slug = detail_url.rstrip("/").split("/")[-1]
    if not slug and not detail_url:
        return None

    # Price
    raw_price = _pick(obj, *_PRICE_KEYS, default=0)

    # Beds / baths / sqft
    beds = 0
    try:
        beds = int(_pick(obj, "bedrooms", "beds", "numBedrooms", default=0) or 0)
    except (TypeError, ValueError):
        pass

    baths = 0.0
    try:
        baths = float(str(_pick(obj, "bathrooms", "baths", "numBathrooms", default=0) or 0)
                    .replace(",", ""))
    except (TypeError, ValueError):
        pass

    sqft = 0
    try:
        sqft = int(str(_pick(obj, *_SQFT_KEYS, default=0) or 0).replace(",", ""))
    except (TypeError, ValueError):
        pass

    year_built = _pick(obj, "yearBuilt", "year_built", "yearConstructed")

    # Address
    addr_obj = _pick(obj, "address", "location", default={})
    if isinstance(addr_obj, dict):
        address  = str(_pick(addr_obj, "street", "streetAddress", "line1", "address1", default="") or "")
        city     = str(_pick(addr_obj, "city", default="") or "")
        state    = str(_pick(addr_obj, "state", "stateCode", default=default_state) or default_state)
        zip_code = str(_pick(addr_obj, "zipCode", "zip", "postalCode", default="") or "")
        lat      = _pick(addr_obj, "lat", "latitude")
        lng      = _pick(addr_obj, "lng", "longitude")
    else:
        raw_addr = _pick(obj, "streetAddress", "address1", "addressLine1", default="")
        if isinstance(raw_addr, str) and "," in raw_addr:
            address, city, state, zip_code = _parse_address_line(raw_addr)
        else:
            address  = str(raw_addr or "")
            city     = str(_pick(obj, "city", default="") or "")
            state    = str(_pick(obj, "state", "stateCode", default=default_state) or default_state)
            zip_code = str(_pick(obj, "zipCode", "zip", "postalCode", default="") or "")
        lat = _pick(obj, "lat", "latitude")
        lng = _pick(obj, "lng", "longitude")

    # Images
    photos = _pick(obj, *_PHOTO_KEYS, default=[]) or []
    image_urls = [u for u in (_photo_url(p) for p in photos) if u]

    # Description
    description = str(_pick(obj, *_DESC_KEYS, default="") or "")

    # Amenities
    amenities_raw = _pick(obj, *_AMEN_KEYS, default=[]) or []
    amenities: list[str] = []
    for a in amenities_raw:
        if isinstance(a, str):
            amenities.append(a)
        elif isinstance(a, dict):
            name = _pick(a, "name", "value", "label", "text", default="") or ""
            if name:
                amenities.append(str(name))

    needs_detail = not description or not image_urls

    return {
        "slug":        slug,
        "detail_url":  detail_url,
        "market_slug": market_slug,
        "price":       raw_price,
        "bedrooms":    beds,
        "bathrooms":   baths,
        "sqft":        sqft,
        "year_built":  year_built,
        "address":     address,
        "city":        city,
        "state":       (state[:2] if len(state) >= 2 else state) or default_state,
        "zip_code":    zip_code,
        "latitude":    lat,
        "longitude":   lng,
        "image_urls":  image_urls,
        "amenities":   amenities,
        "description": description,
        "_needs_detail": needs_detail,
    }


# ── HTML card parser (fallback) ──────────────────────────────────────────────

def _parse_html_cards(html: str, market_slug: str, default_state: str) -> list[dict]:
    """
    Extract listing stubs from the HTML of a market page.
    Used when __NEXT_DATA__ doesn't contain a listings array.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Strategy 1: find links that look like property detail pages
    links = soup.find_all("a", href=re.compile(r"/houses-for-rent/[^/?#]+$"))
    seen: set[str] = set()
    results: list[dict] = []

    for link in links:
        href = link.get("href", "")
        if not href or href in seen:
            continue
        seen.add(href)

        if href.startswith("/"):
            detail_url = f"{BASE}{href}"
        else:
            detail_url = href
        slug = detail_url.rstrip("/").split("/")[-1]

        # Attempt to extract price / beds / baths from surrounding card text
        card = link.find_parent(["article", "section", "div", "li"])
        text = card.get_text(" ", strip=True) if card else link.get_text(" ", strip=True)

        # Price
        price_m = re.search(r"\$([0-9,]+)", text)
        price = int(price_m.group(1).replace(",", "")) if price_m else 0

        # Beds / baths / sqft
        beds_m  = re.search(r"(\d+)\s*bed", text, re.I)
        baths_m = re.search(r"([\d.]+)\s*bath", text, re.I)
        sqft_m  = re.search(r"([0-9,]+)\s*sq", text, re.I)
        beds  = int(beds_m.group(1)) if beds_m else 0
        baths = float(baths_m.group(1)) if baths_m else 0.0
        sqft  = int(sqft_m.group(1).replace(",", "")) if sqft_m else 0

        # Images in card
        imgs = card.find_all("img") if card else []
        image_urls = []
        for img in imgs:
            src = img.get("src") or img.get("data-src") or ""
            if src and "images.invitationhomes.com" in src:
                image_urls.append(_upgrade_ih_image(src))

        results.append({
            "slug":          slug,
            "detail_url":    detail_url,
            "market_slug":   market_slug,
            "price":         price,
            "bedrooms":      beds,
            "bathrooms":     baths,
            "sqft":          sqft,
            "year_built":    None,
            "address":       "",
            "city":          "",
            "state":         default_state,
            "zip_code":      "",
            "latitude":      None,
            "longitude":     None,
            "image_urls":    image_urls,
            "amenities":     [],
            "description":   "",
            "_needs_detail": True,
        })

    return results


# ── Detail page enrichment ───────────────────────────────────────────────────

def _scrape_detail(session: requests.Session, prop: dict,
                base_delay: float) -> dict:
    """Fetch the property detail page and enrich prop with all available data."""
    url = prop.get("detail_url", "")
    if not url:
        return prop

    try:
        resp = _get(session, url, headers=HEADERS, base_delay=base_delay)
    except Exception as exc:
        log.warning("Detail fetch failed %s: %s", url, exc)
        return prop

    html = resp.text
    nd   = _next_data(html)

    if nd:
        pp = nd.get("props", {}).get("pageProps", {})
        listing_obj = None
        for key in ("listing", "property", "home", "unit", "data", "rentalListing"):
            v = pp.get(key)
            if isinstance(v, dict):
                listing_obj = v
                break
        if listing_obj is None and (pp.get("slug") or pp.get("propertyId") or pp.get("id")):
            listing_obj = pp

        if listing_obj:
            enriched = _listing_from_json(listing_obj, prop["market_slug"], prop["state"])
            if enriched:
                for field in ("description", "amenities", "image_urls", "bedrooms",
                            "bathrooms", "sqft", "year_built", "latitude", "longitude",
                            "address", "city", "state", "zip_code"):
                    val = enriched.get(field)
                    if val and not prop.get(field):
                        prop[field] = val

    soup = BeautifulSoup(html, "html.parser")

    # ── Address (microdata / JSON-LD) ──────────────────────────────────────
    if not prop.get("address"):
        street, city, state, zip_c = _parse_microdata_address(soup)
        if street:
            prop["address"]  = street
            prop["city"]     = prop.get("city")  or city
            prop["state"]    = prop.get("state") or state
            prop["zip_code"] = prop.get("zip_code") or zip_c

    # ── Description ────────────────────────────────────────────────────────
    if not prop.get("description"):
        for sel in (
            "[data-testid*='description']",
            "[class*='description']",
            "[class*='Description']",
            "section[class*='about']",
            "div[class*='About']",
        ):
            el = soup.select_one(sel)
            if el:
                prop["description"] = el.get_text("\n", strip=True)
                break

    # ── Amenities ──────────────────────────────────────────────────────────
    if not prop.get("amenities"):
        amenities: list[str] = []
        for sel in (
            "[data-testid*='feature']", "[data-testid*='amenity']",
            "[class*='Feature']",       "[class*='Amenity']",
            "[class*='feature']",       "[class*='amenity']",
        ):
            for el in soup.select(sel):
                for li in el.find_all("li"):
                    t = li.get_text(" ", strip=True)
                    if t and len(t) < 120:
                        amenities.append(t)
        if not amenities:
            heading = soup.find(string=re.compile(r"home\s+features?", re.I))
            if heading:
                parent = heading.find_parent()
                ul = parent.find_next_sibling("ul") if parent else None
                if ul:
                    amenities = [li.get_text(" ", strip=True) for li in ul.find_all("li")]
        if amenities:
            prop["amenities"] = amenities

    # ── Images — collect ALL, filter branded, deduplicate ─────────────────
    existing = set(prop.get("image_urls", []))
    extra: list[str] = []

    # From <img> tags
    for img in soup.find_all("img", src=re.compile(r"images\.invitationhomes\.com")):
        src = img.get("src") or img.get("data-src") or ""
        u = _upgrade_ih_image(src)
        if u and not _is_branded(u) and u not in existing:
            existing.add(u)
            extra.append(u)

    # From <source srcset="..."> inside <picture>
    for src_tag in soup.find_all("source", attrs={"srcset": True}):
        for part in src_tag.get("srcset", "").split(","):
            raw = part.strip().split(" ")[0]
            if "images.invitationhomes.com" in raw:
                u = _upgrade_ih_image(raw)
                if u and not _is_branded(u) and u not in existing:
                    existing.add(u)
                    extra.append(u)

    if extra:
        prop["image_urls"] = list(prop.get("image_urls", [])) + extra

    prop["_needs_detail"] = False
    return prop


# ── Market scraper ───────────────────────────────────────────────────────────

def _scrape_market(session: requests.Session, market_slug: str, default_state: str,
                limit: int | None, base_delay: float, stdout) -> list[dict]:
    """Return all listing stubs (with pagination) for one market."""
    url = f"{BASE}/markets/houses-for-rent/{market_slug}"
    stdout.write(f"    Fetching {url} …")

    resp     = _get(session, url, headers=HEADERS, base_delay=base_delay)
    html     = resp.text
    nd       = _next_data(html)
    build_id = nd.get("buildId", "") if nd else ""

    # ── Try __NEXT_DATA__ path first ────────────────────────────────────────
    nd_listings: list[dict] = []
    nd_total = 0

    if nd:
        pp = nd.get("props", {}).get("pageProps", {})
        found = _find_list(pp, *_LISTING_KEYS)
        if found:
            nd_listings = found
        nd_total = _find_int(pp, *_TOTAL_KEYS)

    if nd_listings:
        # ── NEXT_DATA path: structured JSON ──────────────────────────────
        per_page = len(nd_listings) or 20
        total    = nd_total or per_page
        stdout.write(
            f"    __NEXT_DATA__: {len(nd_listings)} listings "
            f"(total reported: {total})"
        )
        results: list[dict] = [
            p for p in (_listing_from_json(o, market_slug, default_state)
                        for o in nd_listings if isinstance(o, dict))
            if p
        ]
        seen_slugs = {p["slug"] for p in results if p.get("slug")}

        # Paginate via Next.js data API
        if build_id and total > per_page:
            num_pages = math.ceil(total / per_page)
            stdout.write(f"    Next.js API pagination: {num_pages} pages …")
            for page_num in range(2, num_pages + 1):
                if limit and len(results) >= limit:
                    break
                json_url = (
                    f"{BASE}/_next/data/{build_id}"
                    f"/markets/houses-for-rent/{market_slug}.json"
                )
                try:
                    pr    = _get(session, json_url, headers=JSON_HEADERS,
                                base_delay=base_delay, params={"page": page_num})
                    pdata = pr.json()
                    pp    = pdata.get("pageProps", {})
                    found = _find_list(pp, *_LISTING_KEYS)
                    if not found:
                        stdout.write(f"    p{page_num}: empty, stopping")
                        break
                    page_props = [
                        p for p in (
                            _listing_from_json(o, market_slug, default_state)
                            for o in found if isinstance(o, dict)
                        ) if p and p.get("slug") not in seen_slugs
                    ]
                    if not page_props:
                        stdout.write(f"    p{page_num}: all duplicates, stopping")
                        break
                    seen_slugs |= {p["slug"] for p in page_props if p.get("slug")}
                    results.extend(page_props)
                    stdout.write(
                        f"    p{page_num}: +{len(page_props)} "
                        f"({len(results)}/{total})"
                    )
                except Exception as exc:
                    stdout.write(f"    p{page_num} API failed: {exc}, stopping")
                    break

    else:
        # ── HTML fallback path ────────────────────────────────────────────
        page1 = _parse_html_cards(html, market_slug, default_state)
        stdout.write(f"    HTML fallback: {len(page1)} cards on page 1")

        results    = list(page1)
        seen_slugs = {p["slug"] for p in results if p.get("slug")}

        # Try additional HTML pages — stop immediately on duplicates
        # (IH doesn't support ?page=N so duplicates signal end-of-data)
        page_num = 2
        while not limit or len(results) < limit:
            pg_url = f"{BASE}/markets/houses-for-rent/{market_slug}?page={page_num}"
            try:
                pr       = _get(session, pg_url, headers=HEADERS, base_delay=base_delay)
                page_nd  = _next_data(pr.text)
                page_raw: list[dict] = []

                if page_nd:
                    pp       = page_nd.get("props", {}).get("pageProps", {})
                    page_raw = _find_list(pp, *_LISTING_KEYS) or []

                if not page_raw:
                    page_raw = _parse_html_cards(pr.text, market_slug, default_state)

                if not page_raw:
                    stdout.write(f"    p{page_num}: no cards, stopping")
                    break

                page_props = [
                    p for p in (
                        _listing_from_json(o, market_slug, default_state)
                        for o in page_raw if isinstance(o, dict)
                    ) if p and p.get("slug") not in seen_slugs
                ]
                if not page_props:
                    # Also check if they're raw HTML stubs
                    page_props = [
                        r for r in page_raw
                        if isinstance(r, dict)
                        and "_needs_detail" in r
                        and r.get("slug") not in seen_slugs
                    ]

                if not page_props:
                    stdout.write(
                        f"    p{page_num}: all {len(page_raw)} cards are duplicates "
                        f"— site doesn't paginate further, stopping"
                    )
                    break

                seen_slugs |= {p["slug"] for p in page_props if p.get("slug")}
                results.extend(page_props)
                stdout.write(
                    f"    p{page_num} (HTML): +{len(page_props)} "
                    f"({len(results)} total)"
                )
                page_num += 1

            except Exception as exc:
                stdout.write(f"    p{page_num}: failed ({exc}), stopping")
                break

    if limit:
        results = results[:limit]

    return results


# ── Command ──────────────────────────────────────────────────────────────────

class Command(BaseCommand):
        help = "Scrape invitationhomes.com and seed listings into the Property model."

        def add_arguments(self, parser):
            parser.add_argument(
                "--markets", default=None,
                help="Comma-separated market slugs to scrape (default: all 19 markets).",
            )
            parser.add_argument(
                "--limit", type=int, default=None,
                help="Max listings per market.",
            )
            parser.add_argument(
                "--delay", type=float, default=1.5,
                help="Base HTTP delay in seconds between requests (default 1.5).",
            )
            parser.add_argument(
                "--skip-detail", action="store_true",
                help="Skip fetching individual detail pages (faster, less data).",
            )
            parser.add_argument(
                "--dry-run", action="store_true",
                help="Scrape but do NOT write to database.",
            )
            parser.add_argument(
                "--clear", action="store_true",
                help="Delete all properties tagged cross_street='invh' before seeding.",
            )

        def handle(self, *args, **options):
            market_filter = (
                set(options["markets"].split(",")) if options["markets"] else None
            )
            limit       = options["limit"]
            base_delay  = options["delay"]
            skip_detail = options["skip_detail"]
            dry_run     = options["dry_run"]

            if dry_run:
                self.stdout.write(self.style.WARNING("── DRY RUN – nothing will be written ──"))

            # ── Clear existing invh properties ─────────────────────────────────
            if options["clear"] and not dry_run:
                count = Property.objects.filter(cross_street="invh").count()
                Property.objects.filter(cross_street="invh").delete()
                self.stdout.write(self.style.WARNING(f"Cleared {count} existing invh properties."))

            # ── Ensure amenity categories ──────────────────────────────────────
            cat_objs: dict = {}
            if not dry_run:
                for key, name, icon, order in CATEGORIES:
                    obj, _ = AmenityCategory.objects.get_or_create(
                        name=name, defaults={"icon": icon, "order": order}
                    )
                    cat_objs[key] = obj

            # ── Ensure agent ───────────────────────────────────────────────────
            agent = None
            if not dry_run:
                agent, created = User.objects.get_or_create(
                    email="agent@haskerrealtygroup.com",
                    defaults={
                        "first_name": "Marcus",
                        "last_name":  "Reid",
                        "role":       Role.AGENT,
                        "phone":      "(757) 555-0101",
                    },
                )
                if created:
                    agent.set_password("Agent1234!")
                    agent.save()
                    self.stdout.write("Agent user created.")

            # ── Existing slug sets ─────────────────────────────────────────────
            all_existing: set[str] = (
                set() if dry_run
                else set(Property.objects.values_list("slug", flat=True))
            )

            # ── HTTP session ───────────────────────────────────────────────────
            session = requests.Session()
            session.headers.update(HEADERS)

            markets_to_run = [
                (slug, city, state)
                for slug, city, state in MARKETS
                if not market_filter or slug in market_filter
            ]

            total_props = total_images = total_amenities = 0

            for mkt_slug, mkt_city, mkt_state in markets_to_run:
                self.stdout.write(f"\n{'─'*60}")
                self.stdout.write(f"Market: {mkt_city} ({mkt_slug})")

                # ── Scrape listing stubs ───────────────────────────────────────
                try:
                    props_raw = _scrape_market(
                        session, mkt_slug, mkt_state, limit, base_delay, self.stdout
                    )
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f"  Market scrape failed: {exc}"))
                    continue

                self.stdout.write(f"  {len(props_raw)} listing stubs scraped")

                for prop in props_raw:
                    slug = prop.get("slug", "")

                    # Build our DB slug — prefix "invh-" for namespacing
                    our_slug = f"invh-{slug}" if slug else ""
                    if not our_slug:
                        our_slug = slugify(
                            f"invh {prop.get('address','')} {prop.get('zip_code','')}"
                        )
                    if not our_slug or our_slug == "invh-":
                        continue  # can't build a usable slug

                    if our_slug in all_existing:
                        continue  # skip duplicates

                    detail_url = prop.get("detail_url", "")

                    # ── Fetch detail page only when data is actually missing ────
                    needs = (
                        prop.get("_needs_detail")
                        or not prop.get("address")
                        or not prop.get("image_urls")
                        or not prop.get("description")
                    )
                    if not skip_detail and detail_url and needs:
                        self.stdout.write(f"    → {detail_url}")
                        prop = _scrape_detail(session, prop, base_delay)

                    # ── Address fallback: parse from IH slug ───────────────────
                    if not prop.get("address") and slug:
                        slug_addr, slug_zip = _address_from_slug(slug)
                        if slug_addr:
                            prop["address"]  = slug_addr
                            prop["zip_code"] = prop.get("zip_code") or slug_zip

                    # All images collected — no cap applied
                    image_urls = prop.get("image_urls", [])

                    # ── Price transform ───────────────────────────────────────
                    raw_price = prop.get("price", 0)
                    price = _transform_price(raw_price)
                    if price <= 0 and raw_price:
                        price = int(float(str(raw_price)))   # fallback: keep original

                    # ── Build title ───────────────────────────────────────────
                    beds      = prop.get("bedrooms", 0)
                    bed_label = "Studio" if beds == 0 else f"{beds}-Bed"
                    address   = prop.get("address", "")
                    city      = prop.get("city",    "") or mkt_city
                    state     = prop.get("state",   "") or mkt_state
                    zip_code  = prop.get("zip_code","")

                    if address and city:
                        title = f"{bed_label} House for Rent – {address}, {city}, {state}"
                    elif city:
                        title = f"{bed_label} House for Rent in {city}, {state}"
                    else:
                        title = f"{bed_label} House for Rent"

                    # ── Clean description ──────────────────────────────────────
                    description = _clean_desc(prop.get("description", ""))
                    if not description:
                        description = (
                            f"A well-appointed {bed_label.lower()} home available for rent "
                            f"in {city}, {state}. Contact us for more details and to schedule a tour."
                        )

                    # ── Latitude / longitude ───────────────────────────────────
                    lat = lng = None
                    try:
                        if prop.get("latitude"):
                            lat = Decimal(str(prop["latitude"]))
                        if prop.get("longitude"):
                            lng = Decimal(str(prop["longitude"]))
                    except (InvalidOperation, TypeError):
                        pass

                    # ── State: ensure 2-char abbreviation ─────────────────────
                    state_abbr = (state[:2].upper() if len(state) >= 2 else state) or mkt_state

                    if dry_run:
                        self.stdout.write(
                            f"  [DRY] {our_slug}\n"
                            f"        address : {address}, {city}, {state_abbr} {zip_code}\n"
                            f"        price   : ${raw_price} → ${price}/mo\n"
                            f"        size    : {beds}bd {prop.get('bathrooms', 0)}ba {prop.get('sqft', 0)}sqft\n"
                            f"        photos  : {len(image_urls)}\n"
                            f"        amenities: {len(prop.get('amenities', []))}"
                        )
                        all_existing.add(our_slug)
                        total_props += 1
                        continue

                    # ── Write property ─────────────────────────────────────────
                    try:
                        db_prop = Property.objects.create(
                            agent        = agent,
                            slug         = our_slug,
                            title        = title,
                            description  = description,
                            type         = "residential",
                            listing_type = "for-rent",
                            status       = "available",
                            price        = Decimal(str(price)),
                            price_label  = "/mo",
                            bedrooms     = beds,
                            bathrooms    = Decimal(str(prop.get("bathrooms", 0))),
                            sqft         = prop.get("sqft", 0) or 0,
                            year_built   = prop.get("year_built") or None,
                            garage       = 0,
                            address      = address,
                            city         = city,
                            state        = state_abbr,
                            zip_code     = zip_code,
                            latitude     = lat,
                            longitude    = lng,
                            neighborhood = mkt_city,
                            condition    = "good",
                            cross_street = "invh",
                            is_published = True,
                            is_featured  = False,
                        )
                    except Exception as exc:
                        self.stdout.write(
                            self.style.ERROR(f"  DB insert failed for {our_slug}: {exc}")
                        )
                        continue

                    all_existing.add(our_slug)
                    total_props += 1

                    # ── Images via raw SQL ─────────────────────────────────────
                    n_imgs = _insert_images_raw(db_prop.id, image_urls)
                    total_images += n_imgs

                    # ── Amenities ──────────────────────────────────────────────
                    amenity_objs = []
                    for aname in prop.get("amenities", []):
                        if not aname:
                            continue
                        cat_key = _cat_for(aname)
                        cat = cat_objs.get(cat_key) or cat_objs.get("home")
                        if cat:
                            amenity_objs.append(PropertyAmenity(
                                property=db_prop,
                                category=cat,
                                name=str(aname)[:200],
                            ))
                    if amenity_objs:
                        PropertyAmenity.objects.bulk_create(
                            amenity_objs, batch_size=500, ignore_conflicts=True
                        )
                        total_amenities += len(amenity_objs)

                    if total_props % 50 == 0:
                        self.stdout.write(f"  … {total_props} properties saved so far")

            # ── Summary ────────────────────────────────────────────────────────
            self.stdout.write(f"\n{'═'*60}")
            self.stdout.write(self.style.SUCCESS(f"Properties : {total_props}"))
            self.stdout.write(self.style.SUCCESS(f"Images     : {total_images}"))
            self.stdout.write(self.style.SUCCESS(f"Amenities  : {total_amenities}"))
            if dry_run:
                self.stdout.write(self.style.WARNING("DRY RUN — nothing written to database."))
