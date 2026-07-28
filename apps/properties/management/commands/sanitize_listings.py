"""
Management command: sanitize_listings

Post-import cleanup for scraped inventory. Run this after every re-upload.

  1. Marks down price by a percentage YOU specify (deterministic, re-runnable)
  2. Strips source branding, links and HTML out of descriptions
  3. Optionally adds the "Pets Allowed" amenity

Usage:
    python manage.py sanitize_listings --discount 15            # 2000 -> 1700
    python manage.py sanitize_listings --discount 15 --dry-run  # preview, no writes
    python manage.py sanitize_listings --discount 15 --round-to 5
    python manage.py sanitize_listings --discount 0             # restore list prices
    python manage.py sanitize_listings --discount 15 --city Atlanta
    python manage.py sanitize_listings --reset-original         # re-anchor to current price

WHY THIS IS SAFE TO RE-RUN
--------------------------
Every markdown is computed from `Property.original_price`, never from the current
`price`. On first contact with a row, `original_price` is backfilled from `price` and
then left alone forever.

That distinction is the whole point. The older clean_listings command applied its
discount to `price` directly, so each run compounded the last (2000 -> 1400 -> 980 ->
686) and the source figure was unrecoverable after run one. Seeding the RNG per-property
fixed the *percentage* but never the compounding, despite the comment there claiming
otherwise.

Here, `--discount 15` always yields the same number no matter how many times it runs,
and you can move between 15 / 20 / 12 / 0 freely — each run recomputes from the anchor.
"""

import re
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.properties.models import Property, PropertyAmenity, AmenityCategory


HTML_TAG_RE = re.compile(r"<[^>]+>", re.IGNORECASE)
MULTI_SPACE_RE = re.compile(r"\n{3,}")

# Source-operator branding that must not appear on our listings.
BRANDING_RE = re.compile(
    r"(invitation\s*homes|invitationhomes(\.com)?|rently|zillow|trulia|redfin)",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
CTA_RE = re.compile(r"\s*(learn more|view details|apply now|schedule a tour)\s*", re.IGNORECASE)


def clean_description(text: str) -> str:
    """Strip HTML, source URLs, branding and leftover CTA text; tidy whitespace."""
    if not text:
        return text
    out = HTML_TAG_RE.sub("", text)
    out = URL_RE.sub("", out)
    out = BRANDING_RE.sub("", out)
    out = CTA_RE.sub(" ", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = MULTI_SPACE_RE.sub("\n\n", out)
    # Tidy punctuation stranded by the removals above (" ." / " ," / "()").
    out = re.sub(r"\s+([.,;:!?])", r"\1", out)
    out = re.sub(r"\(\s*\)", "", out)
    return out.strip()


class Command(BaseCommand):
    help = "Sanitize imported listings: percentage markdown, de-branded descriptions, pet amenity."

    def add_arguments(self, parser):
        parser.add_argument(
            "--discount", type=Decimal, required=True,
            help="Percent to take OFF the original price. 15 turns 2000 into 1700. Use 0 to restore list prices.",
        )
        parser.add_argument(
            "--round-to", type=int, default=1,
            help="Round the result to the nearest N dollars (e.g. 5, 10, 25). Default 1.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Preview without writing.")
        parser.add_argument("--city", help="Limit to one city (exact, case-insensitive).")
        parser.add_argument("--limit", type=int, help="Process at most N properties.")
        parser.add_argument("--skip-descriptions", action="store_true", help="Leave description text untouched.")
        parser.add_argument("--skip-pets", action="store_true", help="Do not add the Pets Allowed amenity.")
        parser.add_argument(
            "--reset-original", action="store_true",
            help="DESTRUCTIVE: re-anchor original_price to the CURRENT price before applying. "
                 "Only correct when current prices are known-good list prices.",
        )

    # ── Pricing ──────────────────────────────────────────────────────────────
    @staticmethod
    def markdown(original: Decimal, pct: Decimal, round_to: int) -> Decimal:
        """original * (1 - pct/100), rounded to the nearest `round_to` dollars."""
        net = original * (Decimal(100) - pct) / Decimal(100)
        if round_to > 1:
            step = Decimal(round_to)
            net = (net / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step
        return net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def handle(self, *args, **opts):
        pct = opts["discount"]
        if not (Decimal(0) <= pct < Decimal(100)):
            raise CommandError(f"--discount must be >= 0 and < 100 (got {pct}).")
        round_to = opts["round_to"]
        if round_to < 1:
            raise CommandError("--round-to must be >= 1.")

        dry = opts["dry_run"]
        qs = Property.objects.all().order_by("id")
        if opts.get("city"):
            qs = qs.filter(city__iexact=opts["city"])
        if opts.get("limit"):
            qs = qs[: opts["limit"]]
        properties = list(qs)

        self.stdout.write(
            f"{'DRY RUN — nothing will be saved' if dry else 'Applying changes'}\n"
            f"Discount : {pct}%  (round to nearest ${round_to})\n"
            f"Scope    : {len(properties)} properties"
            + (f" in {opts['city']}" if opts.get("city") else "")
            + "\n"
        )

        pet_cat = None
        if not opts["skip_pets"]:
            pet_cat, _ = AmenityCategory.objects.get_or_create(
                name__iexact="pet", defaults={"name": "Pet", "icon": "paw-print"},
            )

        anchored = repriced = descs = pets = 0
        amenity_bulk = []
        samples = []

        with transaction.atomic():
            for prop in properties:
                fields = []

                # ── Anchor ───────────────────────────────────────────────────
                if opts["reset_original"] or prop.original_price is None:
                    prop.original_price = prop.price
                    fields.append("original_price")
                    anchored += 1

                # ── Markdown, always derived from the anchor ─────────────────
                new_price = self.markdown(prop.original_price, pct, round_to)
                if new_price != prop.price:
                    if len(samples) < 10:
                        samples.append(f"    {prop.slug[:48]:<50} ${prop.original_price:>9,.2f} -> ${new_price:>9,.2f}")
                    prop.price = new_price
                    fields.append("price")
                    repriced += 1

                # ── Description ──────────────────────────────────────────────
                if not opts["skip_descriptions"] and prop.description:
                    cleaned = clean_description(prop.description)
                    if cleaned != prop.description:
                        prop.description = cleaned
                        fields.append("description")
                        descs += 1

                # ── Pets ─────────────────────────────────────────────────────
                if pet_cat and not prop.amenities.filter(name__iregex=r"pet|dog|cat|animal").exists():
                    amenity_bulk.append(PropertyAmenity(property=prop, category=pet_cat, name="Pets Allowed"))
                    pets += 1

                if fields and not dry:
                    prop.save(update_fields=fields)

            if amenity_bulk and not dry:
                PropertyAmenity.objects.bulk_create(amenity_bulk, batch_size=500, ignore_conflicts=True)

            if dry:
                transaction.set_rollback(True)

        if samples:
            self.stdout.write("  Sample repricing:")
            for s in samples:
                self.stdout.write(s)
            self.stdout.write("")

        self.stdout.write(self.style.SUCCESS(
            f"Done{' (dry run — rolled back)' if dry else ''}:\n"
            f"  original_price anchored : {anchored}\n"
            f"  prices recalculated     : {repriced}\n"
            f"  descriptions cleaned    : {descs}\n"
            f"  pet amenities added     : {pets}"
        ))
