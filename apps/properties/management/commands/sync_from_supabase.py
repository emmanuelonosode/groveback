"""Management command: sync_from_supabase

Pulls available listings from the Supabase data lake into the local catalogue.

Everything the feed supplies is treated as untrusted, third-party branded
content. Three things happen to it on the way in, all of them in
`apps.properties.sanitize` so the other importers share the same rules:

* text and JSON blobs are scrubbed of the upstream brand, domains, emails and
  phone numbers;
* image URLs are re-pointed at our own `/media/properties/...` proxy, so no
  public response ever names a third-party CDN;
* the slug is regenerated as `<city>-<state>-<address>` rather than reusing the
  upstream one, which embeds the originating operator's internal listing ID.

Usage:
    python manage.py sync_from_supabase
    python manage.py sync_from_supabase --dry-run
    python manage.py sync_from_supabase --limit 50
"""

import os
import time
from decimal import Decimal, InvalidOperation

import requests
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.properties.models import Property, PropertyImage, PropertyAmenity
from apps.properties.sanitize import (
    brand_image_url,
    build_property_slug,
    is_clean,
    sanitize_text,
)

DEFAULT_SUPABASE_URL = "https://okrlwuoqnwujffzyzazw.supabase.co"
PAGE_SIZE = 100
MAX_RETRIES = 3


def _decimal(value, default="0"):
    """Feed numerics arrive as strings, nulls, and occasionally "1,995.00"."""
    try:
        return Decimal(str(value if value not in (None, "") else default).replace(",", ""))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _int(value, default=0):
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


