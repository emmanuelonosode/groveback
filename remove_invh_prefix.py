import json
import os
import sys
import re

# Description cleaning regexes (matching clean_invitationhomes.py)
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
    text = _IH_ANCHOR.sub('', text)
    text = _ALL_ANCHORS.sub('', text)
    text = _HTML_TAGS.sub('', text)
    text = _IH_URL.sub('', text)
    text = _IH_BRAND.sub('', text)
    text = _IH_DOMAIN.sub('', text)
    text = _LEARN_MORE.sub('', text)
    text = _MULTI_SPACE.sub(' ', text)
    text = _MULTI_NL.sub('\n\n', text)
    return text.strip() or None

def fallback_description(fields):
    beds  = fields.get("bedrooms") or 0
    baths = fields.get("bathrooms") or 0
    sqft  = fields.get("sqft") or 0
    city  = fields.get("city") or ''
    state = fields.get("state") or ''
    garage = fields.get("garage") or 0
    year_built = fields.get("year_built") or 0

    bed_label  = 'Studio' if beds == 0 else f'{beds}-bedroom'
    bath_part  = f', {baths} bath{"s" if float(baths) != 1 else ""}' if baths else ''
    sqft_part  = f', {sqft:,} sq ft' if sqft else ''
    loc_part   = f' in {city}, {state}' if city and state else (f' in {city}' if city else '')

    extras = []
    if garage:                 extras.append(f'{garage}-car garage')
    if year_built:             extras.append(f'built {year_built}')

    extra_part = f' Features include {", ".join(extras)}.' if extras else ''

    return (
        f'A {bed_label} home for rent{loc_part}{bath_part}{sqft_part}. '
        f'Available now.{extra_part}'
    ).strip()

def main():
    # 1. Update JSON fixture if it exists in the current directory
    fixture_path = "properties_fixture_prod.json"
    if os.path.exists(fixture_path):
        print(f"Reading {fixture_path}...")
        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        existing_slugs = set()
        for obj in data:
            if obj.get("model") == "properties.property":
                slug = obj.get("fields", {}).get("slug", "")
                if not slug.startswith("invh-"):
                    existing_slugs.add(slug)

        fixture_count = 0
        desc_cleaned = 0
        desc_fallbacks = 0
        
        for obj in data:
            if obj.get("model") == "properties.property":
                fields = obj.get("fields", {})
                slug = fields.get("slug", "")
                cross_street = fields.get("cross_street", "")
                original_desc = fields.get("description", "")
                
                updated = False
                
                # A. Clean slug
                if slug.startswith("invh-"):
                    new_slug = slug[5:]
                    if new_slug in existing_slugs:
                        new_slug = f"{new_slug}-invh"
                    fields["slug"] = new_slug
                    existing_slugs.add(new_slug)
                    updated = True
                
                # B. Clear cross_street
                if cross_street == "invh":
                    fields["cross_street"] = ""
                    updated = True
                
                # C. Clean description
                cleaned_desc = clean_description(original_desc)
                if cleaned_desc is None:
                    new_desc = fallback_description(fields)
                    desc_fallbacks += 1
                else:
                    new_desc = cleaned_desc
                
                if new_desc != original_desc:
                    fields["description"] = new_desc
                    desc_cleaned += 1
                    updated = True
                    
                # D. Map agent to 43
                if fields.get("agent") != 43:
                    fields["agent"] = 43
                    updated = True
                    
                if updated:
                    fixture_count += 1

        with open(fixture_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Success: Updated/cleaned {fixture_count} properties in properties_fixture_prod.json.")
        print(f"  - Cleaned descriptions: {desc_cleaned}")
        print(f"  - Applied fallbacks:    {desc_fallbacks}")
    else:
        print("No properties_fixture_prod.json file found in the current working directory to process.")

    # 2. Update Database (if Django environment is initialized)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
    try:
        import django
        django.setup()
        from apps.properties.models import Property
        from django.db import IntegrityError
        from django.db.models import Q

        db_count = 0
        skipped_count = 0
        db_desc_cleaned = 0
        
        existing_db_slugs = set(Property.objects.exclude(slug__startswith="invh-").values_list("slug", flat=True))

        # Check all properties that might need updating (slug, cross_street, or containing brand keywords)
        props_to_update = Property.objects.filter(
            Q(slug__startswith="invh-") | 
            Q(cross_street="invh") |
            Q(description__icontains="invitation") |
            Q(description__icontains="href")
        )

        for p in props_to_update:
            updated = False
            
            # A. Clean slug
            if p.slug.startswith("invh-"):
                original_slug = p.slug
                new_slug = original_slug[5:]
                if new_slug in existing_db_slugs:
                    new_slug = f"{new_slug}-invh"
                p.slug = new_slug
                existing_db_slugs.add(new_slug)
                updated = True
                
            # B. Clear cross_street
            if p.cross_street == "invh":
                p.cross_street = ""
                updated = True
                
            # C. Clean description
            original_desc = p.description or ""
            cleaned_desc = clean_description(original_desc)
            if cleaned_desc is None:
                # Need to run model logic for has_pool_amenity
                # Define helper for fallback
                beds  = p.bedrooms or 0
                baths = p.bathrooms or 0
                sqft  = p.sqft or 0
                city  = p.city or ''
                state = p.state or ''
                bed_label  = 'Studio' if beds == 0 else f'{beds}-bedroom'
                bath_part  = f', {baths} bath{"s" if float(baths) != 1 else ""}' if baths else ''
                sqft_part  = f', {sqft:,} sq ft' if sqft else ''
                loc_part   = f' in {city}, {state}' if city and state else (f' in {city}' if city else '')
                
                extras = []
                if p.garage:
                    extras.append(f'{p.garage}-car garage')
                if p.year_built:
                    extras.append(f'built {p.year_built}')
                try:
                    if p.amenities.filter(name__icontains='pool').exists():
                        extras.append('pool')
                except Exception:
                    pass
                extra_part = f' Features include {", ".join(extras)}.' if extras else ''
                new_desc = f'A {bed_label} home for rent{loc_part}{bath_part}{sqft_part}. Available now.{extra_part}'
            else:
                new_desc = cleaned_desc
                
            if new_desc != original_desc:
                p.description = new_desc
                db_desc_cleaned += 1
                updated = True
                
            if updated:
                try:
                    p.save()
                    db_count += 1
                except IntegrityError:
                    skipped_count += 1

        print(f"Success: Updated/cleaned {db_count} database properties. (Skipped/Failed: {skipped_count})")
        print(f"  - Cleaned database descriptions: {db_desc_cleaned}")
    except Exception as e:
        print(f"Database update skipped or failed (not running inside a Django project): {e}")

if __name__ == "__main__":
    main()
