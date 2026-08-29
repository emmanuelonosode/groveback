"""Management command: audit_brand_leaks

Answers one question: would anything we serve name the upstream operator?

It checks what the API actually returns — running each property through the
real serializers — rather than grepping columns, because the serializers now
sanitise on output. A column can hold upstream text and still be safe; what
matters is the bytes a visitor or Googlebot receives.

Exits non-zero when a leak is found, so it can gate a deploy.

Usage:
    python manage.py audit_brand_leaks
    python manage.py audit_brand_leaks --fix     # rewrite offending rows in place
    python manage.py audit_brand_leaks --sample 500
"""

import json
import sys

from django.core.management.base import BaseCommand

from apps.properties.models import Property, PropertyImage
from apps.properties.sanitize import (
    _BRAND_BARE_RE,
    _DOMAIN_RE,
    brand_image_url,
    build_property_slug,
    sanitize_text,
)

# Columns worth rewriting when --fix is passed.
_TEXT_FIELDS = (
    "title", "description", "cross_street", "virtual_tour_url",
    "neighborhood", "address",
)
_BLOB_FIELDS = ("schools", "fees", "floor_plans", "office_info", "raw_data")


def _hits(text):
    return bool(_BRAND_BARE_RE.search(text or "")) or bool(_DOMAIN_RE.search(text or ""))


class Command(BaseCommand):
    help = "Report (and optionally fix) upstream brand leaks in served property data."

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true",
                            help="Rewrite offending rows in place.")
        parser.add_argument("--sample", type=int, default=0,
                            help="Audit only N properties (0 = all).")
        parser.add_argument("--reslug", action="store_true",
                            help="Also rewrite slugs still carrying the upstream listing ID.")

    def handle(self, *args, **options):
        from apps.properties.serializers import PropertyDetailSerializer, PropertyListSerializer

        qs = Property.objects.all().prefetch_related("images", "amenities")
        if options["sample"]:
            qs = qs.order_by("?")[: options["sample"]]

        served_leaks, stored_leaks, image_leaks, slug_leaks = [], [], [], []
        total = 0

        for prop in qs.iterator(chunk_size=200):
            total += 1

            # 1. What the API actually serves.
            for ser in (PropertyDetailSerializer, PropertyListSerializer):
                if _hits(json.dumps(ser(prop).data)):
                    served_leaks.append((prop.pk, prop.slug, ser.__name__))

            # 2. What is stored (safe today thanks to output sanitising, but it
            #    rots into a leak the moment a new field or export is added).
            for field in _TEXT_FIELDS + _BLOB_FIELDS:
                if _hits(str(getattr(prop, field, "") or "")):
                    stored_leaks.append((prop.pk, prop.slug, field))

            # 3. Slugs still carrying the upstream internal listing ID.
            if prop.slug and prop.city and prop.address:
                ours = build_property_slug(prop.city, prop.state, prop.address)
                if ours and prop.slug != ours and not prop.slug.startswith(ours):
                    slug_leaks.append((prop.pk, prop.slug, ours))

            if options["fix"]:
                self._fix(prop, options["reslug"])

        image_leaks = list(
            PropertyImage.objects.filter(image__icontains="invitationhomes")
            .values_list("id", "image")[:50]
        )
        image_leak_count = PropertyImage.objects.filter(image__icontains="invitationhomes").count()

        if options["fix"]:
            fixed = 0
            for img in PropertyImage.objects.filter(image__icontains="invitationhomes").iterator():
                branded = brand_image_url(img.image)
                if branded != img.image:
                    img.image = branded
                    img.save(update_fields=["image"])
                    fixed += 1
            self.stdout.write(self.style.SUCCESS(f"Rewrote {fixed} image URLs."))

        self.stdout.write("")
        self.stdout.write(f"Audited {total} properties.")
        self.stdout.write(f"  served responses leaking : {len(served_leaks)}")
        self.stdout.write(f"  stored columns leaking   : {len(stored_leaks)}")
        self.stdout.write(f"  image rows on upstream CDN: {image_leak_count}")
        self.stdout.write(f"  slugs carrying upstream ID: {len(slug_leaks)}")

        for label, rows in (
            ("SERVED", served_leaks[:10]),
            ("STORED", stored_leaks[:10]),
            ("SLUG", slug_leaks[:10]),
        ):
            for row in rows:
                self.stdout.write(f"    {label}: {row}")

        if served_leaks or image_leak_count:
            self.stderr.write(self.style.ERROR("Brand leak present in served output."))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS("No brand leak reaches served output."))

    def _fix(self, prop, reslug):
        changed = []
        for field in _TEXT_FIELDS + _BLOB_FIELDS:
            current = getattr(prop, field, None)
            cleaned = sanitize_text(current)
            if cleaned != current:
                setattr(prop, field, cleaned)
                changed.append(field)
        if reslug and prop.city and prop.address:
            ours = build_property_slug(
                prop.city, prop.state, prop.address,
                existing=lambda c, pk: Property.objects.filter(slug=c).exclude(pk=prop.pk).exists(),
                pk=prop.pk,
            )
            if ours and ours != prop.slug:
                prop.slug = ours
                changed.append("slug")
        if changed:
            prop.save(update_fields=changed)
