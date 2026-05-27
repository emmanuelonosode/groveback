"""
Management command: clean_invitationhomes

Removes all InvitationHomes links, URLs, and brand mentions from property
descriptions. Properties whose descriptions are entirely HTML/IH content
get a clean fallback description generated from their own data.

Usage:
    python manage.py clean_invitationhomes
    python manage.py clean_invitationhomes --dry-run
"""

import re
from django.core.management.base import BaseCommand
from apps.properties.models import Property


# Patterns to strip
_IH_ANCHOR    = re.compile(r'<a[^>]*invitationhomes\.com[^>]*>.*?</a>', re.I | re.S)
_ALL_ANCHORS  = re.compile(r'<a[^>]*>.*?</a>', re.I | re.S)
_HTML_TAGS    = re.compile(r'<[^>]+>', re.I)
_IH_URL       = re.compile(r'https?://(?:www\.)?invitationhomes\.com\S*', re.I)
_IH_BRAND     = re.compile(r'\bInvitation\s*Homes?\b', re.I)
_IH_DOMAIN    = re.compile(r'\binvitationhomes\.com\b', re.I)
_LEARN_MORE   = re.compile(r'\bLearn\s+More\b', re.I)
_MULTI_NL     = re.compile(r'\n{3,}')
_MULTI_SPACE  = re.compile(r'[ \t]+')


def clean_description(text):
    if not text:
        return None
    # Remove IH anchor tags first (preserves inner text of non-IH links)
    text = _IH_ANCHOR.sub('', text)
    # Remove all remaining anchor tags
    text = _ALL_ANCHORS.sub('', text)
    # Strip all remaining HTML tags
    text = _HTML_TAGS.sub('', text)
    # Remove IH URLs, brand name, domain
    text = _IH_URL.sub('', text)
    text = _IH_BRAND.sub('', text)
    text = _IH_DOMAIN.sub('', text)
    text = _LEARN_MORE.sub('', text)
    # Normalise whitespace
    text = _MULTI_SPACE.sub(' ', text)
    text = _MULTI_NL.sub('\n\n', text)
    text = text.strip()
    return text or None  # return None if nothing left after cleaning


def fallback_description(prop):
    """Generate a clean description when the original was empty or IH-only."""
    beds  = prop.bedrooms or 0
    baths = prop.bathrooms or 0
    sqft  = prop.sqft or 0
    city  = prop.city or ''
    state = prop.state or ''

    bed_label  = 'Studio' if beds == 0 else f'{beds}-bedroom'
    bath_part  = f', {baths} bath{"s" if float(baths) != 1 else ""}' if baths else ''
    sqft_part  = f', {sqft:,} sq ft' if sqft else ''
    loc_part   = f' in {city}, {state}' if city and state else (f' in {city}' if city else '')

    extras = []
    if prop.has_pool_amenity():     extras.append('pool')
    if prop.garage:                 extras.append(f'{prop.garage}-car garage')
    if prop.year_built:             extras.append(f'built {prop.year_built}')

    extra_part = f' Features include {", ".join(extras)}.' if extras else ''

    return (
        f'A {bed_label} home for rent{loc_part}{bath_part}{sqft_part}. '
        f'Available now.{extra_part}'
    ).strip()


# Monkey-patch a helper onto Property for the fallback check
def _has_pool(self):
    return self.amenities.filter(name__icontains='pool').exists()
Property.has_pool_amenity = _has_pool


class Command(BaseCommand):
    help = 'Strip InvitationHomes links and brand mentions from all property descriptions.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Preview changes without saving to the database.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be saved.\n'))

        props  = Property.objects.all().order_by('id')
        total  = props.count()
        cleaned_count  = 0
        fallback_count = 0

        self.stdout.write(f'Processing {total} properties...\n')

        for i, prop in enumerate(props.iterator(chunk_size=500), 1):
            original    = prop.description or ''
            cleaned     = clean_description(original)

            if cleaned is None:
                # Description was empty or entirely IH content — use fallback
                new_desc = fallback_description(prop)
                fallback_count += 1
            else:
                new_desc = cleaned

            if new_desc != original:
                cleaned_count += 1
                if dry_run and cleaned_count <= 5:
                    self.stdout.write(f'\n  [{i}] {prop.slug}')
                    self.stdout.write(f'  BEFORE: {original[:120]!r}')
                    self.stdout.write(f'  AFTER : {new_desc[:120]!r}')
                elif not dry_run:
                    prop.description = new_desc
                    prop.save(update_fields=['description'])

            if i % 500 == 0:
                self.stdout.write(f'  {i}/{total} processed...')

        self.stdout.write(self.style.SUCCESS(
            f'\n=== DONE {"(dry run)" if dry_run else ""} ==='
        ))
        self.stdout.write(f'Total properties   : {total}')
        self.stdout.write(f'Descriptions updated: {cleaned_count}')
        self.stdout.write(f'Fallbacks applied  : {fallback_count}')