class Command(BaseCommand):
    help = "Sync available properties from the Supabase data lake, de-branded and re-slugged."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and transform, report what would change, write nothing.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Stop after N listings (0 = no limit). For spot-checking a run.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]

        base_url = os.environ.get("SUPABASE_URL", DEFAULT_SUPABASE_URL).rstrip("/")
        key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
        if not key:
            self.stderr.write(
                self.style.ERROR(
                    "SUPABASE_KEY is not set. Add it to groveback/.env — the feed "
                    "credential no longer ships in source."
                )
            )
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no writes will be made."))

        listings = self._fetch_all(base_url, key, limit)
        if not listings:
            self.stderr.write(self.style.ERROR("No listings fetched; aborting without writing."))
            return

        self.stdout.write(f"Fetched {len(listings)} available listings. Transforming...")

        User = get_user_model()
        agent = User.objects.filter(role="AGENT").order_by("id").first()
        if agent is None:
            agent = User.objects.filter(is_superuser=True).order_by("id").first()
        if agent is None:
            self.stderr.write(
                self.style.ERROR("No agent or superuser exists to own listings; aborting.")
            )
            return

        created = updated = skipped = leaked = 0
        # Slugs claimed during this run — two feed rows can share an address, and
        # the DB check alone would not see the sibling until it was committed.
        claimed = set()

        for row in listings:
            result = self._sync_one(row, agent, claimed, dry_run)
            if result == "created":
                created += 1
            elif result == "updated":
                updated += 1
            elif result == "leaked":
                leaked += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. created={created} updated={updated} skipped={skipped} "
                f"rejected_for_brand_leak={leaked}"
            )
        )
        if leaked:
            self.stderr.write(
                self.style.WARNING(
                    f"{leaked} listing(s) still contained upstream brand text after "
                    "sanitising and were not saved. Check apps/properties/sanitize.py."
                )
            )

    # ── fetch ────────────────────────────────────────────────────────────────
    def _fetch_all(self, base_url, key, limit):
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        rows, offset = [], 0

        while True:
            url = (
                f"{base_url}/rest/v1/properties"
                f"?status=eq.available&select=*&limit={PAGE_SIZE}&offset={offset}"
            )
            page = None
            for attempt in range(MAX_RETRIES):
                try:
                    res = requests.get(url, headers=headers, timeout=25)
                except requests.exceptions.RequestException as exc:
                    self.stderr.write(f"Network error at offset {offset}: {exc}. Retrying...")
                    time.sleep(2 * (attempt + 1))
                    continue
                if res.status_code != 200:
                    self.stderr.write(f"Supabase returned {res.status_code}: {res.text[:200]}")
                    return rows
                page = res.json()
                break

            if page is None:
                # Exhausted retries on a network fault. Returning a partial page set
                # here would let the caller treat a truncated feed as authoritative,
                # so bail loudly instead.
                self.stderr.write(
                    self.style.ERROR(f"Giving up at offset {offset} after {MAX_RETRIES} attempts.")
                )
                return rows
            if not page:
                break

            rows.extend(page)
            self.stdout.write(f"  fetched {len(rows)} so far...")
            if limit and len(rows) >= limit:
                return rows[:limit]
            offset += PAGE_SIZE

        return rows

    # ── transform + write ────────────────────────────────────────────────────
    def _sync_one(self, row, agent, claimed, dry_run):
        address = (row.get("address") or "").strip()
        city = (row.get("city") or "").strip()
        state = (row.get("state") or "").strip()

        existing = None
        upstream_slug = row.get("slug") or ""
        if upstream_slug:
            # Rows imported before re-slugging still carry the upstream slug;
            # match on it so they are updated in place rather than duplicated.
            existing = Property.objects.filter(slug=upstream_slug).first()
        if existing is None and address and city:
            existing = Property.objects.filter(
                address__iexact=address, city__iexact=city, state__iexact=state
            ).first()

        def taken(candidate, pk):
            if candidate in claimed:
                return True
            qs = Property.objects.filter(slug=candidate)
            if pk:
                qs = qs.exclude(pk=pk)
            return qs.exists()

        slug = build_property_slug(
            city, state, address, existing=taken, pk=existing.pk if existing else None
        )
        if not slug:
            self.stderr.write(f"  skip: no city/state/address for upstream '{upstream_slug}'")
            return "skipped"

        price = _decimal(row.get("price"))
        fields = {
            "title": sanitize_text(row.get("title") or ""),
            "description": sanitize_text(row.get("description") or ""),
            "address": sanitize_text(address),
            "city": city,
            "state": state[:2].upper(),
            "zip_code": (row.get("zip_code") or "")[:10],
            "price": price,
            "original_price": price,
            "bedrooms": _int(row.get("bedrooms")),
            "bathrooms": _decimal(row.get("bathrooms")),
            "sqft": _int(row.get("sqft")),
            "year_built": _int(row.get("year_built")),
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
            "cross_street": sanitize_text(row.get("cross_street") or "")[:200],
            "virtual_tour_url": sanitize_text(row.get("virtual_tour_url") or "")[:200],
            "fees": sanitize_text(row.get("fees")),
            "floor_plans": sanitize_text(row.get("floor_plans")),
            "schools": sanitize_text(row.get("schools")),
            "office_info": sanitize_text(row.get("office")),
            "available_on": (row.get("available_on") or "")[:100],
            "is_pet_friendly": bool(row.get("is_pet_friendly")),
            "has_pool": bool(row.get("has_pool")),
            "allow_selfshow": bool(row.get("allow_selfshow")),
            "neighborhood": sanitize_text(row.get("market_name") or "")[:100],
            "raw_data": sanitize_text(row.get("raw_data") or {}),
            "status": "available",
            "type": "residential",
            "listing_type": "for-rent",
            "price_label": "/mo",
            "condition": "good",
            "garage": 0,
            "stories": 1,
            "tour_360_url": "",
            "is_featured": False,
            "homepage_featured": False,
            "is_published": True,
            "agent_id": agent.id,
        }

        images = [
            url
            for url in (brand_image_url(u) for u in self._image_urls(row))
            if url
        ]
        amenities = [
            name
            for name in (
                sanitize_text(a.get("name") if isinstance(a, dict) else a)
                for a in (row.get("amenities") or [])
            )
            if name
        ]

        # Refuse to persist anything still carrying upstream branding. A leak that
        # reaches the database is served to visitors and indexed before anyone
        # notices; failing the row is cheap by comparison.
        payload = [fields[k] for k in ("title", "description", "fees", "floor_plans",
                                       "schools", "office_info", "cross_street",
                                       "virtual_tour_url")]
        if not is_clean(payload) or not is_clean(images) or not is_clean(amenities):
            self.stderr.write(f"  reject (brand leak survived): {slug}")
            return "leaked"

        claimed.add(slug)
        if dry_run:
            action = "update" if existing else "create"
            self.stdout.write(f"  would {action}: {slug} ({len(images)} images)")
            return "updated" if existing else "created"

        with transaction.atomic():
            if existing:
                for key, value in fields.items():
                    setattr(existing, key, value)
                existing.slug = slug
                existing.save()
                prop, was_created = existing, False
            else:
                prop = Property.objects.create(slug=slug, **fields)
                was_created = True

            if images:
                PropertyImage.objects.filter(property=prop).delete()
                PropertyImage.objects.bulk_create(
                    [
                        PropertyImage(property=prop, image=url, is_primary=(i == 0), order=i)
                        for i, url in enumerate(images)
                    ]
                )
            if amenities:
                PropertyAmenity.objects.filter(property=prop).delete()
                PropertyAmenity.objects.bulk_create(
                    [PropertyAmenity(property=prop, name=name[:100]) for name in amenities]
                )

        return "created" if was_created else "updated"

    @staticmethod
    def _image_urls(row):
        """Normalise the feed's several image shapes into a flat list of URLs.

        Older rows store a list of dicts, a bare string, or a stringified dict
        left behind by an early scraper.
        """
        import ast

        raw = row.get("images") or []
        if isinstance(raw, str):
            raw = [raw]

        urls = []
        for item in raw:
            if isinstance(item, dict):
                urls.append(item.get("image_url"))
            elif isinstance(item, str) and item.startswith("{") and "'image_url'" in item:
                try:
                    urls.append(ast.literal_eval(item).get("image_url"))
                except (ValueError, SyntaxError):
                    urls.append(item)
            else:
                urls.append(item)
        return [u for u in urls if u]
