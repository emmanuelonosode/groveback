"""
Management command: sync_invitationhomes

Refreshes the Invitation Homes partnership inventory. This is the command to run
whenever you want fresh houses.

    python manage.py sync_invitationhomes --dry-run --limit 20   # rehearsal
    python manage.py sync_invitationhomes                         # full sync
    python manage.py sync_invitationhomes --discount 15           # sync + subsidy pricing

WHY THIS REPLACES scrape_invitationhomes
----------------------------------------
The old scraper crawled `/markets/homes-for-rent/{market}` and parsed `__NEXT_DATA__`.
All of that is dead: Invitation Homes moved off Next.js, and the market path is now
`/markets/houses-for-rent/{city}-{state}` — two changes at once, so every request 404'd
and the scraper silently imported nothing. That is why inventory froze in May.

It also used `Property.objects.create()` and skipped slugs it had already seen, so even
when it worked it could only ADD listings — never reprice, never update availability,
never notice a home had been taken off the market.

This command instead reads their public property sitemap (4,000+ direct listing URLs, no
pagination) and parses the schema.org JSON-LD each page already publishes for Google —
address, geo, beds, baths, floor size, amenities, images, availability and price, plus a
stable `sku`. Structured data maintained for search engines is far more durable than CSS
selectors, and survives the A/B tests running on their front end.

FRESHNESS
---------
Rows are only written when a field actually changed. `updated_at` is `auto_now`, so
saving unconditionally would restamp all 4,000 rows on every run and tell Google the
whole catalogue changed daily — which is exactly how a site teaches Google to distrust
its <lastmod> (see the note in grovefront/lib/sitemap-data.ts). Untouched listings keep
their real timestamp, so the sitemap stays honest and genuinely-changed homes stand out.

PRICING
-------
`Offer.price` from their page is stored as `original_price` — the partnership list price.
`--discount` then derives the subsidised `price` from it. Re-running never compounds,
because the markdown is always computed from the anchor. See sanitize_listings.
"""

# PEP 604 unions (`dict | None`) in annotations — the production venv is 3.12 but the
# local one is 3.9, and without this the module fails to import there.
from __future__ import annotations

import re
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation

import requests
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.properties.models import (
    Property, PropertyImage, PropertyAmenity, AmenityCategory,
)

User = get_user_model()

SITEMAP_URL = "https://invitationhomes.com/property/sitemap.xml"
LISTING_RE = re.compile(r"/houses-for-rent/[^/]+$")

# Identify honestly. This is a partnership sync, not anonymous scraping, and a real UA
# means they can see who we are in their logs and contact us if the rate is a problem.
HEADERS = {
    "User-Agent": (
        "PrimeFamilyHousingBot/1.0 (partnership inventory sync; "
        "+https://primefamilyhousing.com; housing@primefamilyhousing.com)"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

LD_RE = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)


# ── JSON-LD helpers ──────────────────────────────────────────────────────────
def _iter_nodes(doc):
    """Yield every dict in a JSON-LD document, however deeply nested."""
    stack = [doc]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            yield node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def _dec(value, default=None):
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return default


def _coord(value):
    """
    Round to the 6 decimal places Property.latitude/longitude actually store.

    Their JSON-LD publishes coordinates at up to 12 dp. Django silently rounds those on
    save, so comparing the raw parsed value against the stored one always differed and
    the row was rewritten on every single sync — restamping updated_at forever and
    poisoning the <lastmod> signal this command exists to keep honest.
    """
    d = _dec(value)
    return None if d is None else d.quantize(Decimal("0.000001"))


def _js_literal(text: str, key: str):
    """
    Return the balanced {...} / [...] literal that follows `key:` in the page's embedded
    app state, or None.

    Their detail pages ship the full internal listing record as a JavaScript object
    literal (unquoted keys, so not valid JSON). The schema.org block alongside it is
    clean but deliberately minimal — one hero image and no amenity categories, year
    built, tours or availability date. Everything else lives here.

    Brace-counting rather than regex because the record nests several levels deep and
    contains braces inside description strings.
    """
    i = text.find(key + ":")
    if i < 0:
        return None
    j = i + len(key) + 1
    while j < len(text) and text[j] not in "[{":
        j += 1
    if j >= len(text):
        return None
    open_c = text[j]
    close_c = "]" if open_c == "[" else "}"
    depth, k, instr, esc = 0, j, None, False
    while k < len(text):
        c = text[k]
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == instr:
                instr = None
        else:
            if c in "\"'":
                instr = c
            elif c == open_c:
                depth += 1
            elif c == close_c:
                depth -= 1
                if depth == 0:
                    return text[j:k + 1]
        k += 1
    return None


def _js_to_json(js: str) -> str:
    """Quote bare identifier keys and normalise single-quoted strings so json can read it."""
    js = re.sub(r'([{,])\s*([A-Za-z_$][\w$]*)\s*:', r'\1"\2":', js)
    js = re.sub(r"'((?:[^'\\]|\\.)*)'", lambda m: json.dumps(m.group(1)), js)
    return js


def _embedded(html: str, key: str, default):
    lit = _js_literal(html, key)
    if not lit:
        return default
    try:
        return json.loads(_js_to_json(lit))
    except Exception:
        return default


def _scalar(html: str, key: str):
    """Pull a simple `key:value` scalar out of the embedded record."""
    m = re.search(rf'\b{key}:\s*("(?:[^"\\]|\\.)*"|true|false|null|-?\d+(?:\.\d+)?)', html)
    if not m:
        return None
    raw = m.group(1)
    try:
        return json.loads(raw)
    except Exception:
        return None


def parse_listing(html: str, url: str) -> dict | None:
    """Pull a normalised listing dict out of a detail page's JSON-LD."""
    residence = offer = product = None
    for block in LD_RE.findall(html):
        try:
            doc = json.loads(block)
        except Exception:
            continue
        for node in _iter_nodes(doc):
            t = node.get("@type")
            if t in ("SingleFamilyResidence", "Residence", "House", "Apartment") and not residence:
                residence = node
            elif t == "Offer" and node.get("price") is not None and not offer:
                offer = node
            elif t == "Product" and not product:
                product = node

    if not residence:
        return None

    addr = residence.get("address") or {}
    geo = residence.get("geo") or {}
    floor = residence.get("floorSize") or {}
    slug = url.rstrip("/").rsplit("/", 1)[-1]

    # ── Photos ───────────────────────────────────────────────────────────────
    # The embedded record carries the full gallery (typically 15–20 shots: every
    # bedroom, kitchen, both elevations, floor plans). schema.org only exposes the
    # single hero image, so relying on it alone gave each listing ONE photo.
    photos = _embedded(html, "photos", []) or []
    gallery = []
    for p in sorted(
        [p for p in photos if isinstance(p, dict) and p.get("image_url")],
        key=lambda p: (not p.get("is_primary"), p.get("sequence") or 0),
    ):
        gallery.append({"url": p["image_url"], "primary": bool(p.get("is_primary"))})

    if not gallery:  # fall back to the schema.org hero
        for key in ("image", "photo"):
            val = residence.get(key) or (product or {}).get(key)
            if isinstance(val, str):
                gallery.append({"url": val, "primary": True})
            elif isinstance(val, list):
                gallery.extend(
                    {"url": v if isinstance(v, str) else v.get("url", ""), "primary": False}
                    for v in val
                )
    seen_img = set()
    gallery = [
        g for g in gallery
        if g["url"].startswith("http") and not (g["url"] in seen_img or seen_img.add(g["url"]))
    ]

    # ── Amenities ────────────────────────────────────────────────────────────
    # Embedded list carries a `category` per amenity; schema.org's amenityFeature is
    # names only. Prefer the richer one so they group correctly in the UI.
    amenities = []
    for a in _embedded(html, "amenities", []) or []:
        if isinstance(a, dict) and a.get("name"):
            amenities.append({"name": a["name"].strip(), "category": (a.get("category") or "").strip()})
    if not amenities:
        amenities = [
            {"name": a.get("name", "").strip(), "category": ""}
            for a in (residence.get("amenityFeature") or [])
            if isinstance(a, dict) and a.get("name")
        ]

    year_built = _scalar(html, "year_built")
    tour = _scalar(html, "virtual_tour_url") or ""
    tour_mobile = _scalar(html, "virtual_tour_url_mobile") or ""
    market = _scalar(html, "market_name") or ""

    availability = str((offer or {}).get("availability", "")).lower()

    return {
        "slug": slug,
        "external_id": str((product or {}).get("sku") or ""),
        "description": (residence.get("description") or "").strip(),
        "price": _dec((offer or {}).get("price")),
        "available": "instock" in availability or "presale" in availability,
        "address": (addr.get("streetAddress") or "").strip(),
        "city": (addr.get("addressLocality") or "").strip(),
        "state": (addr.get("addressRegion") or "").strip()[:2],
        "zip_code": (addr.get("postalCode") or "").strip(),
        "latitude": _coord(geo.get("latitude")),
        "longitude": _coord(geo.get("longitude")),
        "bedrooms": int(_dec(residence.get("numberOfBedrooms"), 0) or 0),
        "bathrooms": _dec(residence.get("numberOfBathroomsTotal"), Decimal(0)),
        "sqft": int(_dec(floor.get("value"), 0) or 0),
        "year_built": int(year_built) if isinstance(year_built, (int, float)) else None,
        "virtual_tour_url": tour if isinstance(tour, str) else "",
        "tour_360_url": tour_mobile if isinstance(tour_mobile, str) else "",
        "neighborhood": market if isinstance(market, str) else "",
        "garage": 1 if any("garage" in a["name"].lower() for a in amenities) else 0,
        "images": gallery,
        "amenities": amenities,
        "url": url,
    }


class Command(BaseCommand):
    help = "Sync Invitation Homes partnership inventory from their public property sitemap."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, help="Only process the first N listings.")
        parser.add_argument("--dry-run", action="store_true", help="Fetch and report, write nothing.")
        parser.add_argument("--workers", type=int, default=4, help="Concurrent fetches (default 4; be considerate).")
        parser.add_argument("--delay", type=float, default=0.3, help="Seconds between requests per worker (default 0.3).")
        parser.add_argument("--timeout", type=int, default=30, help="Per-request timeout.")
        parser.add_argument(
            "--discount", type=Decimal, default=None,
            help="Apply the affordability subsidy inline, as a percent off the partnership list price.",
        )
        parser.add_argument(
            "--no-retire", action="store_true",
            help="Do not mark listings that disappeared from their sitemap as unavailable.",
        )
        parser.add_argument(
            "--publish-all", action="store_true",
            help="Publish every synced listing regardless of their availability flag.",
        )
        parser.add_argument(
            "--all-available", action="store_true",
            help="Force status='available' on every synced listing, ignoring their availability flag.",
        )

    # ── Fetch ────────────────────────────────────────────────────────────────
    def listing_urls(self, session, timeout):
        r = session.get(SITEMAP_URL, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        locs = re.findall(r"<loc>([^<]+)</loc>", r.text)
        urls = [u for u in locs if LISTING_RE.search(u) and "/markets/" not in u and "/search/" not in u]
        # Sorted because their sitemap returns the same 4,000 listings in a DIFFERENT
        # order on every fetch. Without this, --limit N takes a random N each run, so a
        # rehearsal never covers the same homes twice and repeat runs look like fresh
        # creates. Irrelevant to a full sync; essential for reproducible testing.
        return sorted(set(urls))

    def fetch(self, session, url, timeout, delay):
        for attempt in range(3):
            try:
                time.sleep(delay)
                r = session.get(url, headers=HEADERS, timeout=timeout)
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                # Force UTF-8. Per RFC 2616 requests falls back to ISO-8859-1 for text/*
                # when the response declares no charset, which silently turns their UTF-8
                # copy into mojibake — "décor" arriving as "dÃ©cor" and landing in the
                # description verbatim. Their pages are UTF-8; say so explicitly.
                r.encoding = "utf-8"
                return parse_listing(r.text, url)
            except Exception:
                if attempt == 2:
                    return None
                time.sleep(2 ** attempt)
        return None

    # ── Write ────────────────────────────────────────────────────────────────
    def upsert(self, data, agent, discount, publish_all=False, all_available=False):
        """
        Returns "created" | "updated" | "unchanged".

        Only calls save() when a value genuinely differs — updated_at is auto_now, so an
        unconditional save would restamp every row and destroy the <lastmod> signal.
        """
        list_price = data["price"]
        if list_price is None:
            return "unchanged"

        price = list_price
        if discount is not None:
            price = (list_price * (Decimal(100) - discount) / Decimal(100)).quantize(Decimal("0.01"))

        beds = data["bedrooms"]
        fields = {
            "title": f"{'Studio' if beds == 0 else f'{beds}-Bed'} House for Rent - "
                     f"{data['address']}, {data['city']}, {data['state']}".strip(" ,-")[:200],
            "description": data["description"] or f"A rental home available in {data['city']}, {data['state']}.",
            "original_price": list_price,
            "price": price,
            "price_label": "/mo",
            "bedrooms": beds,
            "bathrooms": data["bathrooms"],
            "sqft": data["sqft"],
            "address": data["address"][:200],
            "city": data["city"][:100],
            "state": data["state"],
            "zip_code": data["zip_code"][:10],
            "latitude": data["latitude"],
            "longitude": data["longitude"],
            # Availability normally mirrors their feed. The overrides exist because the
            # sync is the authority on these two fields — without them, any manual
            # publish/status change made in the admin or via SQL is silently reverted on
            # the very next run.
            "status": "available" if (all_available or data["available"]) else "rented",
            "type": "residential",
            "listing_type": "for-rent",
            "is_published": bool(publish_all or data["available"]),
            "year_built": data["year_built"],
            "garage": data["garage"],
            "virtual_tour_url": data["virtual_tour_url"][:200],
            "tour_360_url": data["tour_360_url"][:200],
            "neighborhood": data["neighborhood"][:100],
        }

        prop = Property.objects.filter(slug=data["slug"]).first()
        if prop is None:
            prop = Property.objects.create(slug=data["slug"], agent=agent, condition="excellent", **fields)
            self.sync_images(prop, data["images"])
            self.sync_amenities(prop, data["amenities"])
            return "created"

        changed = [f for f, v in fields.items() if getattr(prop, f) != v]
        if changed:
            for f in changed:
                setattr(prop, f, fields[f])
            prop.save(update_fields=changed)
        # Always offered — both helpers compare against what's stored and return early
        # when identical, so galleries and amenities stay in step with their feed
        # (new photos, removed features) without churning rows on a no-op run.
        self.sync_images(prop, data["images"])
        self.sync_amenities(prop, data["amenities"])
        return "updated" if changed else "unchanged"

    def sync_images(self, prop, gallery):
        """Replace the gallery when it differs. Order and primary flag come from their feed."""
        incoming = [g["url"][:500] for g in gallery][:40]
        if not incoming:
            return
        existing = list(prop.images.order_by("order", "id").values_list("image", flat=True))
        if existing == incoming:
            return
        prop.images.all().delete()
        PropertyImage.objects.bulk_create([
            PropertyImage(
                property=prop, image=url,
                is_primary=(gallery[i].get("primary") or i == 0),
                order=i,
            )
            for i, url in enumerate(incoming)
        ])

    def sync_amenities(self, prop, amenities):
        """Mirror their amenity list, preserving their category grouping."""
        incoming = {a["name"][:100] for a in amenities if a.get("name")}
        if not incoming:
            return
        if {a.name for a in prop.amenities.all()} == incoming:
            return

        cats = {}
        for a in amenities:
            label = (a.get("category") or "Features").strip() or "Features"
            if label not in cats:
                cats[label], _ = AmenityCategory.objects.get_or_create(
                    name__iexact=label, defaults={"name": label[:50], "icon": "sparkles"},
                )

        prop.amenities.all().delete()
        seen, rows = set(), []
        for a in amenities:
            name = (a.get("name") or "")[:100]
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            rows.append(PropertyAmenity(
                property=prop,
                category=cats.get((a.get("category") or "Features").strip() or "Features"),
                name=name,
            ))
        PropertyAmenity.objects.bulk_create(rows, batch_size=500)

    # ── Entry point ──────────────────────────────────────────────────────────
    def handle(self, *args, **opts):
        discount = opts["discount"]
        if discount is not None and not (Decimal(0) <= discount < Decimal(100)):
            raise CommandError(f"--discount must be >= 0 and < 100 (got {discount}).")

        agent = User.objects.filter(is_active=True, is_staff=True).order_by("id").first()
        if agent is None:
            raise CommandError("No active staff user to own imported listings. Create one first.")

        session = requests.Session()
        self.stdout.write("Fetching Invitation Homes property sitemap …")
        try:
            urls = self.listing_urls(session, opts["timeout"])
        except Exception as exc:
            raise CommandError(f"Could not read their sitemap: {exc}")

        if opts["limit"]:
            urls = urls[: opts["limit"]]
        self.stdout.write(
            f"  {len(urls)} listing URLs\n"
            f"  workers={opts['workers']} delay={opts['delay']}s "
            f"discount={discount if discount is not None else 'none'}"
            f"{'  [DRY RUN]' if opts['dry_run'] else ''}\n"
        )

        parsed, failed = [], 0
        with ThreadPoolExecutor(max_workers=opts["workers"]) as pool:
            futures = {pool.submit(self.fetch, session, u, opts["timeout"], opts["delay"]): u for u in urls}
            for i, fut in enumerate(as_completed(futures), 1):
                result = fut.result()
                if result:
                    parsed.append(result)
                else:
                    failed += 1
                if i % 250 == 0:
                    self.stdout.write(f"  … fetched {i}/{len(urls)}")

        self.stdout.write(f"\n  parsed {len(parsed)}, failed {failed}\n")

        if opts["dry_run"]:
            for d in parsed[:10]:
                self.stdout.write(
                    f"    {d['slug'][:44]:<46} ${d['price'] or 0:>8,.0f}  "
                    f"{d['bedrooms']}bd/{d['bathrooms']}ba  {d['city']}, {d['state']}  "
                    f"{'available' if d['available'] else 'unavailable'}"
                )
            self.stdout.write(self.style.WARNING("\nDry run — nothing written."))
            return

        created = updated = unchanged = 0
        with transaction.atomic():
            for d in parsed:
                outcome = self.upsert(
                    d, agent, discount,
                    publish_all=opts["publish_all"],
                    all_available=opts["all_available"],
                )
                created += outcome == "created"
                updated += outcome == "updated"
                unchanged += outcome == "unchanged"

            retired = 0
            if not opts["no_retire"] and not opts["limit"]:
                live = {d["slug"] for d in parsed}
                stale = Property.objects.filter(listing_type="for-rent", is_published=True).exclude(slug__in=live)
                retired = stale.update(is_published=False, status="off-market")

        self.stdout.write(self.style.SUCCESS(
            f"Done:\n"
            f"  created   : {created}\n"
            f"  updated   : {updated}\n"
            f"  unchanged : {unchanged}   (untouched — keeps <lastmod> honest)\n"
            f"  retired   : {retired}\n"
            f"  failed    : {failed}"
        ))
